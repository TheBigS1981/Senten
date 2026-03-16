# Bug: Verlaufsspeicherung unzuverlässig (Race Conditions, verlorene Einträge)

**Status:** Open  
**Erstellt:** 2026-03-01  
**Typ:** Bug (Nebenläufigkeit / Race Condition)  
**Priorität:** Medium — betrifft Datenkonsistenz, aber kein Datenverlust  
**Betrifft:** `static/js/app.js` (`_saveSessionToHistory`, `_generateSessionId`), `app/routers/history.py`  

---

## Symptom

Nicht alle Übersetzungen/Optimierungen landen im Verlauf. Einträge fehlen insbesondere bei:
- Schnell aufeinanderfolgenden Eingaben (Tipp-Debounce feuert mehrfach)
- Tab-Wechseln direkt nach einer Übersetzung
- Seiten-Reload kurz nach Abschluss einer Übersetzung
- LLM-Streaming (Output baut sich verzögert auf, Session wird zu früh als "ohne targetText" bewertet)

---

## Root-Cause-Analyse

### Problem 1 — Session-ID basiert nur auf Text, nicht auf Zeitpunkt

`_generateSessionId(text)` erzeugt einen Hash **nur über den Quelltext**. Wenn der User denselben Text mehrfach übersetzt (z.B. mit verschiedenen Zielsprachen), erkennt das System das als "gleiche Session" und speichert den zweiten Eintrag nicht (Deduplizierung via `sessionStorage`).

```javascript
// app.js ~650
const saveKey = `history_saved_${session.id}`;
if (sessionStorage.getItem(saveKey)) return; // ← blockiert legitime Doppelübersetzungen
```

### Problem 2 — `targetText` bei Streaming-Ende nicht garantiert gesetzt

Bei LLM-Streaming wird `session.targetText` erst nach Abschluss des SSE-Streams gesetzt. Wenn `_applyDetectedLang` einen zweiten Request auslöst und `_saveSessionToHistory` zwischen den zwei Requests aufgerufen wird, ist `targetText` leer → kein Save.

```javascript
// Timing-Problem:
// 1. Streaming-Request 1 fertig → targetText noch leer (zweiter Request startet)
// 2. _saveSessionToHistory aufgerufen → targetText === '' → kein Save
// 3. Streaming-Request 2 fertig → targetText gesetzt → aber kein Save mehr ausgelöst
```

### Problem 3 — Race: Tab-Wechsel löst Save aus, aber targetText noch nicht gesetzt

```javascript
// switchTab():
this._saveSessionToHistory(this.state.activeTab, true); // skipAgeCheck=true
```

Wenn der User den Tab wechselt während der Streaming-Request noch läuft, ist `targetText` möglicherweise noch leer → kein Save.

### Problem 4 — `beforeunload` / Seiten-Reload nicht abgedeckt

Beim Reload oder Browser-Schließen gibt es keinen `beforeunload`-Handler. Sessions die noch nicht gespeichert wurden, gehen verloren.

### Problem 5 — `sessionStorage` geht beim Reload verloren

`sessionStorage` wird pro Browser-Tab gehalten und beim Reload geleert. Wenn eine Session als "bereits gespeichert" markiert war (`history_saved_xxx`), aber der Server-Request fehlgeschlagen ist und der User dann einen Reload macht, fehlt der Eintrag permanent.

---

## Fix-Plan

### Fix A — Save nach Streaming-Abschluss (zuverlässigster Trigger)

Statt `_saveSessionToHistory` an vielen Stellen aufzurufen, **nur nach erfolgreichem Abschluss** eines Requests speichern:

```javascript
// Am Ende von _translateLLMStream(), _translateDeepL(), _writeLLMStream(), _writeDeepL():
if (data.translated_text || accumulated) {
    session.targetText = data.translated_text || accumulated;
    this._saveSessionToHistory('translate');
}
```

### Fix B — Session-ID auf Text + Zielsprache erweitern

Um legitime Doppelübersetzungen desselben Texts in verschiedene Sprachen zu erlauben:

```javascript
_generateSessionId(text, targetLang) {
    const key = `${text}::${targetLang}`;
    // ... hash über key statt nur text
}
```

### Fix C — `beforeunload` Handler für offene Sessions

```javascript
window.addEventListener('beforeunload', () => {
    // Synchron via sendBeacon (kein await möglich in beforeunload)
    const session = this.state.translateSession;
    if (session.id && session.targetText) {
        navigator.sendBeacon('/api/history', JSON.stringify({...}));
    }
});
```

`navigator.sendBeacon` ist für diesen Zweck spezifiziert und wird auch beim Schließen zugestellt.

### Fix D — Backend: Deduplizierung statt Frontend-sessionStorage

Statt Deduplizierung im Frontend über `sessionStorage` (die beim Reload verloren geht): Backend gibt bei Doppel-POST desselben Eintrags (gleicher Hash von source+target+lang) einen 200 mit dem bestehenden Eintrag zurück statt 201 — idempotent.

---

## Empfohlene Priorität der Fixes

| Fix | Aufwand | Impact |
|-----|---------|--------|
| A — Save nach Abschluss | Mittel | Hoch — behebt Problem 2+3 |
| B — Session-ID mit Zielsprache | Gering | Medium — behebt Problem 1 |
| C — beforeunload sendBeacon | Gering | Low — edge case |
| D — Backend-Idempotenz | Mittel | Medium — behebt Problem 5 |

---

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `static/js/app.js` | `_saveSessionToHistory`, `_generateSessionId`, Save-Trigger nach Request-Abschluss |
| `app/routers/history.py` | Optional: Idempotenz-Logik |
| `tests/test_translate.py` | Neue Tests für History-Save-Trigger |

---

## Akzeptanzkriterien

- [ ] Jede vollständige Übersetzung/Optimierung erscheint im Verlauf
- [ ] Gleicher Text mit verschiedenen Zielsprachen erzeugt separate Verlaufseinträge
- [ ] Tab-Wechsel während laufendem Request verliert keinen Eintrag
- [ ] Seiten-Reload nach Übersetzung verliert keinen Eintrag (via sendBeacon oder Backend-Idempotenz)
- [ ] Keine Doppeleinträge für identische Übersetzungen (gleicher Text + Zielsprache + Ergebnis)
