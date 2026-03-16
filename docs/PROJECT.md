# Project: Senten

> Self-hosted web interface for the DeepL API

## Overview

Senten provides a self-hosted web interface for the DeepL translation API. Users can translate texts between 30+ languages or optimize their writing style through a double-translation technique, without relying on DeepL's paid web interface.

## Tech Stack

| Layer | Technology |
|-------|-------------|
| Backend | Python 3.11, FastAPI 0.115+ |
| Database | SQLite via SQLAlchemy 2.0 |
| Frontend | Vanilla JavaScript, Jinja2 templates |
| CSS | Tailwind CSS v3 |
| Auth | PyJWT (OIDC/JWT), HTTP Basic Auth, Anonym |
| Rate Limiting | slowapi |
| Tests | pytest, pytest-asyncio, pytest-cov |
| Deployment | Docker |

## Conventions

### Backend

- **Single source of models:** `app/models/schemas.py` — all Pydantic schemas defined here
- **Pydantic v2:** Uses `ConfigDict` and `SettingsConfigDict`
- **Session pattern:** `with SessionLocal() as db:` in services; FastAPI `get_db()` generator for dependency injection
- **Error handling:** Generic HTTP errors to client, full details in server logs only
- **Logging:** `logging.getLogger(__name__)` in every module; configured via `app/logging_config.py`
- **Datetime:** Always `datetime.now(timezone.utc)` — never `datetime.utcnow()`
- **Languages:** Single source of truth in `app/models/schemas.py` (`DEEPL_TARGET_LANGUAGES`, `DEEPL_SOURCE_LANGUAGES`)

### Frontend

- Vanilla JS only (no frameworks)
- CSS custom properties for theming (dark mode via `[data-theme="dark"]`)
- Keyboard shortcuts in dedicated file: `static/js/keyboard-shortcuts.js`
- Numbers formatted with `Intl.NumberFormat('de-DE')`
- Diff display using jsdiff library

### Git

- Conventional Commits format (`<type>(<scope>): <description>`)
- Feature branches recommended

### Docker

- Read-only filesystem with writable `/app/data` volume
- Multi-stage build (slim → slim)
- Non-root user
- Health check endpoints at `/health` (liveness) and `/health/ready` (readness)

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI entry point, middleware, lifespan |
| `app/config.py` | Pydantic Settings configuration |
| `app/logging_config.py` | Logging dictionary configuration |
| `app/routers/translate.py` | Translation and writing optimization endpoints |
| `app/routers/usage.py` | Usage statistics endpoint |
| `app/services/deepl_service.py` | DeepL SDK wrapper with mock mode |
| `app/services/usage_service.py` | SQLite-based usage tracking |
| `app/middleware/auth.py` | Auth middleware (OIDC, Basic, Anonym) |
| `app/middleware/security.py` | Security headers with CSP |
| `app/models/schemas.py` | All Pydantic models and language lists |
| `app/db/database.py` | SQLAlchemy engine, session, init_db |
| `app/db/models.py` | ORM models |
| `static/js/app.js` | Main frontend application |
| `static/js/keyboard-shortcuts.js` | Keyboard shortcut handlers |
| `templates/index.html` | Main HTML template with CSS variables |
| `static/css/input.css` | Tailwind input |
| `static/css/styles.css` | Compiled Tailwind output |

## Scripts

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install and build CSS
npm install && npm run build:css

# Run development server
uvicorn app.main:app --reload

# Run tests (mock mode: DEEPL_API_KEY must be empty or unset)
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Docker
docker compose up --build     # Build and start
docker compose up -d         # Start only (image already built)
docker compose logs -f       # View logs
docker compose down          # Stop
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEEPL_API_KEY` | No | — | DeepL API Key; without it → mock mode |
| `SECRET_KEY` | No | random | Session signing key |
| `DATABASE_URL` | No | `sqlite:///./data/senten.db` | SQLAlchemy DB URL |
| `MONTHLY_CHAR_LIMIT` | No | `500000` | Monthly character budget |
| `ALLOWED_ORIGINS` | No | — | CORS origins, comma-separated |
| `OIDC_DISCOVERY_URL` | No | — | OIDC Discovery URL (enables OIDC mode) |
| `OIDC_CLIENT_ID` | No | — | OIDC Client ID |
| `OIDC_CLIENT_SECRET` | No | — | OIDC Client Secret |
| `AUTH_USERNAME` | No | — | HTTP Basic Auth username |
| `AUTH_PASSWORD` | No | — | HTTP Basic Auth password |
| `LOG_DIR` | No | `data` | Log directory |
| `LLM_PROVIDER` | No | — | LLM provider: `openai`, `anthropic`, `ollama`, `openai-compatible` |
| `LLM_API_KEY` | No | — | LLM API key (optional for Ollama and `openai-compatible`) |
| `LLM_BASE_URL` | No | — | LLM base URL (required for Ollama and `openai-compatible`) |
| `LLM_DISPLAY_NAME` | No | `""` | UI label in engine toggle (e.g. `LiteLLM`) |
| `LLM_TIMEOUT` | No | `30` | Timeout in seconds for LLM requests (min: 1) |
| `LLM_TRANSLATE_MODEL` | No | `gpt-4o` | Model for translation |
| `LLM_WRITE_MODEL` | No | `gpt-4o` | Model for writing optimization |
| `LLM_TRANSLATE_PROMPT` | No | *(built-in)* | System prompt for translation (`{target_lang}` placeholder) |
| `LLM_WRITE_PROMPT` | No | *(built-in)* | System prompt for writing optimization (`{target_lang}` placeholder) |
| `LLM_MAX_INPUT_CHARS` | No | `5000` | Hard cap on LLM input length (cost guard, 1-50000) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Single-Page-App (HTML) |
| GET | `/health` | Liveness probe |
| GET | `/health/ready` | Readiness probe (checks DB + DeepL) |
| POST | `/api/translate` | Translate text |
| POST | `/api/write` | Optimize text (double translation) |
| GET | `/api/config` | DeepL configuration status |
| GET | `/api/usage` | Usage statistics (local + DeepL) |
| GET | `/docs` | Swagger UI (auto-generated) |

## Auth Modes

Senten supports three authentication modes (auto-detected):

1. **OIDC** — when `OIDC_DISCOVERY_URL` is set: Bearer token validation via JWKS
2. **HTTP Basic Auth** — when `AUTH_USERNAME` + `AUTH_PASSWORD` are set (no OIDC)
3. **Anonym** — no auth configured (for home network/VPN use)

Exempt from auth: `/health`, `/static/`, `/favicon`
