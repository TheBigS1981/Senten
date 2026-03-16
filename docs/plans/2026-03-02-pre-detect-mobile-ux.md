# Pre-Detect Language + Mobile UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** (1) Eliminate the LLM intermediate translation by detecting the source language *before* the stream starts; (2) Improve mobile layout with auto-growing textareas, compact language bar, and hidden desktop-only clutter.

**Architecture:**
- New backend endpoint `POST /api/detect-lang` calls `llm_service._detect_language()` with the first 50 words of the text and returns `{"detected_lang": "DE"}`.
- Frontend calls this endpoint before `_translateLLMStream()` when in auto-detection mode, adjusts the target language, then streams with the correct language from the start.
- Mobile improvements are pure CSS + a small JS auto-resize helper — no structural HTML changes.

**Tech Stack:** Python/FastAPI backend, Vanilla JS frontend, Tailwind CSS v3 + CSS custom properties in `templates/index.html`

---

## Task 1 — Backend: `POST /api/detect-lang` endpoint

**Files:**
- Modify: `app/models/schemas.py` — add `DetectLangRequest`, `DetectLangResponse`
- Modify: `app/routers/translate.py` — add the endpoint
- Modify: `app/services/llm_service.py` — reduce `_detect_language()` word limit to 50

**Step 1: Write the failing test**

Add to `tests/test_llm_router.py` (or a new `tests/test_detect_lang.py`):

```python
class TestDetectLang:
    """POST /api/detect-lang — language detection endpoint."""

    def test_returns_detected_lang(self, client):
        """Returns detected language code for given text."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm._detect_language = AsyncMock(return_value="DE")

            res = client.post(
                "/api/detect-lang",
                json={"text": "Das ist ein deutscher Text.", "max_words": 50},
            )

        assert res.status_code == 200
        assert res.json()["detected_lang"] == "DE"

    def test_returns_unknown_when_llm_not_configured(self, client):
        """Returns 'unknown' if LLM is not configured (graceful degradation)."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = False

            res = client.post(
                "/api/detect-lang",
                json={"text": "Some text."},
            )

        assert res.status_code == 200
        assert res.json()["detected_lang"] == "unknown"

    def test_returns_unknown_when_detection_fails(self, client):
        """Returns 'unknown' if _detect_language raises — never 500."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm._detect_language = AsyncMock(side_effect=Exception("LLM error"))

            res = client.post(
                "/api/detect-lang",
                json={"text": "Some text."},
            )

        assert res.status_code == 200
        assert res.json()["detected_lang"] == "unknown"

    def test_rejects_empty_text(self, client):
        """Empty text returns 400."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True

            res = client.post("/api/detect-lang", json={"text": "  "})

        assert res.status_code == 400

    def test_truncates_to_max_words(self, client):
        """Only the first max_words words are sent to the LLM."""
        long_text = " ".join([f"word{i}" for i in range(200)])

        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm._detect_language = AsyncMock(return_value="EN")

            res = client.post(
                "/api/detect-lang",
                json={"text": long_text, "max_words": 50},
            )

        # _detect_language must be called with text truncated to 50 words
        called_text = mock_llm._detect_language.call_args[0][0]
        assert len(called_text.split()) <= 50
        assert res.status_code == 200
```

**Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_llm_router.py::TestDetectLang -v
```
Expected: FAIL — `404 Not Found` or `ImportError`

**Step 3: Add schemas to `app/models/schemas.py`**

Add after the existing `WriteResponse` class:

```python
class DetectLangRequest(BaseModel):
    """Request body for POST /api/detect-lang."""
    text: str
    max_words: int = Field(default=50, ge=1, le=200)


class DetectLangResponse(BaseModel):
    """Response for POST /api/detect-lang."""
    detected_lang: str  # DeepL language code (e.g. "DE", "EN-US") or "unknown"
```

**Step 4: Add the endpoint to `app/routers/translate.py`**

Add these imports at the top (with the other schema imports):
```python
from app.models.schemas import (
    ...
    DetectLangRequest,
    DetectLangResponse,
)
```

Add the endpoint (before the last line of the file, after the `/write/stream` route):

```python
@router.post("/detect-lang", response_model=DetectLangResponse)
@limiter.limit("60/minute")
async def detect_language(request: Request, body: DetectLangRequest):
    """Detect the language of a short text snippet via LLM.

    Designed to be called *before* starting a streaming translation so the
    correct target language is known upfront. Returns {"detected_lang": "unknown"}
    on any failure — never raises 5xx — so the caller can fall back gracefully.
    """
    text = body.text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text darf nicht leer sein.",
        )

    if not llm_service.is_configured():
        return DetectLangResponse(detected_lang="unknown")

    # Truncate to max_words before sending to LLM
    words = text.split()
    truncated = " ".join(words[: body.max_words])

    try:
        detected = await llm_service._detect_language(truncated)
        return DetectLangResponse(detected_lang=detected or "unknown")
    except Exception as exc:
        logger.warning("detect-lang endpoint: detection failed: %s", exc)
        return DetectLangResponse(detected_lang="unknown")
```

**Step 5: Reduce word limit in `llm_service._detect_language()` from 100 to 50**

In `app/services/llm_service.py`, find the method `_detect_language` (~line 714):

```python
# BEFORE
words = text.split()
truncated_text = " ".join(words[:100])

# AFTER — 50 words is enough for reliable detection and halves latency
words = text.split()
truncated_text = " ".join(words[:50])
```

**Step 6: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_llm_router.py::TestDetectLang -v
```
Expected: All 5 tests PASS.

**Step 7: Run full suite**

```bash
python3 -m pytest tests/ -q
```
Expected: All tests pass (440+5 = 445+).

**Step 8: Commit**

```bash
git add app/models/schemas.py app/routers/translate.py app/services/llm_service.py tests/test_llm_router.py
git commit -m "feat(llm): add POST /api/detect-lang endpoint + reduce detection to 50 words"
```

---

## Task 2 — Frontend: Pre-detect before LLM stream

**Files:**
- Modify: `static/js/app.js` — `_translateLLMStream()`, `translate()`

**Step 1: Write the test (integration-level, manual verification)**

This change is frontend-only JS logic. No automated test can cover a fetch call in Vanilla JS without a testing framework. We verify by running the app and observing that:
- Auto-mode + LLM: no intermediate translation visible
- Manual mode (user picked a source language): pre-detect is skipped

**Step 2: Add `_preDetectLang()` helper to `app.js`**

Add this method after `_selectWriteTargetLang()` (around line 1028):

```javascript
/**
 * Pre-detect source language before starting an LLM stream.
 *
 * Called only when useAutoDetection is true and no source language is
 * explicitly selected by the user. Sends the first 50 words to
 * POST /api/detect-lang and returns the detected DeepL language code
 * (e.g. "DE", "EN-US") or null on failure / when not applicable.
 *
 * @param {string} text  Full source text
 * @param {AbortSignal} signal  AbortController signal
 * @returns {Promise<string|null>}
 */
async _preDetectLang(text, signal) {
    if (!this.state.useAutoDetection) return null;
    if (this.getSourceLang()) return null;  // user already picked a language
    if (!this.state.config?.llm_configured) return null;

    // Send only first 50 words — fast, cheap, sufficient
    const words = text.trim().split(/\s+/).slice(0, 50).join(' ');

    try {
        const res = await fetch('/api/detect-lang', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: words, max_words: 50 }),
            signal,
        });
        if (!res.ok) return null;
        const data = await res.json();
        return (data.detected_lang && data.detected_lang !== 'unknown')
            ? data.detected_lang
            : null;
    } catch {
        return null;  // AbortError or network failure — degrade gracefully
    }
},
```

**Step 3: Wire pre-detect into `translate()` for LLM engine**

In `translate()` (around line 1031), the LLM branch currently looks like:
```javascript
if (this.state.translateEngine === 'llm') {
    await this._translateLLMStream(text, sourceLang, targetLang, output, signal);
```

Replace the entire LLM branch with:
```javascript
if (this.state.translateEngine === 'llm') {
    // Pre-detect source language so we know the correct target BEFORE streaming.
    // This eliminates the intermediate translation (Bug #2).
    const preDetected = await this._preDetectLang(text, signal);

    let effectiveTargetLang = targetLang;
    if (preDetected) {
        // Show detected language badge and update source selection
        this._applySourceLangUI(preDetected);
        // Auto-switch target language (DE↔EN) based on detected source
        this.autoSelectTargetLang('translate', preDetected);
        effectiveTargetLang = this.getTargetLang('translate');
    }

    await this._translateLLMStream(text, preDetected || sourceLang, effectiveTargetLang, output, signal);
```

**Step 4: Extract `_applySourceLangUI()` helper**

The logic for updating the source language badge + radio buttons currently lives inside `_applyDetectedLang()`. Extract the UI-update part so it can be called separately from pre-detect.

Add after `_preDetectLang()`:

```javascript
/**
 * Update source language UI (badge + radio/dropdown) for a detected language.
 * Does NOT trigger re-translation. Pure UI update.
 *
 * @param {string} detected  DeepL language code e.g. "DE"
 */
_applySourceLangUI(detected) {
    if (!detected || detected === 'unknown') return;

    this.state.detectedLang = detected;
    const badge = document.getElementById('detected-lang-display');
    if (badge) {
        badge.textContent = `Erkannt: ${this.getLangName(detected)}`;
        badge.classList.add('visible');
    }

    // Sync radio buttons / dropdown
    const sourceRadioValue = detected === 'DE' ? 'DE'
        : detected.startsWith('EN') ? 'EN'
        : null;
    if (sourceRadioValue) {
        this._selectRadio('source-lang-radio', sourceRadioValue);
        const srcSelect = document.getElementById('source-lang');
        srcSelect.value = '';
        if (srcSelect.options[0]) srcSelect.options[0].selected = true;
    } else {
        this._selectRadio('source-lang-radio', '');
        const srcSelect = document.getElementById('source-lang');
        const optExists = Array.from(srcSelect.options).some(o => o.value === detected);
        if (optExists) srcSelect.value = detected;
    }
},
```

**Step 5: Remove re-translate logic from `_applyDetectedLang()` for LLM streaming**

After the pre-detect change, `_applyDetectedLang()` is still called at the end of `_translateLLMStream()`. For LLM streaming the `shouldAutoSwitch` branch would launch *another* non-streaming re-translate — that must not happen when pre-detect already chose the right language.

In `_applyDetectedLang()`, the `shouldAutoSwitch` block fires a non-streaming `/api/translate` call. This is only needed for DeepL (no pre-detect there). Add a guard:

```javascript
// BEFORE (around line 1233):
if (shouldAutoSwitch) {
    ...
    fetch('/api/translate', { ... engine: this.state.translateEngine ... })
    ...
}

// AFTER — skip re-translate when LLM engine is active (pre-detect already corrected it)
if (shouldAutoSwitch && this.state.translateEngine !== 'llm') {
    ...
    fetch('/api/translate', { ... engine: this.state.translateEngine ... })
    ...
}
// For LLM, just update the UI (autoSelectTargetLang was already called in translate())
if (shouldAutoSwitch && this.state.translateEngine === 'llm') {
    this.autoSelectTargetLang(tab, detected);
    this.state.autoTargetChanged = false;
    if (output.value === '') output.value = translatedText;
}
```

**Step 6: Manual verification**

Start the app (`uvicorn app.main:app --reload`), switch to LLM engine:
1. Auto mode + DE text → stream shows EN output immediately (no DE first) ✓
2. Auto mode + EN text → stream shows DE output immediately ✓
3. Manual mode (source = DE selected) → no pre-detect call, stream starts immediately ✓
4. DeepL engine → no pre-detect, behavior unchanged ✓

**Step 7: Commit**

```bash
git add static/js/app.js
git commit -m "feat(frontend): pre-detect language before LLM stream to eliminate intermediate translation"
```

---

## Task 3 — Mobile CSS improvements

**Files:**
- Modify: `templates/index.html` — the `@media (max-width: 680px)` block + `.pane-textarea` + `.pane-output`
- Modify: `static/css/input.css` — add `.mobile-hide` helper
- Modify: `static/js/app.js` — add auto-resize for textareas

**Step 1: No automated test needed — verify visually**

Open Chrome DevTools → toggle device toolbar → iPhone SE or Pixel 5 viewport.

**Step 2: Expand mobile breakpoint CSS in `templates/index.html`**

Find the `@media (max-width: 680px)` block (around line 456) and replace it with:

```css
@media (max-width: 680px) {
    /* Layout */
    .panes { grid-template-columns: 1fr; }
    .pane + .pane { border-left: none; border-top: 1px solid var(--border); }

    /* Language bar: stack source + target vertically, no divider line */
    .lang-bar { grid-template-columns: 1fr; }
    .lang-divider { width: 100%; height: 1px; }
    .lang-options.right { justify-content: flex-start; }

    /* Smaller text panes — give more screen to content */
    .pane-textarea,
    .pane-output { min-height: 120px; max-height: 40vh; }

    /* Hide desktop-only chrome */
    .usage-bar { display: none; }
    .header-inner { gap: var(--space-2); }
    /* Hide keyboard shortcut hint and Debug button on mobile */
    .mobile-hide { display: none !important; }

    /* Compact toolbar — allow wrapping */
    .toolbar { padding: var(--space-2) var(--space-3); gap: var(--space-2); }
    .toolbar-right { font-size: var(--text-xs); flex-wrap: wrap; }

    /* Larger touch targets for language radio labels */
    .lang-label { padding: var(--space-2) var(--space-4); min-height: 40px;
                  display: inline-flex; align-items: center; }

    /* Main padding smaller on mobile */
    .main { padding: var(--space-3); }

    /* Translate card: less top margin */
    .translator-card { margin-top: var(--space-3); }
}
```

**Step 3: Add `mobile-hide` to desktop-only toolbar elements in `templates/index.html`**

In the translate toolbar (search for `id="btn-debug-translate"`), add `mobile-hide` class to:
- The Debug button: `<button ... id="btn-debug-translate" class="btn btn-ghost mobile-hide">`
- The `Strg+Enter` hint span in `.toolbar-right`

Do the same for the write toolbar (same elements in write panel).

**Step 4: Add auto-resize for textareas in `static/js/app.js`**

Add this helper method near the top of `App`, after `init()`:

```javascript
/**
 * Auto-resize a textarea to fit its content.
 * Grows up to the CSS max-height, then scrolls.
 * Called on every input event.
 */
_autoResizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
},
```

In `bindEvents()`, after the existing input listeners for the textareas, add:

```javascript
// Auto-resize textareas on input
const tInput  = document.getElementById('input-text-translate');
const wInput  = document.getElementById('input-text-write');
if (tInput) tInput.addEventListener('input', () => this._autoResizeTextarea(tInput));
if (wInput) wInput.addEventListener('input', () => this._autoResizeTextarea(wInput));
```

**Step 5: Add `overflow-y: auto` guard for auto-resize**

The `.pane-textarea` CSS currently has `resize: none`. Add `overflow-y: auto` so content doesn't clip when `max-height` is reached:

In `templates/index.html`, find `.pane-textarea, .pane-output { ... }` and ensure `overflow-y: auto` is present (`.pane-output` already has it; add it to the shared rule):

```css
.pane-textarea, .pane-output {
    ...
    overflow-y: auto;   /* add if not already present */
}
```

**Step 6: Rebuild CSS**

```bash
npm run build:css
```

**Step 7: Visual QA checklist**

In Chrome DevTools mobile simulator (375px width):
- [ ] Textareas start at ~120px, grow as user types
- [ ] Textareas stop growing at ~40vh and scroll inside
- [ ] Language bar stacks vertically without overflow
- [ ] Debug button not visible
- [ ] "Strg+Enter" hint not visible
- [ ] Action buttons (Übersetzen / Optimieren) large enough to tap
- [ ] No horizontal scrollbar on the page

Also verify on desktop (>680px):
- [ ] Layout unchanged (side-by-side panes)
- [ ] Auto-resize still works in the input pane
- [ ] Debug button still visible

**Step 8: Commit**

```bash
git add templates/index.html static/css/input.css static/css/styles.css static/js/app.js
git commit -m "feat(mobile): responsive layout improvements — compact mobile view, auto-resize textareas"
```

---

## Task 4 — Version bump + release

**Files:**
- Modify: `app/config.py` — VERSION bump to `2.9.3`
- Modify: `CHANGELOG.md` — add v2.9.3 entry
- Modify: `docs/STATUS.md` — update status

**Step 1: Update version**

In `app/config.py`:
```python
VERSION = "2.9.3"
```

**Step 2: Update CHANGELOG**

Add above the existing `[2.9.2]` entry:

```markdown
## [2.9.3] - 2026-03-02

### Added
- **`POST /api/detect-lang`** — neuer leichtgewichtiger Endpunkt erkennt die Quellsprache mit den ersten 50 Wörtern; gibt `{"detected_lang": "DE"}` oder `{"detected_lang": "unknown"}` zurück; niemals 5xx (graceful degradation)
- **Mobile UX** — kompakteres Layout bei ≤680px Breite: Textfelder wachsen dynamisch mit dem Inhalt (max 40vh, dann Scrollbar); Mindesthöhe 120px (war 200px); Debug-Button und Strg+Enter-Hinweis auf Mobil ausgeblendet; Toolbar kompakter; größere Tap-Targets für Sprachauswahl; `.main` padding reduziert

### Fixed
- **Bug #2: LLM Zwischenübersetzung** — Quellsprache wird jetzt *vor* dem Stream erkannt (`_preDetectLang()` mit 50 Wörtern); Zielsprache wird direkt korrekt gesetzt; kein Zwischenergebnis mehr sichtbar; `_detect_language()` intern auf 50 Wörter reduziert (war 100); `_applyDetectedLang()` löst für LLM-Engine keine zweite Übersetzung mehr aus
```

**Step 3: Update STATUS.md**

- Bug #2 in der Tabelle als DONE markieren
- Neue Recent Decision eintragen

**Step 4: Commit + tag**

```bash
git add app/config.py CHANGELOG.md docs/STATUS.md
git commit -m "chore: release v2.9.3"
git tag v2.9.3 && git push && git push --tags
```

---

## Testing Summary

| Task | Test type | Command |
|------|-----------|---------|
| Task 1 | Unit/Integration pytest | `python3 -m pytest tests/ -q` |
| Task 2 | Manual browser test | DevTools + LLM stream |
| Task 3 | Visual QA | DevTools device emulation |
| Task 4 | — | — |

Expected final test count: **445+** (current 440 + 5 new detect-lang tests)
