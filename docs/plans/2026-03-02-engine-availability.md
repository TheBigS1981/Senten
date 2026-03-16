# Engine Availability Handling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Zeige dem Nutzer klar, welche Engine(s) verfügbar sind — und blockiere die UI vollständig wenn gar keine Engine konfiguriert ist.

**Architecture:** Reine Frontend-Änderung. Das Backend liefert bereits alle nötigen Flags (`configured`, `mock_mode`, `llm_configured`) via `GET /api/config`. Die Logik wird in `_initEngineToggles()` (app.js) ausgebaut und durch ein neues Overlay in `index.html` ergänzt.

**Tech Stack:** Vanilla JS, Jinja2/HTML, CSS Custom Properties (kein Framework, kein Backend-Change)

---

## Übersicht der drei Fälle

| DeepL | LLM | Verhalten |
|-------|-----|-----------|
| ✅ | ✅ | Toggle frei bewegbar (unverändert) |
| ✅ | ❌ | Kein Toggle — Label `Engine: DeepL` |
| ❌ | ✅ | Kein Toggle — Label `Engine: <LLM-Name>` |
| ❌ | ❌ | Overlay blockiert die gesamte UI |

**Hinweis zu `configured` vs. `mock_mode`:** DeepL gilt als „nicht konfiguriert" wenn `mock_mode: true` (kein echter Key). Das Overlay erscheint auch im Mock-Modus wenn kein LLM vorhanden ist — das ist gewünscht.

---

## Task 1: CSS für Single-Engine-Label und No-Engine-Overlay

**Files:**
- Modify: `templates/index.html` (CSS-Block, ca. Zeile 654–705)

**Kontext:** Alle Styles leben inline im `<style>`-Block von `index.html`. Die bestehenden `.engine-toggle-*` Klassen bleiben unverändert — wir fügen neue Klassen hinzu.

**Step 1: CSS für Single-Engine-Label einfügen**

Füge direkt nach dem Block `.engine-info { ... }` (ca. Zeile 705) ein:

```css
/* ── Single-Engine Label (nur eine Engine konfiguriert, kein Switch) ── */
.engine-single-label {
    font-size: var(--text-sm);
    color: var(--text-muted);
    font-weight: var(--font-medium);
    white-space: nowrap;
}
```

**Step 2: CSS für No-Engine-Overlay einfügen**

Füge direkt danach ein (nach `.engine-single-label`):

```css
/* ── No-Engine Overlay (blockiert UI wenn weder DeepL noch LLM konfiguriert) ── */
#no-engine-overlay {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 10000;
    background: rgba(0, 0, 0, 0.6);
    align-items: center;
    justify-content: center;
}
#no-engine-overlay.visible {
    display: flex;
}
.no-engine-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    padding: var(--space-8);
    max-width: 420px;
    width: 90%;
    text-align: center;
    box-shadow: var(--shadow-lg);
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
}
.no-engine-icon {
    font-size: 2.5rem;
    color: var(--color-warning, #f59e0b);
}
.no-engine-title {
    font-size: var(--text-lg);
    font-weight: var(--font-semibold);
    color: var(--text);
}
.no-engine-body {
    font-size: var(--text-sm);
    color: var(--text-muted);
    line-height: 1.6;
}
.no-engine-hint {
    font-size: var(--text-xs);
    color: var(--text-weak);
    font-family: monospace;
    background: var(--surface-raised, var(--surface));
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-2) var(--space-3);
    text-align: left;
}
```

**Step 3: Visuell prüfen (kein Test nötig — reines CSS)**

Öffne `http://localhost:8000` — noch keine sichtbare Änderung erwartet (Overlay ist `display: none`).

**Step 4: Commit**

```bash
git add templates/index.html
git commit -m "style(engine): add CSS for single-engine label and no-engine overlay"
```

---

## Task 2: HTML-Struktur für das Overlay

**Files:**
- Modify: `templates/index.html` (direkt vor `</body>`, ca. letzte Zeilen)

**Kontext:** Das Overlay ist ein `<div>` außerhalb aller App-Strukturen, damit es alles überlagert. Es wird per JS via `.visible`-Klasse aktiviert.

**Step 1: Overlay-HTML einfügen**

Füge direkt vor dem letzten `</body>`-Tag ein:

```html
<!-- ── No-Engine Overlay ── -->
<div id="no-engine-overlay" role="alertdialog" aria-modal="true"
     aria-labelledby="no-engine-title" aria-describedby="no-engine-desc">
    <div class="no-engine-card">
        <div class="no-engine-icon" aria-hidden="true">
            <i class="fas fa-triangle-exclamation"></i>
        </div>
        <p class="no-engine-title" id="no-engine-title">Keine Engine konfiguriert</p>
        <p class="no-engine-body" id="no-engine-desc">
            Weder DeepL noch ein LLM ist eingerichtet.<br>
            Die App kann keine Übersetzungen durchführen.
        </p>
        <div class="no-engine-hint">
            DEEPL_API_KEY=&lt;dein-key&gt;<br>
            — oder —<br>
            LLM_PROVIDER=openai<br>
            LLM_API_KEY=&lt;dein-key&gt;
        </div>
    </div>
</div>
```

**Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat(engine): add no-engine overlay HTML structure"
```

---

## Task 3: JS — `_initEngineToggles()` für alle drei Fälle ausbauen

**Files:**
- Modify: `static/js/app.js` (Funktion `_initEngineToggles`, ca. Zeile 536–568)

**Kontext:**
- `this.state.config.configured` = `true` wenn DeepL echter Key vorhanden (nicht Mock)
- `this.state.config.mock_mode` = `true` wenn DeepL im Mock-Modus
- `this.state.config.llm_configured` = `true` wenn LLM konfiguriert
- DeepL gilt als "aktiv" wenn `configured && !mock_mode`
- Die bestehende `_initEngineToggles()`-Funktion wird erweitert — sie wird nur bei `llm_configured` aufgerufen (Zeile 385). Das ändern wir: sie wird immer aufgerufen.

**Step 1: `loadConfig()` anpassen — immer `_initEngineToggles()` aufrufen**

Aktuelle Stelle (ca. Zeile 384–388):
```js
// Show engine toggles if LLM is configured
if (this.state.config.llm_configured) {
    this._initEngineToggles();
    this._updateDebugVisibility();
}
```

Ersetze durch:
```js
// Always init engine toggles — handles all 4 states internally
this._initEngineToggles();
this._updateDebugVisibility();
```

**Step 2: `_initEngineToggles()` vollständig ersetzen**

Ersetze die gesamte Funktion (Zeile 536–568) durch:

```js
_initEngineToggles() {
    const cfg = this.state.config;
    const deeplActive = cfg.configured && !cfg.mock_mode;
    const llmActive   = cfg.llm_configured;

    // ── Fall 4: Keine Engine — Overlay anzeigen ──────────────────────────
    if (!deeplActive && !llmActive) {
        document.getElementById('no-engine-overlay')?.classList.add('visible');
        // Engine-State auf deepl lassen (default) — keine Übersetzung möglich
        return;
    }

    // ── Fall 2 + 3: Genau eine Engine — Single-Label anzeigen ────────────
    if (!deeplActive || !llmActive) {
        const PROVIDER_LABELS = {
            'openai':             'OpenAI',
            'anthropic':          'Anthropic',
            'ollama':             'Ollama',
            'openai-compatible':  'OpenAI-compatible',
        };
        const engineName = llmActive
            ? (cfg.llm_display_name
                || PROVIDER_LABELS[cfg.llm_provider]
                || (cfg.llm_provider
                    ? cfg.llm_provider.charAt(0).toUpperCase() + cfg.llm_provider.slice(1)
                    : 'LLM'))
            : 'DeepL';

        // Engine-State fest auf die verfügbare Engine setzen (nicht in localStorage!)
        const forcedEngine = llmActive ? 'llm' : 'deepl';
        this.state.translateEngine = forcedEngine;
        this.state.writeEngine     = forcedEngine;

        ['translate', 'write'].forEach(tab => {
            const wrap = document.getElementById(`${tab}-engine-toggle`);
            if (!wrap) return;
            // Toggle-Row durch Single-Label ersetzen
            const row = wrap.querySelector('.engine-toggle-row');
            if (row) {
                row.innerHTML = `<span class="engine-single-label">Engine: ${engineName}</span>`;
            }
            // Info-Zeile: Modell anzeigen falls LLM
            const info = document.getElementById(`${tab}-engine-info`);
            if (info) {
                const model = tab === 'translate' ? cfg.llm_translate_model : cfg.llm_write_model;
                info.textContent = llmActive && model ? model : '';
            }
            wrap.classList.add('visible');
        });

        // Formality-Sichtbarkeit synchronisieren
        this._updateFormalityVisibility('translate', forcedEngine === 'llm');
        this._updateFormalityVisibility('write', forcedEngine === 'llm');
        return;
    }

    // ── Fall 1: Beide Engines — Toggle frei bewegbar (bisheriges Verhalten) ─
    const PROVIDER_LABELS = {
        'openai':             'OpenAI',
        'anthropic':          'Anthropic',
        'ollama':             'Ollama',
        'openai-compatible':  'OpenAI-compatible',
    };
    const providerLabel = cfg.llm_display_name
        || PROVIDER_LABELS[cfg.llm_provider]
        || (cfg.llm_provider
            ? cfg.llm_provider.charAt(0).toUpperCase() + cfg.llm_provider.slice(1)
            : 'LLM');

    ['translate', 'write'].forEach(tab => {
        const model = tab === 'translate'
            ? cfg.llm_translate_model
            : cfg.llm_write_model;

        document.getElementById(`${tab}-engine-toggle`).classList.add('visible');
        document.getElementById(`${tab}-engine-info`).textContent =
            `${providerLabel} · ${model || ''}`;

        this._updateEngineLabels(tab);
    });

    // Apply saved engine states to checkboxes
    document.getElementById('translate-engine-checkbox').checked = this.state.translateEngine === 'llm';
    document.getElementById('write-engine-checkbox').checked = this.state.writeEngine === 'llm';
},
```

**Step 3: Commit**

```bash
git add static/js/app.js
git commit -m "feat(engine): handle single-engine and no-engine states in _initEngineToggles"
```

---

## Task 4: Tests — Backend-Config-Endpunkt (keine Änderung nötig)

**Kontext:** Der Backend-Endpunkt `/api/config` liefert `configured`, `mock_mode` und `llm_configured` bereits korrekt. Kein Backend-Change → keine neuen Backend-Tests nötig.

**Prüfe, dass bestehende Tests noch grünen:**

```bash
pytest tests/ -q
```

Erwartetes Ergebnis: alle Tests grün (aktuell 448).

**Step 1: Commit (nur wenn Tests grün)**

```bash
git commit --allow-empty -m "test(engine): existing tests cover config endpoint — no new backend tests needed"
```

*(Leerer Commit als explizite Dokumentation der Entscheidung.)*

---

## Task 5: Manuelle Smoke-Tests (lokale Entwicklung)

**Kontext:** Die drei Zustände lassen sich lokal durch `.env`-Manipulation testen. Nutze `uvicorn app.main:app --reload`.

### 5a — Fall 1: Beide Engines (normaler Betrieb)
```
DEEPL_API_KEY=<echter-key>
LLM_PROVIDER=openai
LLM_API_KEY=<key>
```
**Erwartung:** Toggle sichtbar, frei bewegbar, Labels „DeepL" und „OpenAI", Info-Zeile zeigt Modell.

### 5b — Fall 2: Nur DeepL
```
DEEPL_API_KEY=<echter-key>
# LLM_PROVIDER nicht gesetzt
```
**Erwartung:** Kein Toggle-Switch sichtbar. Stattdessen `Engine: DeepL` als Plain-Text in beiden Toolbars. Formality-Dropdown sichtbar. Übersetzung funktioniert.

### 5c — Fall 3: Nur LLM
```
# DEEPL_API_KEY nicht gesetzt (oder leer)
LLM_PROVIDER=openai
LLM_API_KEY=<key>
```
**Erwartung:** Kein Toggle-Switch. `Engine: OpenAI` (oder LLM_DISPLAY_NAME) als Plain-Text. Formality-Dropdown ausgeblendet. Übersetzung per LLM funktioniert.

### 5d — Fall 4: Keine Engine
```
# weder DEEPL_API_KEY noch LLM_PROVIDER gesetzt
```
**Erwartung:** Overlay erscheint, überlagert die gesamte UI, kein Schließen möglich. Text nennt beide Env-Variablen. Kein Klick-Durchstich auf die App möglich.

### 5e — Overlay-Eingabesperre prüfen
Mit geöffnetem Overlay: Tab-Taste drücken, Übersetzen-Button klicken, Escape drücken.
**Erwartung:** Overlay bleibt, keine Interaktion mit der App möglich.

**Step 1: Commit nach erfolgreichem Smoke-Test**

```bash
git add templates/index.html static/js/app.js
git commit -m "feat(engine): engine availability handling complete — single-label + no-engine overlay"
```

---

## Task 6: Version-Bump und CSS-Build

**Files:**
- Modify: `app/config.py` (VERSION)
- Modify: `CHANGELOG.md`
- Build: `static/css/styles.css` via `npm run build:css`

**Step 1: CSS neu bauen**

```bash
npm run build:css
```

**Step 2: VERSION in `app/config.py` erhöhen**

Aktuell: `VERSION = "2.9.3"` → `VERSION = "2.9.4"`

**Step 3: CHANGELOG.md — neuen Eintrag oben einfügen**

```markdown
## [2.9.4] - 2026-03-02

### Added
- Engine-Availability-Handling: Zeigt `Engine: DeepL` oder `Engine: <LLM-Name>` wenn nur eine Engine konfiguriert ist (kein Switch)
- No-Engine-Overlay: Blockiert die gesamte UI mit einer Fehlermeldung wenn weder DeepL noch LLM konfiguriert sind
```

**Step 4: Commit und Tag**

```bash
git add app/config.py CHANGELOG.md static/css/styles.css
git commit -m "chore: release v2.9.4"
git tag v2.9.4
git push && git push --tags
```

---

## Rollback-Notiz

Falls das Feature Probleme macht: einziger Touchpoint ist `_initEngineToggles()` in `app.js`. Rückgängig machen: alten Stand aus Git-History holen (`git show HEAD~N:static/js/app.js > static/js/app.js`) und den Aufruf in `loadConfig()` wieder auf `if (llm_configured)` beschränken.
