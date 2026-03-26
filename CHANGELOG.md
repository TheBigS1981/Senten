# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-03-26

### Changed
- **Mobile UX improvements** for better usability on phones and tablets
  - Compact header: icon-only theme picker and user menu save ~200px horizontal space
  - Redesigned language selector with native dropdown selects on mobile
  - Language bar height reduced from ~200px to ~90px — **saves 110px vertical space**
  - Increased textarea height from 28vh to 35vh for more visible content (~+80px)
  - All touch targets meet WCAG minimum 44×44px standard
  - Mobile language dropdowns sync bidirectionally with desktop controls
  - Detected language badge now appears on both desktop and mobile views

### Fixed
- Header overflow on small screens (375px-430px width devices)
- Language selector usability on mobile devices
- Touch target sizes below accessibility standards

## [1.0.1] - 2026-03-25

### Added
- Dual action buttons in both tabs for improved workflow flexibility
  - **Tab "Translate"**: Two optimize buttons — optimize source text or optimize translation
  - **Tab "Optimize"**: Two translate buttons — translate source text or translate optimization result
- Dynamic button visibility: output action buttons appear only after successful translation/optimization
- i18n support for new error messages in 5 languages (DE, EN, FR, IT, ES)

### Changed
- Streamlined toolbar design with icon-only buttons for secondary actions
  - Reduced toolbar width by ~156px for better space efficiency
  - Consistent icon usage: pen-fancy (🖊️) for optimize, language (🌐) for translate
  - Improved icon visibility with better contrast and sizing (36×36px)
- Toolbar buttons now auto-resize for multi-icon buttons (e.g., arrow + action icon)
- Tab navigation icon for "Optimize" now matches toolbar icon for consistency

### Fixed
- Icon visibility issues in dark mode (improved contrast and background)
- Button sizing for multi-icon buttons (arrow + action combinations)

## [1.0.0] - 2026-03-16

First public release.

### Added

#### Translation
- DeepL translation with 30+ source and target languages
- Automatic source language detection
- Language swap button (one click to swap source and target)
- Real-time character counter against monthly DeepL quota

#### Writing Optimization
- Style optimization via double-translation (forward + back-translation)
- Diff view — visual highlighting of insertions and deletions

#### LLM Support
- Engine toggle: switch between DeepL and LLM per request
- Supported providers: OpenAI, Anthropic, Ollama, OpenAI-compatible proxies (e.g. LiteLLM)
- SSE streaming with real-time word-by-word output
- Streaming progress overlay — "Translating…" / "Optimizing…" banner until stream completes
- LLM meta-commentary stripping — removes preambles like "Here is the translation:"
- Prompt injection protection — pattern-based detection across 8 categories

#### User Interface
- Multi-language UI: German, English, French, Italian, Spanish
- Dark mode — system-based or manual toggle with multiple color themes (Blue, Violet)
- Translation and optimization history with auto-save and restore
- Output statistics: words, characters, LLM tokens (input/output), estimated EUR cost
- Cumulative 4-week usage stats in header (translated words, optimized words, LLM tokens)
- Keyboard shortcuts: `Ctrl+Enter` (execute), `Ctrl+1`/`2` (tab switch), `Ctrl+D` (theme toggle), `Escape` (clear)
- Auto-processing with 2-second debounce while typing

#### User Management & Authentication
- Three auth modes (auto-detected at startup): OIDC/JWT, HTTP Basic Auth, anonymous
- Session cookie authentication with login/logout and "Remember me"
- Admin panel: user creation, editing, password reset, activation/deactivation
- Gravatar profile pictures
- Per-user settings: theme, UI language, engine preference, session lifetime

#### Security
- Rate limiting: 5 req/min on login, 30 req/min on API endpoints with burst support
- Security headers: CSP with per-request nonce on `script-src`, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- Trusted reverse proxy support for X-Forwarded-For header
- bcrypt password hashing with constant-time compare
- OIDC with JWKS validation, explicit algorithm allowlist, audience check

#### Deployment
- Docker multi-stage build (Python slim image, non-root user, read-only filesystem)
- `docker-compose.yml` for local development
- `docker-compose.server.yml` for production (uses pre-built image from ghcr.io)
- Caddy reverse proxy example configuration (`Caddyfile.example`)
- GitHub Actions CI/CD pipeline: lint → test (538) → Trivy security scan → Docker build & push to ghcr.io
- Dependabot for automated dependency and Actions updates
- Health check endpoints: `GET /health` (liveness) and `GET /health/ready` (readiness, checks DB + DeepL)
- Automatic database migration on startup (idempotent)
