# API-Referenz — Senten

Basis-URL: `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`

Alle Request- und Response-Bodies sind JSON (`Content-Type: application/json`).

---

## Endpunkte

### GET /health

Liveness-Probe. Gibt immer `200 OK` zurück (solange der Prozess läuft).

**Response:**
```json
{"status": "ok"}
```

---

### GET /health/ready

Readiness-Probe. Prüft DB-Verbindung und DeepL-Service-Zustand bevor der Container als "ready" gilt.

**Response:**
```json
{"status": "ready", "checks": {"database": "ok", "deepl": "ok"}}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `status` | string | `"ready"` wenn alle Checks OK, sonst `"not_ready"` |
| `checks.database` | string | `"ok"` wenn DB erreichbar |
| `checks.deepl` | string | `"ok"` wenn DeepL konfiguriert (oder Mock-Modus) |

**Hinweis:** `/health` (Liveness) und `/health/ready` (Readiness) haben unterschiedliche Zwecke:
- `/health` — Prozess läuft noch (für Kubernetes LivenessProbe)
- `/health/ready` — bereit für Traffic (für Kubernetes ReadinessProbe)

---

### GET /api/config

Gibt zurück, ob die DeepL API und/oder LLM konfiguriert und erreichbar ist.

**Response:**
```json
{
  "configured": true,
  "mock_mode": false,
  "error": null,
  "llm_configured": true,
  "llm_provider": "openai-compatible",
  "llm_translate_model": "gpt-4o",
  "llm_write_model": "gpt-4o",
  "llm_display_name": "LiteLLM",
  "llm_max_input_chars": 5000
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `configured` | bool | `true` wenn `DEEPL_API_KEY` gesetzt |
| `mock_mode` | bool | `true` wenn kein gültiger Key (Platzhalter-Antworten) |
| `error` | string\|null | Fehlermeldung falls API nicht erreichbar |
| `llm_configured` | bool | `true` wenn LLM-Anbieter konfiguriert (`LLM_PROVIDER` gesetzt) |
| `llm_provider` | string\|null | Aktueller LLM-Anbieter (`openai`, `anthropic`, `ollama`, `openai-compatible`) |
| `llm_translate_model` | string\|null | Modell für Übersetzung |
| `llm_write_model` | string\|null | Modell für Schreiboptimierung |
| `llm_display_name` | string\|null | UI-Label im Engine-Toggle; `null` wenn nicht gesetzt (dann wird `llm_provider` angezeigt) |
| `llm_max_input_chars` | int | Maximale Eingabelänge für LLM-Endpunkte (Kostenschutz); Default: 5000 |

---

### LLM_MAX_INPUT_CHARS Konfiguration

Maximale Eingabelänge für alle LLM-Endpunkte als Kostenschutz.

| Umgebungsvariable | Default | Beschreibung |
|---|---|---|
| `LLM_MAX_INPUT_CHARS` | `5000` | Hard Cap auf Eingabelänge (1–50000); wird auf Router-Ebene erzwungen |

**Validierung:** 
- Text > `LLM_MAX_INPUT_CHARS` → `400 Bad Request` mit Fehlermeldung
- Gilt für `/api/translate`, `/api/write`, `/api/translate/stream`, `/api/write/stream` (nur bei `engine=llm`)

---

### POST /api/translate

Text übersetzen.

**Request:**
```json
{
  "text": "Hello world",
  "target_lang": "DE",
  "source_lang": "EN",
  "formality": "default",
  "engine": "deepl"
}
```

| Feld | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| `text` | string | ja | Zu übersetzender Text (1–10.000 Zeichen) |
| `target_lang` | string | nein | Zielsprache (Standard: `DE`) |
| `source_lang` | string | nein | Quellsprache; leer = automatische Erkennung |
| `formality` | string | nein | `default`, `more`, `less` (Standard: `default`) |
| `engine` | string | nein | `deepl` oder `llm` (Standard: `deepl`) |

**Response `200 OK`:**
```json
{
  "translated_text": "Hallo Welt",
  "detected_source_lang": "EN",
  "characters_used": 11,
  "usage": {
    "input_tokens": 10,
    "output_tokens": 8,
    "total_tokens": 18
  }
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `translated_text` | string | Übersetzter Text |
| `detected_source_lang` | string\|null | Erkannte Quellsprache (nur bei Auto-Erkennung) |
| `characters_used` | int | Verbrauchte Zeichen (= Länge des Eingabetexts) |
| `usage` | object\|null | Token-Nutzung (nur bei `engine=llm`) |
| `usage.input_tokens` | int | Input-Token |
| `usage.output_tokens` | int | Output-Token |
| `usage.total_tokens` | int | Gesamt-Token |

**Fehler:**

| Status | Beschreibung |
|---|---|
| `400` | Text leer oder Validierungsfehler |
| `408` | LLM-Timeout — Provider hat nicht rechtzeitig geantwortet |
| `401` | LLM-Auth-Fehler — ungültiger oder fehlender API-Key |
| `422` | LLM-Modell nicht gefunden oder nicht verfügbar |
| `429` | LLM-Quota oder Rate-Limit überschritten |
| `503` | DeepL API nicht erreichbar (bei `engine=deepl`) |
| `503` | LLM nicht konfiguriert (bei `engine=llm` aber `LLM_PROVIDER` nicht gesetzt) |
| `503` | LLM-Provider nicht erreichbar (Verbindungsfehler) |

---

### POST /api/write

Text stilistisch optimieren via Doppel-Übersetzung (Hin + Zurück).  
Verwendet **2 DeepL API-Calls** pro Request.

**Request:**
```json
{
  "text": "Das ist ein einfacher Text.",
  "target_lang": "DE",
  "formality": "default",
  "engine": "deepl"
}
```

| Feld | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| `text` | string | ja | Zu optimierender Text (1–10.000 Zeichen) |
| `target_lang` | string | nein | Zielsprache für Optimierung (Standard: `DE`) |
| `formality` | string | nein | `default`, `more`, `less` (Standard: `default`) |
| `engine` | string | nein | `deepl` oder `llm` (Standard: `deepl`) |

**Response `200 OK`:**
```json
{
  "optimized_text": "Das ist ein einfacher Text.",
  "characters_used": 52,
  "usage": {
    "input_tokens": 25,
    "output_tokens": 30,
    "total_tokens": 55
  }
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `optimized_text` | string | Optimierter Text |
| `characters_used` | int | Verbrauchte Zeichen (~2× Eingabelänge wegen Doppel-Übersetzung) |
| `usage` | object\|null | Token-Nutzung (nur bei `engine=llm`) |
| `usage.input_tokens` | int | Input-Token |
| `usage.output_tokens` | int | Output-Token |
| `usage.total_tokens` | int | Gesamt-Token |

**Fehler:**

| Status | Beschreibung |
|---|---|
| `400` | Text leer oder Validierungsfehler |
| `408` | LLM-Timeout — Provider hat nicht rechtzeitig geantwortet |
| `401` | LLM-Auth-Fehler — ungültiger oder fehlender API-Key |
| `422` | LLM-Modell nicht gefunden oder nicht verfügbar |
| `429` | LLM-Quota oder Rate-Limit überschritten |
| `503` | DeepL API nicht erreichbar (bei `engine=deepl`) |
| `503` | LLM nicht konfiguriert (bei `engine=llm` aber `LLM_PROVIDER` nicht gesetzt) |
| `503` | LLM-Provider nicht erreichbar (Verbindungsfehler) |

---

### POST /api/translate/stream

Übersetzung als SSE-Stream (Server-Sent Events). **Nur verfügbar wenn `engine="llm"`.**

Der Response ist kein JSON, sondern ein kontinuierlicher Event-Stream (`text/event-stream`).
Jedes Event hat das Format `data: <json>\n\n`.

**Request:**
```json
{
  "text": "Hello world",
  "target_lang": "DE",
  "source_lang": "EN",
  "formality": "default",
  "engine": "llm"
}
```

Gleiche Felder wie `POST /api/translate` — `engine` muss `"llm"` sein.

**Response-Header:**
```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

**SSE-Events (in Reihenfolge):**

| Event | Format | Beschreibung |
|---|---|---|
| Chunk | `data: {"chunk": "<text>"}` | Inkrementelles Übersetzungsfragment |
| Abschluss | `data: {"done": true, "detected_source_lang": "<code>"}` | Letztes Event; enthält erkannte Quellsprache |
| Fehler | `data: {"error": "<message>"}` | Fehler während des Streams; Stream endet danach |

**Beispiel-Stream:**
```
data: {"chunk": "Hallo"}

data: {"chunk": " Welt"}

data: {"done": true, "detected_source_lang": "EN"}
```

**Fehler (vor Stream-Start, als HTTP-Status):**

| Status | Beschreibung |
|---|---|
| `400` | Text leer, Validierungsfehler, oder `engine != "llm"` |
| `503` | LLM nicht konfiguriert (`LLM_PROVIDER` nicht gesetzt) |

**Rate Limit:** 30 Requests/Minute (identisch zu `/api/translate`).  
**Auth:** Geschützt durch AuthMiddleware (identisch zu allen anderen Endpunkten).

---

### POST /api/write/stream

Schreiboptimierung als SSE-Stream (Server-Sent Events). **Nur verfügbar wenn `engine="llm"`.**

Gleiche Streaming-Mechanik wie `POST /api/translate/stream`.

**Request:**
```json
{
  "text": "Das ist ein einfacher Text.",
  "target_lang": "DE",
  "formality": "default",
  "engine": "llm"
}
```

Gleiche Felder wie `POST /api/write` — `engine` muss `"llm"` sein.

**Response-Header:**
```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

**SSE-Events (in Reihenfolge):**

| Event | Format | Beschreibung |
|---|---|---|
| Chunk | `data: {"chunk": "<text>"}` | Inkrementelles Optimierungsfragment |
| Abschluss | `data: {"done": true}` | Letztes Event (kein `detected_source_lang`) |
| Fehler | `data: {"error": "<message>"}` | Fehler während des Streams; Stream endet danach |

**Beispiel-Stream:**
```
data: {"chunk": "Das ist ein"}

data: {"chunk": " prägnanter Text."}

data: {"done": true}
```

**Fehler (vor Stream-Start, als HTTP-Status):**

| Status | Beschreibung |
|---|---|
| `400` | Text leer, Validierungsfehler, oder `engine != "llm"` |
| `503` | LLM nicht konfiguriert (`LLM_PROVIDER` nicht gesetzt) |

**Rate Limit:** 30 Requests/Minute (identisch zu `/api/write`).  
**Auth:** Geschützt durch AuthMiddleware (identisch zu allen anderen Endpunkten).

---

### GET /api/usage

Nutzungsstatistiken (lokal aus SQLite + DeepL API-Kontingent).

**Response `200 OK`:**
```json
{
  "daily_translate": 1200,
  "daily_write": 800,
  "daily_total": 2000,
  "monthly_translate": 45000,
  "monthly_write": 30000,
  "monthly_total": 75000,
  "monthly_limit": 500000,
  "remaining": 425000,
  "percent_used": 15.0,
  "deepl_character_count": 75000,
  "deepl_character_limit": 500000
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `daily_translate` | int | Übersetzte Zeichen heute |
| `daily_write` | int | Optimierte Zeichen heute |
| `daily_total` | int | Gesamte Zeichen heute |
| `monthly_translate` | int | Übersetzte Zeichen diesen Monat |
| `monthly_write` | int | Optimierte Zeichen diesen Monat |
| `monthly_total` | int | Gesamte Zeichen diesen Monat |
| `monthly_limit` | int | Konfiguriertes Monatsbudget (`MONTHLY_CHAR_LIMIT`) |
| `remaining` | int | Verbleibende Zeichen (lokal) |
| `percent_used` | float | Prozent des Monatsbudgets verbraucht |
| `deepl_character_count` | int\|null | Verbrauch laut DeepL API (null im Mock-Modus) |
| `deepl_character_limit` | int\|null | Limit laut DeepL API (null im Mock-Modus) |

---

## Unterstützte Sprachen

### Zielsprachen (`target_lang`)

| Code | Sprache |
|---|---|
| `AR` | Arabisch |
| `BG` | Bulgarisch |
| `CS` | Tschechisch |
| `DA` | Dänisch |
| `DE` | Deutsch |
| `EL` | Griechisch |
| `EN-GB` | Englisch (UK) |
| `EN-US` | Englisch (US) |
| `ES` | Spanisch |
| `ET` | Estnisch |
| `FI` | Finnisch |
| `FR` | Französisch |
| `HU` | Ungarisch |
| `ID` | Indonesisch |
| `IT` | Italienisch |
| `JA` | Japanisch |
| `KO` | Koreanisch |
| `LT` | Litauisch |
| `LV` | Lettisch |
| `NB` | Norwegisch |
| `NL` | Niederländisch |
| `PL` | Polnisch |
| `PT-BR` | Portugiesisch (Brasilien) |
| `PT-PT` | Portugiesisch (Portugal) |
| `RO` | Rumänisch |
| `RU` | Russisch |
| `SK` | Slowakisch |
| `SL` | Slowenisch |
| `SV` | Schwedisch |
| `TR` | Türkisch |
| `UK` | Ukrainisch |
| `ZH` | Chinesisch (vereinfacht) |
| `ZH-HANS` | Chinesisch (vereinfacht) |
| `ZH-HANT` | Chinesisch (traditionell) |

### Quellsprachen (`source_lang`)

Alle obigen Codes ohne die regionalen Varianten (`EN` statt `EN-GB`/`EN-US`,
`PT` statt `PT-BR`/`PT-PT`, `ZH` statt `ZH-HANS`/`ZH-HANT`).
Leer lassen für automatische Spracherkennung.

---

## Authentifizierung

Drei Modi — automatisch erkannt:

| Modus | Header |
|---|---|
| OIDC | `Authorization: Bearer <token>` |
| HTTP Basic Auth | `Authorization: Basic <base64(user:pass)>` |
| Anonym | kein Header erforderlich |

Exempt von Auth: `GET /health`, `/static/*`, `/favicon*`

---

## Fehlerformat

Alle Fehler folgen dem FastAPI-Standard:

```json
{
  "detail": "Beschreibung des Fehlers"
}
```

Interne Details (Stack Traces, DeepL-Fehlercodes) werden nur server-seitig geloggt,
nie an den Client übertragen.
