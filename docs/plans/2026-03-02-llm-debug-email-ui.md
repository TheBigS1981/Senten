# LLM Debug Panel + E-Mail-Feld in Admin-UI — Implementierungsplan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** (1) Admin-only Debug-Toggle in Translate- und Write-Tab zeigt Raw-Prompt, Raw-Response und Diff nach `_strip_markdown()`. (2) E-Mail-Feld im "Benutzer anlegen"-Dialog und editierbar in der Benutzerliste.

**Architecture:**
- Backend: Neuer Admin-Endpunkt `POST /api/admin/debug/llm` — nimmt denselben Body wie `/api/translate`/`/api/write`, ruft LLM nicht-streaming auf, gibt Debug-Paket zurück.
- Frontend (Debug): Toggle-Button nur für Admins sichtbar (`App.currentUser.is_admin`). Nach jedem LLM-Call wird `debug_info` im App-State gespeichert. Beim Aktivieren des Toggles rendert ein `<details>`-Panel unter dem Output.
- Frontend (E-Mail): Input im "Benutzer anlegen"-Modal + Edit-Icon in jeder User-Card öffnet ein kleines Edit-Modal für E-Mail.

**Tech Stack:** FastAPI, Vanilla JS, Jinja2, Tailwind CSS (existing patterns only)

---

## Task 1: Backend — Debug-Endpunkt

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `app/models/schemas.py`
- Modify: `app/services/llm_service.py`

### Schritt 1: Schema für Debug-Request und -Response in `schemas.py` ergänzen

Am Ende von `app/models/schemas.py` hinzufügen:

```python
class LLMDebugRequest(BaseModel):
    mode: Literal["translate", "write"]
    text: str = Field(..., min_length=1, max_length=10000)
    target_lang: str = Field(default="DE")
    source_lang: Optional[str] = Field(default=None)

    model_config = ConfigDict(str_strip_whitespace=True)


class LLMDebugResponse(BaseModel):
    mode: str
    provider: str
    model: str
    system_prompt: str
    user_content: str
    raw_response: str
    processed_response: str
    strip_markdown_changed: bool
    detected_source_lang: Optional[str]
    usage: dict[str, int]
```

### Schritt 2: `llm_service.py` — Debug-Methode ergänzen

In `LLMService` nach `write_optimize()` eine neue Methode einfügen:

```python
async def debug_call(
    self,
    mode: str,
    text: str,
    target_lang: str,
    source_lang: Optional[str] = None,
) -> dict:
    """Debug-Aufruf: Gibt Prompt, Raw-Response und verarbeitete Response zurück.

    Verwendet immer non-streaming complete(), nie stream.
    """
    if not self._translate_provider:
        raise ValueError("LLM ist nicht konfiguriert.")

    lang_label = _lang_name(target_lang)

    if mode == "translate":
        provider = self._translate_provider
        model = self._translate_model

        if source_lang:
            system_prompt = self._translate_prompt_template.format(
                target_lang=lang_label
            )
            user_content = text
        else:
            system_prompt = (
                "You are a professional translator. "
                f"Translate the following text to {lang_label}. "
                "Respond with JSON only, no other text: "
                '{"detected_lang": "<2-letter ISO code>", "translation": "<translated text>"}'
            )
            user_content = text

        response = await provider.complete(system_prompt, user_content)
        raw = response.text
        processed = _strip_markdown(raw.strip())
        detected = source_lang

        # Try to extract translation from JSON for processed field
        if not source_lang:
            import re as _re
            try:
                import json as _json
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = _re.sub(r"^```(?:json)?\s*", "", cleaned)
                    cleaned = _re.sub(r"\s*```\s*$", "", cleaned)
                result_json = _json.loads(cleaned)
                detected = self._normalize_lang_code(
                    result_json.get("detected_lang", "")
                )
                processed = _strip_markdown(result_json.get("translation", "").strip())
            except Exception:
                pass

    else:  # write
        provider = self._write_provider
        model = self._write_model
        system_prompt = self._write_prompt_template.format(target_lang=lang_label)
        user_content = text
        response = await provider.complete(system_prompt, user_content)
        raw = response.text
        processed = _strip_markdown(raw.strip())
        detected = None

    return {
        "mode": mode,
        "provider": self._provider_name,
        "model": model,
        "system_prompt": system_prompt,
        "user_content": user_content,
        "raw_response": raw,
        "processed_response": processed,
        "strip_markdown_changed": raw.strip() != processed,
        "detected_source_lang": detected,
        "usage": {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.total_tokens,
        },
    }
```

### Schritt 3: Endpunkt in `admin.py` ergänzen

Imports ergänzen: `LLMDebugRequest`, `LLMDebugResponse` aus schemas, `llm_service` aus llm_service.

Am Ende von `admin.py` hinzufügen:

```python
@router.post("/admin/debug/llm", tags=["Admin"])
async def debug_llm(
    body: LLMDebugRequest,
    senten_session: str = Cookie(default=None),
):
    """Debug-Endpunkt für LLM-Anfragen. Admin only.

    Gibt System-Prompt, User-Content, Raw-Response und verarbeitete Response zurück.
    Nie für produktive Übersetzungen verwenden — keine Usage-Aufzeichnung.
    """
    _require_admin(senten_session)

    if not llm_service.is_configured():
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM ist nicht konfiguriert.",
        )

    try:
        result = await llm_service.debug_call(
            mode=body.mode,
            text=body.text,
            target_lang=body.target_lang,
            source_lang=body.source_lang,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("LLM debug call failed: %s", exc)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="LLM-Anfrage fehlgeschlagen.",
        ) from exc

    return result
```

### Schritt 4: Tests schreiben

In `tests/test_admin.py` neue Klasse `TestDebugLlm` ergänzen:

```python
class TestDebugLlm:
    def test_non_admin_gets_401(self, client):
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "translate", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 401

    def test_regular_user_gets_403(self, regular_client):
        client, _ = regular_client
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "translate", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 403

    def test_admin_gets_503_when_llm_not_configured(self, admin_client):
        """LLM ist in Tests nicht konfiguriert — 503 erwartet."""
        client, _ = admin_client
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "translate", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 503

    def test_admin_gets_debug_response_with_mocked_llm(self, admin_client):
        from unittest.mock import AsyncMock, patch
        from app.services.llm_service import LLMResponse

        client, _ = admin_client
        mock_response = LLMResponse(
            text="Hallo Welt", input_tokens=10, output_tokens=5, total_tokens=15
        )
        with patch("app.routers.admin.llm_service.is_configured", return_value=True), \
             patch("app.routers.admin.llm_service.debug_call", new_callable=AsyncMock) as mock_debug:
            mock_debug.return_value = {
                "mode": "translate",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "system_prompt": "You are a translator...",
                "user_content": "Hello world",
                "raw_response": "Hallo Welt",
                "processed_response": "Hallo Welt",
                "strip_markdown_changed": False,
                "detected_source_lang": "EN",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
            res = client.post(
                "/api/admin/debug/llm",
                json={"mode": "translate", "text": "Hello world", "target_lang": "DE"},
            )
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "translate"
        assert "system_prompt" in data
        assert "raw_response" in data
        assert "processed_response" in data
        assert "strip_markdown_changed" in data
        assert "usage" in data

    def test_invalid_mode_returns_422(self, admin_client):
        client, _ = admin_client
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "invalid", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 422
```

### Schritt 5: Tests ausführen

```bash
python3 -m pytest tests/test_admin.py::TestDebugLlm -v
```

Erwartet: 5 Tests grün.

### Schritt 6: Commit

```bash
git add app/routers/admin.py app/models/schemas.py app/services/llm_service.py tests/test_admin.py
git commit -m "feat(admin): add POST /api/admin/debug/llm endpoint for LLM debugging"
```

---

## Task 2: Frontend — Debug-Toggle in Translate-Tab und Write-Tab

**Files:**
- Modify: `templates/index.html`
- Modify: `static/js/app.js`
- Modify: `static/css/input.css`

### Schritt 1: CSS für Debug-Panel in `static/css/input.css` ergänzen

Am Ende der Datei hinzufügen:

```css
/* ── LLM Debug Panel (Admin only) ── */
.debug-panel {
  @apply mt-3 rounded-lg border text-sm font-mono;
  background: var(--surface-alt);
  border-color: var(--border);
}
.debug-panel summary {
  @apply px-3 py-2 cursor-pointer font-sans font-medium select-none;
  color: var(--text-muted);
}
.debug-panel summary:hover { color: var(--text); }
.debug-panel .debug-section {
  @apply px-3 pb-3;
  border-top: 1px solid var(--border);
}
.debug-section h4 {
  @apply mt-2 mb-1 text-xs font-sans font-semibold uppercase tracking-wide;
  color: var(--text-sub);
}
.debug-section pre {
  @apply p-2 rounded text-xs overflow-x-auto whitespace-pre-wrap break-words;
  background: var(--surface);
  border: 1px solid var(--border);
  max-height: 200px;
  overflow-y: auto;
}
.debug-badge-changed {
  @apply inline-block px-1 rounded text-xs ml-1;
  background: var(--badge-warn-bg);
  color: var(--badge-warn-fg);
}
.debug-badge-same {
  @apply inline-block px-1 rounded text-xs ml-1;
  background: var(--surface);
  color: var(--text-muted);
}
```

Danach CSS neu bauen:

```bash
npm run build:css
```

### Schritt 2: HTML — Debug-Toggle-Button in beiden Toolbars ergänzen

**In `templates/index.html`**, in der Toolbar des Translate-Panels (nach `btn-clear-translate`), vor `</div><!-- toolbar-left -->`:

```html
<!-- Debug Toggle — nur für Admins, nur bei LLM aktiv (via JS gesteuert) -->
<button id="btn-debug-translate" class="btn btn-ghost admin-only llm-only"
        style="display:none" aria-label="LLM Debug-Informationen anzeigen"
        title="Debug: Prompt & Response anzeigen">
    <i class="fas fa-bug" aria-hidden="true"></i> Debug
</button>
```

**In der Toolbar des Write-Panels** (nach `btn-clear-write`):

```html
<button id="btn-debug-write" class="btn btn-ghost admin-only llm-only"
        style="display:none" aria-label="LLM Debug-Informationen anzeigen"
        title="Debug: Prompt & Response anzeigen">
    <i class="fas fa-bug" aria-hidden="true"></i> Debug
</button>
```

**Debug-Panel-Container** direkt nach dem Output-Bereich in beiden Panels einfügen (nach dem Stats-Bar `</div>` und vor der Toolbar):

Für Translate (nach `<div class="stats-bar ...">...</div>` des Translate-Panels):

```html
<!-- LLM Debug Panel — nur für Admins, nach LLM-Call befüllt -->
<div id="debug-panel-translate" style="display:none; margin: 0 var(--space-3) var(--space-2);">
    <details class="debug-panel">
        <summary>LLM Debug-Informationen</summary>
        <div class="debug-section">
            <h4>Provider / Modell</h4>
            <pre id="debug-translate-meta"></pre>
        </div>
        <div class="debug-section">
            <h4>System Prompt</h4>
            <pre id="debug-translate-system"></pre>
        </div>
        <div class="debug-section">
            <h4>User Content</h4>
            <pre id="debug-translate-user"></pre>
        </div>
        <div class="debug-section">
            <h4>Raw Response (vor _strip_markdown)</h4>
            <pre id="debug-translate-raw"></pre>
        </div>
        <div class="debug-section">
            <h4>Verarbeitete Response <span id="debug-translate-diff-badge"></span></h4>
            <pre id="debug-translate-processed"></pre>
        </div>
        <div class="debug-section">
            <h4>Token-Nutzung</h4>
            <pre id="debug-translate-usage"></pre>
        </div>
    </details>
</div>
```

Identisch für Write (IDs mit `-write` statt `-translate`):

```html
<div id="debug-panel-write" style="display:none; margin: 0 var(--space-3) var(--space-2);">
    <details class="debug-panel">
        <summary>LLM Debug-Informationen</summary>
        <div class="debug-section">
            <h4>Provider / Modell</h4>
            <pre id="debug-write-meta"></pre>
        </div>
        <div class="debug-section">
            <h4>System Prompt</h4>
            <pre id="debug-write-system"></pre>
        </div>
        <div class="debug-section">
            <h4>User Content</h4>
            <pre id="debug-write-user"></pre>
        </div>
        <div class="debug-section">
            <h4>Raw Response (vor _strip_markdown)</h4>
            <pre id="debug-write-raw"></pre>
        </div>
        <div class="debug-section">
            <h4>Verarbeitete Response <span id="debug-write-diff-badge"></span></h4>
            <pre id="debug-write-processed"></pre>
        </div>
        <div class="debug-section">
            <h4>Token-Nutzung</h4>
            <pre id="debug-write-usage"></pre>
        </div>
    </details>
</div>
```

### Schritt 3: JavaScript in `app.js` — Debug-State und Handler

**Im App-Objekt**, nach `currentUser: null,` ergänzen:

```js
_debugTranslate: null,  // letzte Debug-Daten für Translate-Tab
_debugWrite: null,      // letzte Debug-Daten für Write-Tab
```

**Neue Methode `_isAdmin()`** ergänzen (Hilfsmethode):

```js
_isAdmin() {
    return this.currentUser && this.currentUser.is_admin === true;
},
```

**Neue Methode `_updateDebugVisibility()`** — zeigt/versteckt Debug-Buttons je nach Admin + Engine:

```js
_updateDebugVisibility() {
    const isAdmin = this._isAdmin();
    const translateLLM = document.getElementById('translate-engine-checkbox')?.checked;
    const writeLLM = document.getElementById('write-engine-checkbox')?.checked;

    const btnT = document.getElementById('btn-debug-translate');
    const btnW = document.getElementById('btn-debug-write');
    if (btnT) btnT.style.display = (isAdmin && translateLLM) ? '' : 'none';
    if (btnW) btnW.style.display = (isAdmin && writeLLM) ? '' : 'none';
},
```

**Neue Methode `_renderDebugPanel(tab, data)`**:

```js
_renderDebugPanel(tab, data) {
    const panel = document.getElementById(`debug-panel-${tab}`);
    if (!panel || !data) return;

    const esc = s => String(s ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    document.getElementById(`debug-${tab}-meta`).textContent =
        `Provider: ${data.provider}\nModell:    ${data.model}` +
        (data.detected_source_lang ? `\nErkannte Sprache: ${data.detected_source_lang}` : '');
    document.getElementById(`debug-${tab}-system`).textContent = data.system_prompt;
    document.getElementById(`debug-${tab}-user`).textContent = data.user_content;
    document.getElementById(`debug-${tab}-raw`).textContent = data.raw_response;
    document.getElementById(`debug-${tab}-processed`).textContent = data.processed_response;

    const badge = document.getElementById(`debug-${tab}-diff-badge`);
    if (data.strip_markdown_changed) {
        badge.className = 'debug-badge-changed';
        badge.textContent = 'verändert';
    } else {
        badge.className = 'debug-badge-same';
        badge.textContent = 'unverändert';
    }

    const u = data.usage || {};
    document.getElementById(`debug-${tab}-usage`).textContent =
        `Input:  ${u.input_tokens ?? 0} Tokens\nOutput: ${u.output_tokens ?? 0} Tokens\nGesamt: ${u.total_tokens ?? 0} Tokens`;

    panel.style.display = '';
    // Auto-open the details element
    const details = panel.querySelector('details');
    if (details) details.open = true;
},
```

**Neue Methode `_fetchDebugInfo(tab)`** — ruft den Backend-Endpunkt auf:

```js
async _fetchDebugInfo(tab) {
    const text = tab === 'translate'
        ? document.getElementById('input-text-translate')?.value?.trim()
        : document.getElementById('input-text-write')?.value?.trim();
    if (!text) return;

    const isTranslate = tab === 'translate';
    const targetLang = isTranslate
        ? (document.querySelector('input[name="translate-target-lang"]:checked')?.value
           || document.getElementById('translate-target-lang-select')?.value || 'DE')
        : (document.querySelector('input[name="write-target-lang"]:checked')?.value
           || document.getElementById('write-target-lang-select')?.value || 'DE');

    const body = { mode: tab === 'translate' ? 'translate' : 'write', text, target_lang: targetLang };

    try {
        const res = await fetch('/api/admin/debug/llm', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            this.showError(err.detail || 'Debug-Anfrage fehlgeschlagen.');
            return;
        }
        const data = await res.json();
        if (tab === 'translate') this._debugTranslate = data;
        else this._debugWrite = data;
        this._renderDebugPanel(tab, data);
    } catch (e) {
        this.showError('Debug-Anfrage fehlgeschlagen.');
    }
},
```

**Im `_bindEvents()`**, Event-Listener für Debug-Buttons ergänzen:

```js
document.getElementById('btn-debug-translate')?.addEventListener('click', () => {
    this._fetchDebugInfo('translate');
});
document.getElementById('btn-debug-write')?.addEventListener('click', () => {
    this._fetchDebugInfo('write');
});
```

**`_updateDebugVisibility()` aufrufen** nach:
- `loadProfile()` (nach `this.currentUser = profile;`)
- `_initEngineToggles()` (wenn Engine-Checkbox sich ändert)
- `loadConfig()` (nach LLM-Konfiguration geladen)

**Debug-Panels verstecken beim Löschen** (`clearTranslate()` und `clearWrite()`):

```js
// in clearTranslate():
document.getElementById('debug-panel-translate').style.display = 'none';
this._debugTranslate = null;

// in clearWrite():
document.getElementById('debug-panel-write').style.display = 'none';
this._debugWrite = null;
```

### Schritt 4: Manuell testen

1. Als Admin einloggen
2. LLM-Engine aktivieren
3. Text eingeben, auf "Debug" klicken
4. Debug-Panel öffnet sich mit Prompt, Raw-Response, Processed-Response
5. Als normaler User: Debug-Button nicht sichtbar
6. DeepL-Engine: Debug-Button nicht sichtbar

### Schritt 5: CSS bauen und committen

```bash
npm run build:css
git add templates/index.html static/js/app.js static/css/input.css static/css/styles.css
git commit -m "feat(ui): add LLM debug panel for admins in translate and write tabs"
```

---

## Task 3: E-Mail-Feld im Admin-UI

**Files:**
- Modify: `templates/admin.html`
- Modify: `static/js/admin.js`

### Schritt 1: E-Mail-Feld im "Benutzer anlegen"-Modal ergänzen

In `templates/admin.html`, nach dem `display_name`-Feld und vor der Checkbox:

```html
<label>
    E-Mail (optional, für Gravatar)
    <input type="email" name="email" class="form-input"
           placeholder="user@example.com">
</label>
```

### Schritt 2: E-Mail im `form-create` Submit-Handler mitschicken

In `static/js/admin.js`, im Submit-Handler des `form-create`:

```js
// vorher:
const body = {
    username: fd.get('username'),
    password: fd.get('password'),
    display_name: fd.get('display_name') || null,
    is_admin: fd.has('is_admin'),
};

// nachher:
const body = {
    username: fd.get('username'),
    password: fd.get('password'),
    display_name: fd.get('display_name') || null,
    email: fd.get('email') || null,
    is_admin: fd.has('is_admin'),
};
```

### Schritt 3: E-Mail-Anzeige in der Benutzerliste + Edit-Modal

**In `_renderUsers()`**, in der `user-info`-Sektion nach dem Avatar, die E-Mail anzeigen (falls vorhanden):

```js
${u.email ? `<span class="user-email" title="${this._esc(u.email)}">${this._esc(u.email)}</span>` : ''}
```

**Edit-Button für E-Mail** in der `user-actions`-Sektion ergänzen (vor dem Deaktivieren-Button):

```js
<button class="btn btn-ghost btn-sm"
        data-action="edit-email"
        data-user-id="${this._esc(u.id)}"
        data-current-email="${this._esc(u.email || '')}">
    <i class="fas fa-at"></i> E-Mail
</button>
```

### Schritt 4: Edit-E-Mail-Handler im Event Delegation ergänzen

Im `_bindEvents()` Delegation-Handler:

```js
if (action === 'edit-email') Admin.editEmail(userId, btn.dataset.currentEmail);
```

**Neue Methode `editEmail()`**:

```js
async editEmail(id, currentEmail) {
    const email = prompt(`E-Mail-Adresse für diesen Benutzer (leer lassen für Gravatar via Benutzername):\n\nAktuell: ${currentEmail || '(keine)'}`, currentEmail || '');
    if (email === null) return; // Abgebrochen
    const res = await fetch(`/api/admin/users/${id}`, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() || null }),
    });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || 'Fehler beim Speichern der E-Mail.');
    }
    await this.loadUsers();
},
```

**Wichtig:** `AdminUserUpdateRequest` erlaubt `email: null` aktuell nicht (wegen `exclude_none=True`). Wir müssen im Backend das Email-Löschen ermöglichen. In `admin.py`:

```python
# Statt exclude_none=True:
updates = {k: v for k, v in body.model_dump().items() if v is not None or k == 'email'}
```

Und in `user_service.update_user()`:

```python
# Statt: if email is not None: user.email = email
# Neu: email explizit auf None setzen erlauben
if 'email' in kwargs or email is not None:
    user.email = email
```

Da `update_user` keyword-arguments benutzt, besser: Sentinel-Pattern. Einfacher Fix — `update_user` erhält ein explizites `UNSET`-Sentinel:

```python
_UNSET = object()

def update_user(self, user_id, ..., email=_UNSET):
    ...
    if email is not _UNSET:
        user.email = email
```

Und den Aufruf im Router anpassen: `body.model_dump()` (ohne `exclude_none`) filtern, aber `email` immer übergeben wenn es im Body ist:

```python
# In admin.py update_user endpoint:
raw = body.model_dump()
updates = {}
for k, v in raw.items():
    if k == 'email':
        updates['email'] = v  # Immer übergeben, auch wenn None
    elif v is not None:
        updates[k] = v
user = user_service.update_user(user_id, **updates)
```

### Schritt 5: CSS für `.user-email` ergänzen

In `templates/admin.html` im `<style>`-Block:

```css
.user-email {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
}
```

### Schritt 6: Tests ergänzen

In `tests/test_admin.py`, `TestUpdateEmail` erweitern um Email-Löschen:

```python
def test_email_can_be_set_to_null_via_api(self, admin_client):
    """Email kann auf null gesetzt werden (gravatar fällt auf username zurück)."""
    import hashlib
    client, svc = admin_client
    user = svc.create_user(
        username="null_email_test", password="pw12345678",
        email="remove@example.com"
    )
    res = client.put(
        f"/api/admin/users/{user.id}",
        json={"email": None},
    )
    assert res.status_code == 200
    # avatar_url soll jetzt den username-Hash enthalten
    expected_hash = hashlib.md5("null_email_test".encode()).hexdigest()
    assert expected_hash in res.json()["avatar_url"]
```

### Schritt 7: Tests ausführen

```bash
python3 -m pytest tests/test_admin.py -v
```

Erwartet: Alle Admin-Tests grün, inkl. neuer Email-Null-Test.

### Schritt 8: Commit

```bash
git add templates/admin.html static/js/admin.js app/routers/admin.py app/services/user_service.py tests/test_admin.py
git commit -m "feat(admin): add email field to create/edit user UI with gravatar support"
```

---

## Task 4: Gesamttest + Release

### Schritt 1: Vollständige Test-Suite

```bash
python3 -m pytest tests/ -q
```

Erwartet: Alle Tests grün (413+).

### Schritt 2: CSS-Build sicherstellen

```bash
npm run build:css
```

### Schritt 3: Version-Bump und Commit

- `app/config.py`: VERSION auf `"2.9.0"` (Minor-Bump — neue Features)
- `CHANGELOG.md`: Neuen Eintrag `[2.9.0]` anlegen

```bash
git add -A
git commit -m "chore: release v2.9.0"
git tag v2.9.0 && git push && git push --tags
```
