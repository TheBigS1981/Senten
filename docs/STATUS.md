# Project Status

> Last updated: 2026-10-10

## Current Version
**v1.0.4** — Latest stable release (2026-10-10)

## Active Development

### Recent Features
- Maintenance release: openai 3.x / anthropic 1.x / bcrypt 5.x, bcrypt 72-byte fix, Debian CVE fixes in Docker image, CI actions v7 (v1.0.4)
- Security & maintenance release: vulnerable deps fixed, all Python deps current within major, Starlette 1.x template fix, CI actions bumped (v1.0.3)
- Mobile UX improvements — compact header, native language dropdowns, larger textareas, 44×44px touch targets (v1.0.2)
- Dual action buttons in Translate/Optimize tabs, icon-only toolbar (v1.0.1)
- Multi-language UI support (i18n) — German, English, French, Italian, Spanish
- Streaming progress overlay for LLM translations
- LLM meta-commentary prevention (strips "Here is the translation:" etc.)

### Known Issues / Tech Debt
- Pending major upgrade: `websockets` 17.x (transitive via uvicorn) — `openai` 3.x, `anthropic` 1.x, `bcrypt` 5.x done in v1.0.4
- Tailwind CSS 4 upgrade — major, requires config migration (CSS-first config, `@tailwindcss/cli`); Dependabot major updates ignored, PR #25 closed
- `docs/api_documentation.md` only covers core endpoints in detail (auth/profile/history/admin/i18n only listed in `docs/PROJECT.md`)

## Recent Decisions
- 2026-09-30: All Python deps upgraded within their major version (incl. SQLAlchemy 2.1, uvicorn 0.54, openai 2.54, anthropic 0.125); Dependabot PRs #1, #2, #3, #15, #24 closed as superseded
- 2026-09-30: Starlette 1.x requires `TemplateResponse(request, name, context)` — fixed in `app/main.py`, HTML pages now covered by `tests/test_pages.py`
- 2026-09-30: Vulnerable deps upgraded (PyJWT, anyio, cryptography, python-multipart, starlette/fastapi, urllib3) — Trivy blocked CI on main
- 2026-09-30: `requirements.txt` = runtime only (pip-compile from `requirements.in`); CI installs `requirements-dev.in` additionally
- 2026-09-30: GitHub Actions bumped (checkout v6, setup-python v6, build-push-action v7, trivy-action 0.36.0) — supersedes Dependabot PRs #1, #2, #3, #15
- 2026-09-30: `docker-compose.server.yml` healthcheck uses Python instead of `curl` (not present in slim image)

## Roadmap

### Planned Features
- Additional UI language support (consideration)
- Performance optimizations for large text translations

## Tech Stack
- Backend: Python 3.11, FastAPI, SQLAlchemy 2.0
- Frontend: Vanilla JavaScript, Tailwind CSS
- Database: SQLite
- Deployment: Docker

## Links
- [README.md](../README.md) — Installation and setup
- [CONTRIBUTING.md](../CONTRIBUTING.md) — How to contribute
- [CHANGELOG.md](../CHANGELOG.md) — Release history
- [SECURITY.md](../SECURITY.md) — Security policy
