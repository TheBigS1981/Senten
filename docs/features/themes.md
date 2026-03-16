# Feature: Verschiedene Themes

**Status:** Done  
**Erstellt:** 2026-02-27  
**Erstellt von:** @build  
**Ziel-Version:** 2.7.0

---

## Übersicht

User sollen die Möglichkeit bekommen, das visuelle Theme der Anwendung zu ändern — nicht nur zwischen Hell und Dunkel, sondern auch zwischen verschiedenen Farbvarianten und einer individuellen Akzentfarbe.

---

## Anforderungen

### Funktionale Anforderungen

1. **Vordefinierte Themes** — mindestens 3–4 Themes zur Auswahl
   - Hell (Blau) — Standard, aktuelles Design
   - Dunkel (Blau) — aktueller Dark Mode
   - Hell (Violett) — Violett-Variante
   - Dunkel (Violett) — Violett-Dark

2. **Custom Akzentfarbe** — User kann eine eigene Farbe über einen Color Picker wählen
   - Überschreibt die Akzentfarbe des aktiven Themes
   - Alle abhängigen Werte (hover, subtle, active) werden automatisch berechnet

3. **Persistenz** — Gewähltes Theme + Akzentfarbe werden in `localStorage` gespeichert
   - Key `theme`: `light-blue` | `dark-blue` | `light-violet` | `dark-violet`
   - Key `accent`: `blue` | `violet` | `custom:#rrggbb`

4. **System-Präferenz** — Falls kein Theme gespeichert, wird `prefers-color-scheme` berücksichtigt (wie bisher)

### UI-Anforderungen

5. **Theme-Dropdown im Header** — ersetzt den bisherigen Hell/Dunkel-Toggle-Button
   - Zeigt aktuelles Theme mit Icon
   - Öffnet Dropdown mit allen Optionen
   - Am Ende des Dropdowns: Akzentfarbe-Sektion mit Color Picker

6. **Live-Preview** — Theme wechselt sofort beim Klick (kein Reload nötig)

---

## Design

### Vordefinierte Themes

| Theme-ID | Modus | Akzent-Base | Beschreibung |
|----------|-------|-------------|-------------|
| `light-blue` | Hell | `#0066ff` | Standard (aktuell) |
| `dark-blue` | Dunkel | `#60a5fa` | Aktueller Dark Mode |
| `light-violet` | Hell | `#7c3aed` | Violett-Variante |
| `dark-violet` | Dunkel | `#a78bfa` | Violett-Dark |

### UI-Konzept (Header)

```
[ Senten Logo ]  [ Usage Bar ]  [ 🎨 Hell (Blau) ▾ ]
                                      ↓ Dropdown:
                                  ○ Hell (Blau)      ← aktiv
                                  ○ Dunkel (Blau)
                                  ○ Hell (Violett)
                                  ○ Dunkel (Violett)
                                  ─────────────────
                                  🎨 Akzentfarbe: [█ #0066ff]
```

---

## Technische Spezifikation

### Betroffene Dateien

| Datei | Art der Änderung |
|-------|-----------------|
| `static/css/design-tokens.css` | Violett-Accent Tokens + `--accent-*` Variablen |
| `templates/index.html` | Theme-Dropdown HTML + CSS, Color Picker |
| `static/js/app.js` | `applyTheme(theme, accent)` erweitern, localStorage-Keys |

### CSS-Strategie

```css
/* Neue --accent-* Variablen — überschreibbar per JS inline-style */
:root {
  --accent-default: var(--color-primary-500);
  --accent-hover:   var(--color-primary-600);
  --accent-active:  var(--color-primary-700);
  --accent-subtle:  var(--color-primary-50);
}

/* Violett-Theme */
[data-theme="light-violet"],
[data-theme="dark-violet"] {
  --color-interactive-default: var(--color-secondary-500);
  --color-interactive-hover:   var(--color-secondary-600);
  --color-interactive-active:  var(--color-secondary-700);
  --color-interactive-subtle:  var(--color-secondary-50);
}

/* Dark-Variants */
[data-theme="dark-blue"],
[data-theme="dark-violet"] {
  /* … dark mode overrides … */
}
```

### JS-Strategie

```javascript
applyTheme(themeId, customAccent = null) {
  // themeId: 'light-blue' | 'dark-blue' | 'light-violet' | 'dark-violet'
  document.documentElement.setAttribute('data-theme', themeId);
  if (customAccent) {
    // Inline CSS-Variable setzen für Custom-Farbe
    document.documentElement.style.setProperty('--color-interactive-default', customAccent);
    // hover/subtle aus customAccent berechnen
  }
  localStorage.setItem('theme', themeId);
  if (customAccent) localStorage.setItem('accent-custom', customAccent);
}
```

---

## Akzeptanzkriterien

- [ ] Mindestens 4 vordefinierte Themes auswählbar
- [ ] Custom Akzentfarbe via Color Picker wählbar
- [ ] Theme überlebt Page-Reload (localStorage)
- [ ] System-Präferenz (dark/light) wird als Fallback genutzt
- [ ] Alle interaktiven Elemente (Buttons, Links, Tabs, Toggles) spiegeln das Theme korrekt wider
- [ ] Color Picker zeigt aktuelle Akzentfarbe an
- [ ] Kein Seitenreload beim Theme-Wechsel
- [ ] Kein Backend-Change notwendig

---

## Nicht in Scope

- Backend-Speicherung des Themes
- Mehr als 4 vordefinierte Themes in der ersten Version
- Font-Auswahl
- Layout-Varianten (nur Farben)
