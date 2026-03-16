# Debug Button Active State Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Visual indicator for the LLM Debug button — show active state when panel is open.

**Architecture:** Small frontend-only change — toggle a CSS class on the button when panel is shown/hidden.

**Tech Stack:** Vanilla JS, CSS

---

## Problem

Der Debug-Button (lupe/Bug-Icon) zeigt nicht, ob er gerade "aktiv" ist (d.h. ob das Debug-Panel aufgeklappt ist). Der User sieht nicht, ob er gerade darauf geklickt hat.

---

## Lösung

- Button bekommt eine `.active` Klasse wenn das Panel sichtbar ist
- CSS: `.active` Button hat andere Farbe/Icon
- Icon wechseln von `fa-magnifying-glass` (Lupe) zu `fa-xmark` (X) oder `fa-magnifying-glass` → `fa-magnifying-glass-solid`

---

## Implementation

**Files:**
- Modify: `static/js/app.js` (toggle logic)
- Modify: `templates/index.html` (CSS für `.btn-debug.active`)

**Schritt 1: JS — Toggle `.active` class**

In `_renderDebugPanel()` und in `clearTranslate()`/`clearWrite()`:

```js
// Panel öffnen
document.getElementById(`debug-panel-${tab}`).style.display = 'block';
document.getElementById(`btn-debug-${tab}`).classList.add('active');

// Panel schließen
document.getElementById(`debug-panel-${tab}`).style.display = 'none';
document.getElementById(`btn-debug-${tab}`).classList.remove('active');
```

**Schritt 2: CSS — Active State**

In `input.css`:

```css
.btn-debug.active {
    background: var(--brand);
    color: #fff;
}
```

**Schritt 3: Commit**

```bash
git add static/js/app.js templates/index.html static/css/input.css
git commit -m "feat(debug): add active state to debug button — shows when panel is open"
```
