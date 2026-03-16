# Project Rules

> **Note for external contributors:** This file contains development guidelines optimized for use with the [opencode](https://opencode.ai) AI coding assistant. Some commands and conventions are specific to that tool. For general contributors, the key files to understand are `docs/PROJECT.md`, `CONTRIBUTING.md`, and `README.md`.

## Agents

Agents are role personas that Claude adopts depending on the task. The `@`-syntax is a convention in the prompt — not a technical trigger. Each agent brings domain-specific behavior and priorities.

| Agent | Invoke via | Scope |
|-------|-----------|-------|
| `build` | default | General implementation, bug fixes, configuration |
| `plan` | Tab key | Analysis and planning without code changes |
| `@backend-architect` | `@backend-architect <task>` | FastAPI architecture, DB schema, API design, system-wide decisions |
| `@frontend` | `@frontend <task>` | Vanilla JS, Tailwind CSS, Jinja2 templates, Dark Mode, UI bugs |
| `@security` | `@security` / `/security-audit` | OWASP Top 10 audit, auth review, CVE analysis — always read-only |
| `@devops` | `@devops <task>` | Docker, GitHub Actions CI/CD, secrets handling, deployment |
| `@tester` | `@tester <task>` | pytest, coverage, test quality, test architecture |
| `@documentation` | `@documentation <task>` | README, CHANGELOG, API docs, ADRs, inline comments |
| `@refactoring` | `@refactoring <task>` | Code quality, tech debt, dependency audit, safe updates |
| `@deep-thinker` | `@deep-thinker <problem>` | Structured analysis of complex problems using mental models |

### Mapping to Claude Task Agent Types

When a subagent is started via the Task tool, the following mappings apply:

| Persona | Claude Task-Agent Type |
|---------|----------------------|
| `@backend-architect` | `Backend Architect` |
| `@frontend` | `Frontend Developer` |
| `@security` | `Security Engineer` |
| `@devops` | `DevOps Automator` |
| `@tester` | `Test Results Analyzer` |
| `@documentation` | `Technical Writer` |
| `@refactoring` | `Workflow Optimizer` |
| `@deep-thinker` | `general` (with explicit analysis task) |

---

## Session Start Protocol

Every agent must execute this protocol at the start of every session, before doing anything else.

### Step 1 — Read project state
```
Read docs/STATUS.md
Read docs/PROJECT.md
```
If `docs/STATUS.md` does not exist, create it using the template structure (see below).
If `docs/PROJECT.md` does not exist, ask the user to fill it in — or run `/harmonize` to generate it automatically.

### Step 2 — Read relevant feature file (if applicable)
If `docs/STATUS.md` lists an active feature relevant to the current task:
```
Read docs/features/<feature-name>.md
```

### Step 3 — Verify file structure
If the file structure is unknown or the task touches unfamiliar areas:
```
tree -L 3 or find . -type f -not -path '*/node_modules/*' -not -path '*/.git/*'
```

### Step 4 — Confirm context
Before writing any code, briefly state:
- What the current project goal is (from STATUS.md)
- Which feature or task is being worked on
- What was done last and what the next step is

If STATUS.md is empty or missing key information, ask the user to clarify before proceeding.

### Session End — Update project state

At the end of every session (or when handing off), update `docs/STATUS.md`:
- Update the status of any feature touched
- Log decisions made under "Recent Decisions"
- Update "Next step" for any in-progress feature
- Move completed features to "Completed This Week"

---

## STATUS.md Template

If `docs/STATUS.md` does not exist, create it with this structure:

```markdown
# Project Status
> Last updated by: <agent> on <date>

## Active Sprint / Current Goal
_Not yet defined._

## Features In Progress
_No features in progress._

## Recent Decisions
_No decisions recorded yet._

## Open Questions
_None._

## Known Issues / Tech Debt
_None recorded._

## Completed This Week
_Nothing completed yet._
```

---

## External References

CRITICAL: Load these files on-demand using the Read tool — only when relevant to the current task. Do NOT preload all files.

**Always read at session start (required):**
- Project status and active features: `@docs/STATUS.md`
- Project description, stack, conventions: `@docs/PROJECT.md`

**Load on-demand when relevant:**
- Which agent to use + example prompts: `@docs/agents-reference.md`
- Subagent flows and coordination: `@docs/agents-flows.md`
- Coding standards detail: `@docs/coding-standards.md`

**Load per feature when in progress:**
- Active feature context: `@docs/features/<feature-name>.md`
- Feature requirements: `@docs/features/<feature-name>.md` (contains PRD if created with /feature)

---

## Operational Protocol: 4-Layer Architecture

Every non-trivial request must pass through these four layers before any code is written. No layer may be skipped.

### Layer 1 — Identity & Constraints
- **If the file structure is unknown, run `tree -L 3` or `find . -type f -not -path '*/node_modules/*' -not -path '*/.git/*'` before proceeding.** Never assume a file path or module structure that has not been verified.
- Assign the appropriate expert role (architect, frontend engineer, security engineer, etc.).
- Identify the project's tech stack and adhere to it strictly.
- Do not introduce new dependencies or patterns without explicit justification.

### Layer 2 — Scope & Logic
- Define business rules and states before implementing.
- Separate logic into clear modules (e.g. Auth, Core, Billing, Notifications).
- Identify which existing modules are affected.

### Layer 3 — The Paranoid Engineer
- Anticipate failure states: what happens if this breaks?
- Check for validation gaps, missing RBAC, and side effects.
- Identify security risks before a single line of code is written.

### Layer 4 — Modular Output
For complex features, always respond in this order:
1. **System diagram** — how does this change fit into the overall system?
2. **Database schema** — which data structures are affected or created?
3. **API routes / controllers** — which endpoints are added or changed?
4. **Frontend components** — which UI elements are affected?
5. **Verification checklist** — self-check before handoff (see Self-Verification below)

For simple tasks (single-file changes, bugfixes), reduce to relevant points — but never omit entirely.

---

## Autonomy Protocol: Plan First, Then Execute

1. **Show the plan** before any non-trivial implementation:
   - What will be changed and why?
   - Which files are affected?
   - Are there risks or dependencies?

2. **Wait for confirmation** — the plan is presented and waits for a green light, unless the task is clearly trivial.
   **Fast-track**: Add `fast:` at the start of any prompt to skip the planning step and execute immediately.
   Example: `fast: @frontend fix the button margin in Header.tsx`

3. **Execute autonomously** — after confirmation, implement fully without further questions, unless an unexpected CRITICAL situation arises.

4. **Deliver a closing report** — after implementation, always output a brief summary of what was done and what remains open.

---

## Self-Verification

Before every response that contains code, check internally:

> *"Is this a functional system architecture — or just a scaffold?"*

- [ ] Does the code fully cover the described scope?
- [ ] Are error scenarios handled?
- [ ] Am I introducing a security vulnerability?
- [ ] Does this fit the existing patterns in the project?
- [ ] Would another developer understand this code without an explanation?

If any answer is "No": fix it first, then output.

---

## Context Management

Long sessions cause early context to fade. Agents must create a State Summary at these triggers:

- After completing a full subagent flow
- When switching agents mid-task
- When uncertain about a decision made earlier in the session
- When the user runs `/summary`

### State Summary format

```
## STATE SUMMARY
**Active agent:** <current agent>
**Task:** <one-sentence description of the overall goal>
**Stack identified (Layer 1):** <tech stack and constraints>
**Scope defined (Layer 2):** <modules affected>
**Risks identified (Layer 3):** <open security or failure concerns>
**Progress:** <what is done / what remains>
**Open decisions:** <anything not yet confirmed by the user>
**Next step:** <exactly what happens next>
```

The State Summary is always output in full — never abbreviated. Run `/summary` before `/compact` to preserve the red thread.

---

## Context Recovery

When an agent loses the thread — after `/compact`, after a long session, or when uncertain about prior decisions — execute this recovery sequence before continuing:

### Recovery sequence

```
1. Read docs/STATUS.md                          ← current project state
2. Read docs/features/<active-feature>.md       ← active feature details (if exists)
3. Read AGENTS.md                               ← protocols and constraints
4. Read relevant skill via skill tool           ← domain-specific rules
5. Run tree -L 3                               ← verify file structure
```

Then output a Recovery Confirmation:

```
## RECOVERY CONFIRMATION
**Status read:** YES/NO
**Active feature:** <name or NONE>
**Last known action:** <from STATUS.md or UNKNOWN>
**Next step:** <from STATUS.md or needs clarification>
**Context sufficient to continue:** YES / NO — <what is missing if NO>
```

If context is insufficient after recovery: ask the user one specific question to resolve the gap. Never guess.

### Trigger recovery when:
- Starting a session after `/compact` was run
- Switching agents mid-task
- Uncertain about a decision made more than 10 messages ago
- User runs `/recover`

---

## Versioning Protocol

Every agent that produces a push-ready or merge-ready result must trigger the versioning check.

Before any push, tag, or deploy, ask:

```
## VERSION CHECK
Current version: <read from package.json, pyproject.toml, Cargo.toml, or git tag>
Last tag: <output of `git describe --tags --abbrev=0`>

Changes in this batch:
- <brief summary>

Suggested bump:
  [ ] patch  (x.x.+1) — bug fixes, dependency updates, minor refactoring
  [ ] minor  (x.+1.0) — new features, non-breaking changes
  [ ] major  (+1.0.0) — breaking changes, major rewrites

→ Which version bump should I apply, or should I skip tagging for this push?
```

Never auto-tag without explicit approval. After confirmation:
1. Update version in project manifest
2. Update `CHANGELOG.md` — move `[Unreleased]` to new version with today's date
3. Stage all changes: `git add -A`
4. Commit using Conventional Commits: `git commit -m "chore: release vX.Y.Z"`
5. `git tag vX.Y.Z && git push && git push --tags`

### Commit messages (Conventional Commits)

All commits — not just releases — must follow this format:
```
<type>(<scope>): <short description>
```
See `docs/coding-standards.md` for the full type list, rules, and examples.

The `@documentation` agent maps `feat` and `fix` commits to CHANGELOG sections before every release.

---

## Handoff Protocol

When an agent passes work to another, always append:

```
## HANDOFF
- **Changes made:** <summary>
- **Needs @backend-architect:** YES/NO — <reason if YES>
- **Needs @frontend:** YES/NO — <reason if YES>
- **Needs @tester:** YES/NO — <reason if YES>
- **Needs @devops:** YES/NO — <reason if YES>
- **Blocking issues:** <list or NONE>
```

---

# Senten — Project Context for AI Agents

Self-hosted web interface for DeepL API and LLM providers (OpenAI, Anthropic, Ollama).  
Users can translate texts (30+ languages) or optimize writing style, with user management,
session history, and admin interface.

**Project structure and key files:** → `docs/PROJECT.md`

---

For environment variables, API endpoints, authentication modes, Docker instructions, and full tech stack details, see `docs/PROJECT.md`.

---

# opencode-Specific Commands

> The following commands are specific to the [opencode](https://opencode.ai) AI coding assistant and require the opencode TUI to function:

| Command | Description |
|---------|-------------|
| `/feature FEATURE_NAME=<name>` | Creates feature file, updates STATUS.md, starts development flow |
| `/review TARGET=<path>` | Runs full code review, routes findings to correct agents |
| `/maintenance` | Dependency audit + safe updates + code quality |
| `/ship FEATURE_NAME=<name>` | Completes feature: tests → docs → version bump |
| `/dod FEATURE_NAME=<name>` | Checks Definition of Done before shipping |
| `/status` | Shows current project state from STATUS.md |
| `/build-from-screenshot` | Implement UI from visual reference (attach image first) |
| `/security-audit` | Full OWASP Top 10 audit — read-only, full project |
| `/compact` | Reduces context window by summarizing and removing history |
| `/summary` | Outputs current state summary before compaction |
| `/recover` | Recovers context after compaction |
| Tests | pytest, pytest-asyncio, httpx |
| Deployment | Docker (slim/slim multi-stage, non-root, read-only FS) |

---

## Wichtige Konventionen

### Backend

- **Einzige Modell-Quelle:** `app/models/schemas.py` enthält alle Pydantic-Schemas.
  Niemals Router-lokale Modelle erstellen.

- **Pydantic v2:** `model_config = ConfigDict(...)` statt innerer `class Config`.
  `SettingsConfigDict` in `config.py`. `model_dump()` statt `.dict()`.

- **Geteilte Helpers:** `app/utils.py` für Funktionen, die in mehreren Routern benötigt werden
  (z.B. `get_user_id(request)`).

- **Session-Pattern:** `with SessionLocal() as db:` in Services.
  Der FastAPI `get_db()`-Generator in `db/database.py` ist für Router-Dependency-Injection.

- **Fehlerbehandlung:** Generische HTTP-Fehlermeldungen an den Client (`HTTPException`),
  vollständige Details nur server-seitig per `logger.error()`. Niemals `str(e)` im HTTP-Response.

- **Logging:** `logging.getLogger(__name__)` in jeder Datei.
  Konfiguration via `app/logging_config.py` und `logging.config.dictConfig(LOGGING)` in `main.py`.

- **Datetime:** Immer `datetime.now(timezone.utc)` — niemals `datetime.utcnow()` (deprecated).

- **Sprachen:** `app/models/schemas.py` enthält `DEEPL_TARGET_LANGUAGES` und
  `DEEPL_SOURCE_LANGUAGES` als einzige Quelle der Wahrheit für unterstützte Sprachen.

### Frontend

- **Keine Frameworks:** Reines Vanilla JS in `static/js/app.js`.
  State im `App`-Objekt. DOM-Manipulation direkt per `getElementById`.

- **Kein doppelter API-Call:** Spracherkennung kommt aus dem ersten `/api/translate`-Response.
  Kein zweiter Request zur Spracherkennung.

- **Fehlermeldungen:** `App.showError()` zeigt einen Toast (kein `alert()`).

- **CSS:** Alle Farben als CSS Custom Properties in `templates/index.html` (`--bg`, `--surface`, etc.).
  Dark Mode via `[data-theme="dark"]`-Selektor auf `<html>`. Tailwind-Utilities
  können in `static/css/input.css` ergänzt werden.

- **Tastaturkürzel:** Ausschließlich in `static/js/keyboard-shortcuts.js`.
  `app.js` hat nur inline `Ctrl+Enter`-Handler für Textareas.

- **Zahlenformatierung:** `Intl.NumberFormat('de-DE')` statt manueller Regex.

### CSS-Build

```bash
npm run build:css   # input.css → styles.css (minified)
npm run watch:css   # Watch-Modus für Entwicklung
```

`static/css/styles.css` wird generiert — niemals manuell bearbeiten.

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/` | Single-Page-App (HTML) |
| GET | `/health` | Liveness-Probe |
| GET | `/health/ready` | Readiness-Probe (DB + DeepL) |
| POST | `/api/translate` | Text übersetzen (DeepL oder LLM) |
| POST | `/api/translate/stream` | Text übersetzen (SSE-Stream) |
| POST | `/api/write` | Text optimieren (Doppel-Übersetzung) |
| POST | `/api/write/stream` | Text optimieren (SSE-Stream) |
| POST | `/api/detect-lang` | Spracherkennung |
| GET | `/api/config` | DeepL/LLM-Konfigurationsstatus |
| GET | `/api/usage` | Nutzungsstatistiken (lokal + DeepL) |
| GET | `/api/usage/summary` | Kumulative Statistiken (4 Wochen) |
| POST | `/api/auth/login` | Login (Session-Cookie) |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/history` | Session-Historie abrufen |
| POST | `/api/history` | History-Record anlegen |
| DELETE | `/api/history/{id}` | History-Record löschen |
| GET | `/api/admin/users` | Alle Benutzer (Admin) |
| POST | `/api/admin/users` | Benutzer anlegen (Admin) |
| PATCH | `/api/admin/users/{id}` | Benutzer aktualisieren (Admin) |
| DELETE | `/api/admin/users/{id}` | Benutzer löschen (Admin) |
| PATCH | `/api/admin/users/{id}/deactivate` | Benutzer deaktivieren (Admin) |
| POST | `/api/admin/users/{id}/reset-password` | Passwort zurücksetzen (Admin) |
| GET | `/docs` | Swagger UI (FastAPI auto-generated) |

---

## Authentifizierung (drei Modi, automatisch erkannt)

1. **OIDC** — wenn `OIDC_DISCOVERY_URL` gesetzt: Bearer-Token-Validierung via JWKS
2. **HTTP Basic Auth** — wenn `AUTH_USERNAME` + `AUTH_PASSWORD` gesetzt, kein OIDC
3. **Anonym** — kein Auth konfiguriert (für Heimnetz/VPN-Einsatz)

Exempt von Auth: `/health`, `/static/`, `/favicon`

---

## Umgebungsvariablen (`.env`)

| Variable | Pflicht | Default | Beschreibung |
|---|---|---|---|
| `DEEPL_API_KEY` | Nein | — | DeepL API Key; ohne Key → Mock-Modus |
| `SECRET_KEY` | Nein | zufällig | Session-Signing-Key |
| `DATABASE_URL` | Nein | `sqlite:///./data/senten.db` | SQLAlchemy DB-URL |
| `MONTHLY_CHAR_LIMIT` | Nein | `500000` | Monatliches Zeichenbudget |
| `ALLOWED_ORIGINS` | Nein | `` (leer) | CORS-Origins, kommagetrennt |
| `OIDC_DISCOVERY_URL` | Nein | — | OIDC Discovery-URL (aktiviert OIDC-Modus) |
| `OIDC_CLIENT_ID` | Nein | — | OIDC Client-ID |
| `OIDC_CLIENT_SECRET` | Nein | — | OIDC Client-Secret |
| `AUTH_USERNAME` | Nein | — | HTTP-Basic-Auth Benutzername |
| `AUTH_PASSWORD` | Nein | — | HTTP-Basic-Auth Passwort |
| `LOG_DIR` | Nein | `data` | Verzeichnis für Log-Dateien |
| `ALLOW_ANONYMOUS` | Nein | `true` | Anonymer Zugriff erlauben (ohne Login) |
| `SESSION_LIFETIME_HOURS` | Nein | `168` | Session-Lebensdauer in Stunden (7 Tage) |
| `LLM_PROVIDER` | Nein | — | LLM-Anbieter: `openai`, `anthropic`, `ollama`, `openai-compatible` |
| `LLM_API_KEY` | Nein | — | API-Key für LLM (optional bei Ollama) |
| `LLM_BASE_URL` | Nein | — | Base-URL für Ollama/openai-compatible |
| `LLM_TRANSLATE_MODEL` | Nein | `gpt-4o` | Modell für Übersetzung |
| `LLM_WRITE_MODEL` | Nein | `gpt-4o` | Modell für Schreiboptimierung |
| `LLM_DISPLAY_NAME` | Nein | `""` | UI-Label im Engine-Toggle |
| `LLM_TIMEOUT` | Nein | `30` | Timeout in Sekunden |
| `LLM_MAX_INPUT_CHARS` | Nein | `5000` | Zeichenlimit für LLM-Input (Cost-Guard) |

---

## Tests ausführen

```bash
# Alle Tests (Mock-Modus: DEEPL_API_KEY muss leer oder nicht gesetzt sein)
pytest

# Mit Coverage
pytest --cov=app --cov-report=term-missing

# Einzelne Testdatei
pytest tests/test_translate.py -v
```

Tests verwenden eine In-Memory-SQLite-Datenbank (konfiguriert in `tests/conftest.py`).
Kein echter DeepL-Key erforderlich — DeepLService läuft im Mock-Modus wenn
`DEEPL_API_KEY` leer ist.

---

## Lokale Entwicklung

```bash
# Python-Abhängigkeiten installieren
pip install -r requirements.txt

# CSS bauen
npm install && npm run build:css

# Server starten (Hot-Reload)
uvicorn app.main:app --reload

# Datenbank wird beim Start automatisch initialisiert (init_db() in lifespan)
```

---

## Docker

```bash
# Bauen und starten
docker compose up --build

# Nur starten (Image bereits gebaut)
docker compose up -d

# Logs
docker compose logs -f

# Stoppen
docker compose down
```

Schreibbare Verzeichnisse im Container (read-only FS):
- `/app/data` — SQLite-Datenbank + Logs (Volume)
- `/tmp` — uvicorn/Python Runtime-Temp

---

## DeepL-Service Details

- **Mock-Modus:** Aktiv wenn `DEEPL_API_KEY` nicht gesetzt oder ungültig.
  Alle Antworten sind Platzhalter (`[Mock DE] ...`, `[Optimiert Mock] ...`).
- **Übersetzung:** `deepl_service.translate()` — ein API-Call.
- **Optimierung:** `deepl_service.write_optimize()` — **zwei** API-Calls
  (Hin-Übersetzung zur Zwischensprache, Rück-Übersetzung zur Quellsprache).
  Spracherkennung wird aus dem ersten Ergebnis gewonnen (kein separater Detect-Call).
- **Usage:** `usage.character.count` und `usage.character.limit` (DeepL SDK v1.17 Objektstruktur).
