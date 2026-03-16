# ADR-005: Professionelles Design-System

## Status

**Proposed** — 2026-02-24

## Kontext

Das Senten-Frontend wurde bisher mit Inline-CSS und vereinzelten CSS-Variablen entwickelt. Es fehlte:
- Konsistentes Farbsystem
- Formelle Type Scale
- Definiertes Spacing-System
- Dokumentierte Component-Styles

Dies führte zu inkonsistenten Werten wie `border-radius: 6px` an einer Stelle und `border-radius: 8px` an einer anderen.

## Entscheidungen

### 1. Farbsystem: 10-Stufen-Palette

**Entscheidung:** Jede Farbe (Primary, Secondary, Neutral) erhält eine 10-stufige Skala von 50–950.

**Begründung:**
- 10 Stufen bieten genug Granularität für alle Use Cases (Subtle Backgrounds bis High-Contrast Text)
- Skala ist etablierter Industry Standard (Tailwind, Material Design)
- Ermöglicht konsistente "Abstufungen" innerhalb einer Farbfamilie

**Alternative verworfen:**
- 5 Stufen → nicht genug Granularität für Subtle/Dark Mode
- Beliebige Werte → keine Konsistenz

### 2. Type Scale: Major Third

**Entscheidung:** Type Scale mit Ratio 1.25 (Major Third), Base 16px.

**Begründung:**
- Major Third ist der beste Kompromiss zwischen Lesbarkeit und Information Density
- 16px Base ist WCAG-konform (nicht unter 14px für Body)
- Perfekt für Dashboard/Application-UI (nicht zu locker wie Perfect Fourth)

**Alternative verworfen:**
- Major Second (1.125) → zu eng für Headings
- Perfect Fourth (1.333) → zu luftig für Dashboard

### 3. Spacing: 8pt Grid

**Entscheidung:** Alle Spacing-Werte sind Vielfache von 4px (0.25rem).

**Begründung:**
- 8pt Grid ist Developer-Standard (iOS, Material, Atlassian)
- 4px Basis ermöglicht feinere Abstufungen als 8px
- Funktioniert gut mit 16px Base Font

**Alternative verworfen:**
- 4px Grid → zu fein, zu viele Werte
- 16px Grid → zu grob für kompakte UIs

### 4. Border Radius: 5-Stufen-Scale

**Entscheidung:** 5 Stufen (sm, md, lg, xl, 2xl) + full für Pills.

**Begründung:**
- Unterschiedliche Radien für unterschiedliche Komponenten-Größen
- 2xl (16px) für Cards, lg (8px) für Buttons, md (6px) für Inputs
- full für Badges/Chips

### 5. Elevation: 6-Stufen Shadow Scale

**Entscheidung:** xs, sm, md, lg, xl, 2xl basierend auf Tailwind.

**Begründung:**
- Bewährtes System, Entwickler kennen es
- Klare Hierarchie: Card < Dropdown < Modal
- Focus-Ring als separater Shadow für Accessibility

### 6. Motion: Duration + Easing getrennt

**Entscheidung:** Duration-Tokens (50ms–500ms) und Easing-Tokens getrennt definieren.

**Begründung:**
- Erlaubt feinere Kontrolle über Animationen
- Standardisierte Easing-Kurven statt "magic numbers"
- prefers-reduced-motion Respektierung möglich

### 7. Dark Mode: Semantic Aliases

**Entscheidung:** Nur semantische Aliases (`--color-bg-default`) ändern sich in Dark Mode, nicht die Rohfarben.

**Begründung:**
- Einheitliche API für Komponenten
- Entwickler nutzen semantische Tokens, Dark/Light ist Implementierungsdetail
- Leichter erweiterbar für zukünftige Themes

### 8. Component Specs als CSS-Klassen

**Entscheidung:** Wiederverwendbare Komponenten als fertige CSS-Klassen bereitstellen (`.btn-primary`, `.select`, etc.).

**Begründung:**
- Schnellere Entwicklung durch Copy-Paste
- Konsistenz über alle Instanzen
- Selbst-dokumentierend durch Klassen-Namen

## Konsequenzen

### Positiv

- **Konsistenz:** Alle Farben, Abstände, Radien kommen aus dem gleichen System
- **Wartbarkeit:** Änderungen an zentraler Stelle wirken global
- **Developer Experience:** Token-Namen sind selbsterklärend (`var(--color-text-sub)`)
- **Accessibility:** Alle Contrast Ratios WCAG AA geprüft
- **Dark Mode:** Vollständig unterstützt

### Negativ

- **Lernkurve:** Entwickler müssen Token-Namen lernen
- **Migration:** Bestehendes CSS muss migriert werden (einmaliger Aufwand)

## Referenzen

- **Token-Datei:** `static/css/design-tokens.css`
- **Implementierung:** `templates/index.html`
- **Inspiration:** Tailwind CSS, Material Design 3, Atlassian Design System

## Historie

- **2026-02-24:** ADR erstellt, Design-System implementiert
