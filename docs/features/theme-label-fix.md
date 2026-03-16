# Feature: Theme-Label korrigieren bei Custom-Akzentfarbe

**Status:** Done  
**Erstellt:** 2026-02-28  
**Erstellt von:** @deep-thinker  
**Ziel-Version:** TBD (Bugfix, vermutlich Patch)

---

## Übersicht

Das Theme-Dropdown im Header zeigt den Namen des vordefinierten Themes an, z.B. "Dunkel (Blau)". Wenn der User jedoch eine eigene Akzentfarbe per Color Picker definiert hat, ist der Farbname im Label (z.B. "Blau") falsch bzw. irreführend. Das Label sollte in diesem Fall anzeigen, dass eine individuelle Farbe aktiv ist.

---

## Anforderungen

### Funktionale Anforderungen

1. **Label-Aktualisierung bei Custom-Akzentfarbe**
   - [ ] Wenn eine Custom-Akzentfarbe gesetzt ist, wird der Farbname durch "Individuell" (oder ähnlich) ersetzt
   - [ ] Beispiel: "Dunkel (Blau)" → "Dunkel (Individuell)" wenn Custom-Farbe aktiv
   - [ ] Beispiel: "Hell (Violett)" → "Hell (Individuell)" wenn Custom-Farbe aktiv

2. **Label-Wiederherstellung beim Reset**
   - [ ] Wenn die Custom-Akzentfarbe zurückgesetzt wird (Reset-Button), kehrt das Label zum ursprünglichen Theme-Namen zurück
   - [ ] Beispiel: "Dunkel (Individuell)" → "Dunkel (Blau)" nach Reset

3. **Korrekte Anzeige bei Seitenreload**
   - [ ] Beim Laden der Seite wird geprüft, ob eine Custom-Farbe in localStorage gespeichert ist
   - [ ] Falls ja: Label zeigt "(Individuell)" statt den Theme-Farbnamen

---

## Nicht in Scope

- Änderung der Theme-IDs oder der Dropdown-Optionsliste
- Anzeige des konkreten Farbnamens (z.B. "Dunkel (#ff5500)") — "Individuell" reicht
- Änderung am Color Picker selbst

---

## Technische Spezifikation

### Betroffene Dateien

| Datei | Art der Änderung |
|-------|-----------------|
| `static/js/app.js` | `applyTheme()` — Label-Logik erweitern (Zeilen ~114–124) |

### Aktuelle Logik (app.js, Zeile 114–124)

```javascript
const labels = {
    'light-blue':   { icon: 'fas fa-sun',  text: 'Hell (Blau)' },
    'dark-blue':    { icon: 'fas fa-moon', text: 'Dunkel (Blau)' },
    'light-violet': { icon: 'fas fa-sun',  text: 'Hell (Violett)' },
    'dark-violet':  { icon: 'fas fa-moon', text: 'Dunkel (Violett)' },
};
const meta  = labels[themeId] || labels['light-blue'];
// ...
if (label) label.textContent = meta.text;
```

### Gewünschte Logik

```javascript
const labels = {
    'light-blue':   { icon: 'fas fa-sun',  text: 'Hell (Blau)',    customText: 'Hell (Individuell)' },
    'dark-blue':    { icon: 'fas fa-moon', text: 'Dunkel (Blau)',   customText: 'Dunkel (Individuell)' },
    'light-violet': { icon: 'fas fa-sun',  text: 'Hell (Violett)',  customText: 'Hell (Individuell)' },
    'dark-violet':  { icon: 'fas fa-moon', text: 'Dunkel (Violett)',customText: 'Dunkel (Individuell)' },
};
const meta = labels[themeId] || labels['light-blue'];
const hasCustomAccent = !!localStorage.getItem('accent-custom');
if (label) label.textContent = hasCustomAccent ? meta.customText : meta.text;
```

Alternativ einfacher: den Modus-Teil ("Hell"/"Dunkel") extrahieren und den Farbteil dynamisch setzen.

---

## Akzeptanzkriterien

- [ ] Bei aktiver Custom-Akzentfarbe zeigt das Header-Label "(Individuell)" statt "(Blau)"/"(Violett)"
- [ ] Nach Reset der Akzentfarbe wird der ursprüngliche Theme-Name wiederhergestellt
- [ ] Beim Seitenreload mit gespeicherter Custom-Farbe wird "(Individuell)" korrekt angezeigt
- [ ] Ctrl+D (Hell/Dunkel-Wechsel) behält "(Individuell)" bei wenn Custom-Farbe aktiv

---

## Decisions Made

_Keine — Feature ist in der Planungsphase._

---

## Progress Log

- [2026-02-28] @deep-thinker — Feature-Request erstellt — next: Implementierung (reines Frontend, ~10 Zeilen JS)
- [2026-03-01] @build — Implementiert: `customText`-Feld zu `labels`-Objekt ergänzt; `label.textContent` nutzt jetzt `customAccent`-Parameter direkt (kein extra localStorage-Zugriff nötig, da Parameter bereits vorhanden) — 301 Tests grün

---

## Testing Notes

- Manuell: Theme wechseln → Custom-Farbe setzen → Label prüfen
- Manuell: Custom-Farbe resetten → Label prüft zurück auf Theme-Name
- Manuell: Seite neu laden mit Custom-Farbe → Label korrekt
- Manuell: Ctrl+D mit Custom-Farbe → "(Individuell)" bleibt
- Kein Backend-Test nötig (reine Frontend-Änderung)
