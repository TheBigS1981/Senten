# Feature: LLM Erweiterung

> Created: 2026-02-25 | Status: Done

## Problem Statement
Nutzer sind auf die DeepL API beschränkt — weder für Übersetzungen noch für Textoptimierung gibt es eine Alternative, wenn DeepL nicht verfügbar, zu teuer oder für den Anwendungsfall ungeeignet ist. Self-Hoster wollen oft lokale LLMs (Ollama) oder bereits bezahlte Cloud-APIs (OpenAI, Anthropic) nutzen können.

## Goal
Nutzer können in jedem Tab (Übersetzen, Optimieren) per Toggle zwischen DeepL und einem konfigurierten LLM wechseln — der Schalter erscheint nur, wenn ein LLM konfiguriert ist.

## User Stories
1. Als **Nutzer** möchte ich **im Übersetzen-Tab zwischen DeepL und LLM umschalten**, damit **ich je nach Aufgabe die bessere Engine nutzen kann**.
2. Als **Nutzer** möchte ich **im Optimieren-Tab zwischen DeepL und LLM umschalten**, damit **ich Texte auch ohne DeepL-API stilistisch verbessern kann**.
3. Als **Admin** möchte ich **den LLM-Anbieter, das Modell und den System-Prompt per `.env` konfigurieren**, damit **Nutzer keine API-Keys sehen oder eingeben müssen**.
4. Als **Nutzer** möchte ich **den aktiven Anbieter und das Modell im Toggle sehen**, damit **ich weiß, welche Engine gerade aktiv ist**.

## Acceptance Criteria
- [x] Toggle erscheint in Translate-Tab und Write-Tab nur wenn `llm_configured: true` in `/api/config`
- [x] Toggle-Zustand ist pro Tab unabhängig (ein Tab kann DeepL, der andere LLM verwenden)
- [x] Übersetzen mit LLM liefert ein korrektes Ergebnis (Text + erkannte Quellsprache)
- [x] Optimieren mit LLM liefert ein korrektes Ergebnis
- [x] OpenAI, Anthropic und Ollama funktionieren als Provider
- [x] Ollama funktioniert ohne API-Key (optionaler Key für gesicherte Ollama-Instanzen)
- [x] System-Prompts sind intern in `app/config.py` definiert (nicht via `.env` konfigurierbar)
- [x] `/api/config` gibt `llm_configured`, `llm_provider`, `llm_translate_model`, `llm_write_model` zurück
- [x] Formality-Option wird ausgeblendet wenn LLM-Modus aktiv (keine Formality-UI vorhanden, wird null gesendet)
- [x] Fehler (kein API-Key, Timeout, Modell nicht verfügbar) zeigen benutzerfreundliche Fehlermeldung
- [x] Kein Breaking Change: Default `engine=deepl` — bestehende Nutzung unverändert

## Scope
### In scope
- OpenAI, Anthropic, Ollama als Provider
- Übersetzen + Optimieren mit LLM
- Pro-Tab-Toggle (unabhängig)
- Konfiguration via `.env` (Provider, API-Key, Modell, Base-URL, Prompts)
- Mock-Modus wenn kein LLM konfiguriert (kein Fehler, Toggle ausgeblendet)
- SSE-Streaming für inkrementelle Ausgabe (v2.4.0)

### Out of scope
- Modell-Auswahl im UI
- LLM-History getrennt von DeepL-History
- Formality-Kontrolle für LLM
- Mehrere gleichzeitig konfigurierte Provider

## UI / Visual Reference
```
Translate-Tab Toolbar (wenn llm_configured):
┌──────────────────────────────────────────────────────┐
│ [Übersetzen] [Optimieren] [DeepL ●──○ LLM]           │
│                            OpenAI · gpt-4o            │
└──────────────────────────────────────────────────────┘

Write-Tab Toolbar (unabhängiger Toggle):
┌──────────────────────────────────────────────────────┐
│ [Optimieren] [Übersetzen] [DeepL ○──● LLM]           │
│                            Ollama · llama3.2          │
└──────────────────────────────────────────────────────┘
```

## Technical Notes
**Affected modules:**
- `app/config.py` — 7 neue Settings
- `app/models/schemas.py` — `engine` Feld zu TranslateRequest + WriteRequest
- `app/services/llm_service.py` — **neu**
- `app/routers/translate.py` — Engine-Routing
- `templates/index.html` — Toggle-HTML
- `static/js/app.js` — Toggle-State + engine-Parameter

**New dependencies needed:**
- `openai>=1.0`
- `anthropic>=0.30`
- `httpx>=0.27` (für Ollama REST)

**Database changes:** NONE
**API changes:** `/api/config` + optionales `engine` Feld in bestehenden Requests (non-breaking)
**Breaking changes:** NO

## New Env Variables
```env
# LLM Provider: openai | anthropic | ollama
LLM_PROVIDER=openai
# API-Key (für OpenAI / Anthropic; bei Ollama optional)
LLM_API_KEY=sk-...
# Modell-Namen
LLM_TRANSLATE_MODEL=gpt-4o
LLM_WRITE_MODEL=gpt-4o
# Nur für Ollama: Base-URL
LLM_BASE_URL=http://localhost:11434
```

## Definition of Done
- [x] All acceptance criteria pass
- [x] Unit tests für LLMService (alle 3 Provider gemockt)
- [x] Integration-Tests für /api/translate?engine=llm + /api/write?engine=llm
- [x] Code review passed (no CRITICAL/HIGH findings) — @code-simplifier hat Vereinfachungen vorgenommen
- [x] CHANGELOG entry written (v2.3.1)
- [x] Manually verified (Tests bestehen, Code vereinfacht)

## Post-Ship Improvements (2026-02-25)

### openai-compatible Provider + Timeout + Fehlerbehandlung

**Scope:**
- Neuer Provider `openai-compatible` für LiteLLM und andere OpenAI-kompatible Proxys
- Timeout für alle Provider konfigurierbar via `LLM_TIMEOUT` (Default: 30s)
- Spezifische Fehlerklassen pro Fehlertyp (Timeout, Auth, Quota, Modell, Verbindung)
- HTTP-Status-Codes differenziert: 408 Timeout / 401 Auth / 429 Quota / 422 Modell / 503 Verbindung
- `LLM_DISPLAY_NAME` für benutzerdefiniertes UI-Label im Engine-Toggle

**Acceptance Criteria:**
- [x] `LLM_PROVIDER=openai-compatible` + `LLM_BASE_URL` aktiviert Proxy-Modus
- [x] API-Key ist optional für openai-compatible (kein Key = `"no-key"` Fallback)
- [x] Fehlt `LLM_BASE_URL` bei openai-compatible → LLM deaktiviert mit Warning
- [x] Timeout löst 408 aus mit verständlicher Fehlermeldung
- [x] Auth-Fehler löst 401 aus mit Hinweis auf LLM_API_KEY
- [x] Quota/Rate-Limit löst 429 aus mit Hinweis auf Kontingent
- [x] Modell nicht gefunden löst 422 aus mit Hinweis auf LLM_TRANSLATE_MODEL
- [x] Verbindungsfehler löst 503 aus mit Hinweis auf LLM_BASE_URL
- [x] `LLM_DISPLAY_NAME` erscheint im Toggle statt Provider-Name
- [x] Alle 144 Tests bestehen (24 neue Tests)

## Decisions Made
- [2026-02-25] Toggle pro Tab unabhängig — Nutzer kann unterschiedliche Engines pro Aufgabe wählen
- [2026-02-25] Ollama API-Key optional — `LLM_API_KEY` leer lassen erlaubt, Key möglich für gesicherte Instanzen
- [2026-02-25] System-Prompt in `app/config.py` als Default — nicht via `.env` überschreibbar (Pydantic lädt die Werte nicht)
- [2026-02-25] Drei Provider: OpenAI, Anthropic, Ollama — abstrakte Provider-Klasse für Erweiterbarkeit
- [2026-02-25] Kein Streaming in v1 — zu komplex, kann später nachgerüstet werden
- [2026-02-25] `openai-compatible` als eigener Provider-Typ — semantisch klar, API-Key optional, eigene Fehlermeldung wenn BASE_URL fehlt
- [2026-02-25] Custom Exception-Hierarchie in llm_service.py — provider-agnostisch, Router mappt auf HTTP-Status

## Progress Log
- [2026-02-25] Post-ship: openai-compatible Provider, Timeout, spezifische Fehlerbehandlung — 144 Tests grün
- [2026-02-25] Feature-Datei angelegt, Plan finalisiert, Implementierung gestartet

## Open Questions
NONE
