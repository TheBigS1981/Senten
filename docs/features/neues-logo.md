# Feature: Neues Logo

**Status:** DONE  
**Erstellt:** 2026-02-27  
**Erstellt von:** @build  
**Ziel-Version:** 2.7.0

---

## Übersicht

Das bestehende Logo (stilisiertes "S" auf blauem Hintergrund) soll durch ein neues, professionelles Logo ersetzt werden. Das neue Logo soll als Wordmark gestaltet sein (Icon + Schriftzug "Senten") und das Konzept "Sprechblase / Translation" visuell kommunizieren.

---

## Anforderungen

### Design-Anforderungen

1. **Stil:** Wordmark — App-Icon + Schriftzug "Senten" nebeneinander
2. **Konzept:** Sprechblasen-Icon — symbolisiert Dialog und Übersetzung zwischen zwei Sprachen
   - Zwei überlappende oder nebeneinanderliegende Sprechblasen
   - Pfeil oder Übergangs-Element zeigt Übersetzungsrichtung
3. **Theme-Integration:** Logo-Akzentfarbe passt sich ans aktive Theme an
   - Icon nutzt `var(--color-interactive-default)` oder `currentColor`
   - Funktioniert automatisch mit dem Theme-Feature
4. **Lesbarkeit:** Schriftzug "Senten" klar und lesbar in verschiedenen Größen

### Technische Anforderungen

5. **Formate:**
   - `static/img/logo.svg` — 32×32 App-Icon (nur Icon-Teil, für den Header)
   - `static/img/logo-large.svg` — Wordmark: Icon + "Senten"-Schriftzug (128×40 oder ähnlich)
   - `static/img/favicon.svg` — Skaliertes Favicon (SVG, vereinfachte Version)
6. **Kein Raster-Format** (kein `.ico`, kein `.png`) — SVG reicht für alle modernen Browser
7. **Kein externer Font im SVG** — Schrift entweder als Pfad eingebettet oder via `font-family: inherit`

---

## Konzept-Beschreibung

### App-Icon (logo.svg — 32×32)
- Linke Sprechblase: etwas größer, symbolisiert Quellsprache
- Rechte Sprechblase: etwas kleiner, leicht überlappend oder daneben, symbolisiert Zielsprache
- Zwischen den Blasen: kleiner Pfeil oder Übergangsindikator
- Stil: modern, flach (flat design), keine Schatten, keine Gradienten
- Hintergrundform: abgerundetes Quadrat (wie bisher) ODER transparenter Hintergrund

### Favicon (favicon.svg)
- Vereinfachte Version des Icons
- Gut erkennbar bei kleinen Größen (16×16, 32×32)

### Wordmark (logo-large.svg)
- Icon links + "Senten" rechts
- Schrift: Inter, font-weight 600 oder 700
- Schrift als Pfad oder via `<text>` mit `font-family="Inter, sans-serif"`

---

## Betroffene Dateien

| Datei | Änderung |
|-------|---------|
| `static/img/logo.svg` | Neudesign — 32×32 Icon |
| `static/img/logo-large.svg` | Wordmark — Icon + "Senten" |
| `static/img/favicon.svg` | Neues Favicon (neu erstellen) |
| `templates/index.html` | Favicon-Link auf `favicon.svg` zeigen |

---

## Akzeptanzkriterien

- [x] Neues logo.svg ist 32×32, erkennbar als Sprechblasen-Icon
- [x] logo-large.svg zeigt Icon + "Senten"-Schriftzug als Wordmark (160×36)
- [x] favicon.svg ist als Browser-Tab-Icon erkennbar und gut lesbar
- [x] Icon-Hintergrund in Brand-Blau #0066ff (feste Farbe, da SVG via img-Tag)
- [x] Kein externer HTTP-Request für Logo-Assets nötig
- [x] Browser-Tab zeigt neues Favicon korrekt (Link in index.html auf favicon.svg)

---

## Nicht in Scope

- Raster-Formate (PNG, ICO)
- Animiertes Logo
- Mehrere Logo-Varianten (hell/dunkel) — CSS-Variablen übernehmen das
