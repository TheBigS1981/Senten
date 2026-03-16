"""Senten — FastAPI application entry point."""

import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded

from app.config import VERSION, get_git_info, settings
from app.limiter import limiter
from app.logging_config import LOGGING
from app.middleware.auth import AuthMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.routers import admin, auth, history, i18n, profile, translate, usage

# Apply structured logging before anything else
logging.config.dictConfig(LOGGING)
logger = logging.getLogger(__name__)

# Resolve paths relative to this file so the app works regardless of cwd
_BASE_DIR = Path(__file__).parent.parent
_STATIC_DIR = _BASE_DIR / "static"
_TEMPLATES_DIR = _BASE_DIR / "templates"


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown hooks
# ---------------------------------------------------------------------------


_SESSION_CLEANUP_INTERVAL_SECONDS = 3600  # Run cleanup every hour


async def _session_cleanup_loop(user_service) -> None:
    """Background task: delete expired sessions every hour."""
    while True:
        await asyncio.sleep(_SESSION_CLEANUP_INTERVAL_SECONDS)
        try:
            count = user_service.cleanup_expired_sessions()
            if count:
                logger.info("Session cleanup: %d expired session(s) removed.", count)
        except Exception as exc:
            logger.warning("Session cleanup failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database on startup and run background tasks."""
    from app.db.database import init_db, migrate_db
    from app.services.user_service import user_service as _user_service

    logger.info("Senten startet — Datenbank wird initialisiert …")
    init_db()
    migrate_db()
    _user_service.ensure_admin_user()
    logger.info("Datenbank bereit.")

    cleanup_task = asyncio.create_task(_session_cleanup_loop(_user_service))
    logger.info(
        "Session-Cleanup-Task gestartet (Intervall: %ds).",
        _SESSION_CLEANUP_INTERVAL_SECONDS,
    )

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Senten wird beendet.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Senten",
    description="AI-powered text refinement via DeepL API",
    version=VERSION,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# --- Rate limiting ---
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors with a proper JSON response."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Zu viele Anfragen. Bitte warte einen Moment und versuche es erneut.",
            "retry_after": exc.detail,
        },
    )


# --- Security headers (must be added first so it wraps everything) ---
app.add_middleware(SecurityHeadersMiddleware)

# --- Authentication ---
app.add_middleware(AuthMiddleware)

# --- CORS ---
# Build the allowed-origins list from config; fall back to empty (same-origin only)
_allowed_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins else [],
    allow_credentials=bool(_allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# --- Static files ---
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# --- Templates ---
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# --- Routers ---
app.include_router(translate.router, prefix="/api", tags=["Translate"])
app.include_router(usage.router, prefix="/api", tags=["Usage"])
app.include_router(history.router, prefix="/api", tags=["History"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(profile.router, prefix="/api", tags=["Profile"])
app.include_router(admin.router, prefix="/api", tags=["Admin"])
app.include_router(i18n.router, prefix="/api", tags=["i18n"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health():
    """Liveness probe — fast check used by Docker / load balancer.

    Only verifies that the process is alive; does NOT check external services.
    Use ``/health/ready`` for a full readiness probe.
    """
    return {"status": "ok", "service": "Senten"}


@app.get("/health/ready", tags=["Health"])
async def health_ready():
    """Readiness probe — verifies database connectivity and service state.

    Returns HTTP 503 if the application is not ready to serve requests so that
    orchestrators (Docker healthcheck, Kubernetes, load balancers) can route
    traffic away until the instance recovers.
    """
    from app.db.database import SessionLocal
    from app.services.deepl_service import deepl_service

    checks: dict[str, str] = {}
    healthy = True

    # ── Database ─────────────────────────────────────────────────────────────
    try:
        from sqlalchemy import text as sa_text

        with SessionLocal() as db:
            db.execute(sa_text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Health/ready: database check failed: %s", exc)
        checks["database"] = "error"
        healthy = False

    # ── DeepL service ────────────────────────────────────────────────────────
    if deepl_service.is_configured():
        checks["deepl"] = "ok"
    elif deepl_service.mock_mode:
        checks["deepl"] = "mock"
    else:
        checks["deepl"] = "error"

    if not healthy:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "service": "Senten", "checks": checks},
        )

    return {"status": "ok", "service": "Senten", "checks": checks}


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Serve the login page."""
    csp_nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "csp_nonce": csp_nonce},
    )


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request):
    """Serve the admin UI."""
    csp_nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "csp_nonce": csp_nonce},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    """Serve the single-page application shell."""
    from app.services.i18n_service import get_translations

    csp_nonce = getattr(request.state, "csp_nonce", "")

    git_hash, is_dev = get_git_info()
    version_display = f"v{VERSION}"
    if is_dev and git_hash:
        version_display = f"v{VERSION}-{git_hash}"

    # Language detection priority: query param > cookie > Accept-Language header
    ui_language = _detect_ui_language(request)

    # Get translations for the detected language
    translations = get_translations(ui_language)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "csp_nonce": csp_nonce,
            "current_year": datetime.now().year,
            "version": version_display,
            "ui_language": ui_language,
            "translations": translations,
        },
    )


def _detect_ui_language(request: Request) -> str:
    """Detect UI language from query param, cookie, or Accept-Language header.

    Priority: 1. ?lang= query parameter
              2. ui_language cookie
              3. Accept-Language header
    """
    from app.services.i18n_service import get_default_language, is_supported

    # 1. Query parameter ?lang=de
    lang_param = request.query_params.get("lang")
    if lang_param and is_supported(lang_param):
        return lang_param

    # 2. Cookie ui_language
    ui_cookie = request.cookies.get("ui_language")
    if ui_cookie and is_supported(ui_cookie):
        return ui_cookie

    # 3. Accept-Language header (e.g., "de-DE,en-US;q=0.9,en;q=0.8")
    accept_lang = request.headers.get("Accept-Language", "")
    if accept_lang:
        # Parse Accept-Language and find first supported language
        for lang in accept_lang.split(","):
            # Extract language code (e.g., "de-DE" -> "de")
            lang_code = lang.split("-")[0].strip().split(";")[0].lower()
            if is_supported(lang_code):
                return lang_code

    return get_default_language()
