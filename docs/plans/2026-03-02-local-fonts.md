# Local Fonts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate external Google Fonts dependency — load Inter font locally instead.

**Architecture:** Pure frontend/CSS change. Download Inter font files, store locally, update CSS `@font-face` rules, remove Google Fonts link from HTML.

**Tech Stack:** WOFF2 font files, CSS `@font-face`, static file serving

---

## Task 1: Download Inter Font Files

**Kontext:** Inter von Google Fonts herunterladen. Wir brauchen die gängigen Gewichte.

**Schritt:** Lade folgende Dateien von [Google Fonts Inter](https://fonts.google.com/specimen/Inter) oder einem Mirror herunter:

- `Inter-Regular.woff2`
- `Inter-Medium.woff2`
- `Inter-SemiBold.woff2`
- `Inter-Bold.woff2`

Speichere unter: `static/fonts/Inter-{weight}.woff2`

**Alternative:** Nutze `google-fonts-downloader` CLI oder lade manuell herunter.

---

## Task 2: CSS — Add @font-face Rules

**Files:**
- Modify: `static/css/input.css` (neue Sektion am Anfang nach `:root {}`)

**Schritt:** Füge ein:

```css
/* ── Local Fonts ─────────────────────────────────────────────────────── */
@font-face {
    font-family: 'Inter';
    src: url('../fonts/Inter-Regular.woff2') format('woff2');
    font-weight: 400;
    font-display: swap;
}
@font-face {
    font-family: 'Inter';
    src: url('../fonts/Inter-Medium.woff2') format('woff2');
    font-weight: 500;
    font-display: swap;
}
@font-face {
    font-family: 'Inter';
    src: url('../fonts/Inter-SemiBold.woff2') format('woff2');
    font-weight: 600;
    font-display: swap;
}
@font-face {
    font-family: 'Inter';
    src: url('../fonts/Inter-Bold.woff2') format('woff2');
    font-weight: 700;
    font-display: swap;
}
```

Dann: `npm run build:css`

---

## Task 3: HTML — Remove Google Fonts Link

**Files:**
- Modify: `templates/index.html` (Zeile 24–27)

**Schritt:** Entferne diese Zeilen:

```html
<!-- Google Fonts — Inter (with SRI) -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" integrity="sha384-K5EqGsh0IDpTzs9sOw3mL5+ZbdoldYLVpEj46TA37y2gfudWisq74pKFqxrnWAv+" crossorigin="anonymous">
```

---

## Task 4: Verify

Starte den Server und prüfe:
- [ ] Inter Font wird korrekt geladen (DevTools → Network → .woff2)
- [ ] Keine Requests an fonts.googleapis.com mehr
- [ ] Seite sieht gleich aus wie vorherback

Falls Probleme: Google Fonts Link

---

## Roll wieder einfügen, Fonts behalten (kein Schaden).
