# Feature: Diff View Toggle

> Created: 2026-02-26 | Status: **Done**

---

## Goal

Add a toggle button in the Write tab toolbar to switch between "Diff View" and "Plain Text" modes for the optimized output. The preference is persisted in localStorage and defaults to "Diff View" enabled (current behavior).

---

## Requirements

### User Story
As a **user**, I want to **toggle between diff view and plain text** in the Write tab, so that **I can choose whether to see the detailed changes or just the optimized text**.

### Acceptance Criteria

- [ ] Toggle button appears in the Write tab toolbar (next to or integrated with the engine toggle)
- [ ] Toggle is visible only when LLM is configured (`llm_configured: true`)
- [ ] Default state: Diff View enabled (matches current behavior)
- [ ] When Diff View is enabled: Show optimized text with diff highlighting (green for additions, red/strikethrough for removals)
- [ ] When Diff View is disabled: Show only plain optimized text without any diff markup
- [ ] Preference is stored in localStorage (`writeDiffView` key) and persists across page reloads
- [ ] Toggle state does not affect the Translate tab (only Write tab)
- [ ] Changes badge (`+X / -X`) is hidden when Diff View is disabled (since there's no diff to show)
- [ ] Streaming mode: Plain text during stream, diff applied when complete (existing behavior preserved)

### Out of scope

- Adding diff view to the Translate tab (Write tab only)
- Per-engine diff preference (one toggle for both DeepL and LLM)
- Customizing diff colors or styling
- Diff algorithm options (always uses word-level diff)

---

## Technical Approach

### Files affected

- `templates/index.html` — Add toggle HTML in Write toolbar
- `static/css/input.css` — Add styles for diff-toggle (optional, can reuse engine-toggle styles)
- `static/js/app.js` — Add state, localStorage handling, toggle logic

### New state

```javascript
// In App.state
writeDiffView: true  // Default enabled
```

### New localStorage key

- `writeDiffView` — `'true'` (enabled) or `'false'` (disabled)

### Implementation steps

1. **Add state + localStorage loading** in `app.js`
   - Load `writeDiffView` from localStorage on init (similar to engine states)
   - Default to `true` if not set

2. **Add toggle HTML** in `index.html`
   - Place in Write tab toolbar, similar to engine toggle
   - Only visible when `llm_configured` is true
   - Use existing `.engine-toggle-wrap` CSS class for styling consistency

3. **Add toggle handler** in `app.js`
   - Listen for toggle change, save to localStorage
   - Re-render current output if text exists

4. **Modify output rendering** in `app.js`
   - In `_writeLLM()` and `_writeDeepL()` methods
   - Check `this.state.writeDiffView` before applying `renderDiff()`
   - If disabled, use `output.textContent = text` instead of `output.innerHTML = this.renderDiff()`
   - Hide/show changes badge based on diff view state

### Edge cases

- No output yet: Toggle should still be functional, applies to next optimization
- Toggling while streaming: Toggle state saved, applied after stream completes
- jsdiff not loaded: Plain text shown regardless of toggle (existing safety check)

---

## Decisions Made

<!-- None yet — planning phase -->

---

## Progress Log

<!-- [date] @agent — <what was done> — next: <what comes next> -->

---

## Open Questions

- Should the toggle be visible even when LLM is NOT configured? (Requirement says "when LLM is configured", but DeepL users might also want diff toggle)
  - **Current decision**: Follow requirement exactly — only visible when LLM is configured
- Should we add a keyboard shortcut for toggling diff view?
  - **Current decision**: Out of scope — can be added later if requested

---

## Testing Notes

### Functional tests

1. Toggle visible when LLM configured, hidden when not
2. Toggle state persists after page reload
3. Diff highlighting appears when enabled (green additions, red strikethrough removals)
4. Plain text shown when disabled (no span tags in DOM)
5. Changes badge shows correct counts when enabled, hidden when disabled
6. Works with both DeepL and LLM engines

### Visual check

- Toggle matches existing engine toggle styling
- Diff colors are visible in both light and dark mode
- Layout doesn't break with long model names in engine toggle row
