# Bug: LLM — Zwischenübersetzung auf Deutsch sichtbar vor finaler Ausgabe

**Status:** Open  
**Erstellt:** 2026-03-01  
**Typ:** Bug (UX / Sichtbares Artefakt)  
**Priorität:** High — sichtbarer UX-Bruch bei jeder LLM-Nutzung  
**Betrifft:** `static/js/app.js` (`_applyDetectedLang`), `app/services/llm_service.py` (write_optimize)  

---

## Symptom

Bei LLM-Übersetzen **und** LLM-Optimieren erscheint kurzzeitig eine **deutsche Zwischenversion** im Output-Feld, bevor die tatsächliche Übersetzung/Optimierung angezeigt wird.

Beispiel: Text auf Englisch → Zielsprache Englisch → kurz erscheint "Dieser Text handelt von..." (Deutsch) → danach "This text is about..."

---

## Root-Cause-Analyse

### Ursache 1 — `_applyDetectedLang` löst Re-Translation aus (Translate-Tab)

In `_applyDetectedLang()` (app.js, Zeile ~1032) wird bei automatischer Spracherkennung die **Zielsprache gewechselt** und danach `this.translate()` erneut aufgerufen. Dieser zweite Call gibt zunächst einen leeren Output aus und füllt ihn dann mit der re-translated Version — zwischenzeitlich flackert das Outputfeld.

```javascript
// app.js ~1068
this.translate(); // ← löst einen zweiten vollständigen LLM-Streaming-Request aus
```

Das erste Streaming-Result ist häufig eine Übersetzung ins Deutsche (Default-Zielsprache), **weil die Sprache beim ersten Call noch nicht erkannt war**. Erst im zweiten Call wird in die richtige Sprache übersetzt.

### Ursache 2 — DeepL write_optimize: Zwischenübersetzung sichtbar (Write-Tab)

Die DeepL-Doppelübersetzung (`write_optimize`) übersetzt intern zuerst in eine Zwischensprache (z.B. EN→DE→EN). Das Backend gibt nur das Endresultat zurück — **das ist korrekt und nicht das Problem für DeepL**.

Beim LLM-Streaming-Write-Mode (`/api/write/stream`) streamt der LLM das Ergebnis direkt. Wenn die Sprache noch nicht bekannt ist, sendet der Frontend-Code initial `target_lang: 'DE'` (Default), obwohl der Text auf Englisch ist. Das führt dazu, dass das LLM kurz eine deutsche Version ausgibt, bis `_applyDetectedLang` eingreift und neu startet.

### Kern-Problem: Spracherkennung kommt NACH dem ersten Request

Der Flow ist:
1. User tippt Text → Frontend kennt Sprache noch nicht
2. `translate()` / `write()` startet mit `target_lang: 'DE'` (Default)
3. LLM übersetzt → gibt Deutsch-Ergebnis aus (sichtbar im Output)
4. SSE-Event `detected_source_lang` kommt → Sprache erkannt
5. `_applyDetectedLang()` korrigiert Zielsprache → zweiter Request startet
6. Zweiter Request übersetzt korrekt

---

## Lösungsansätze

### Lösung A — Output erst nach Sprach-Commit anzeigen (Frontend, empfohlen)

Beim Streaming: Output **nicht sofort** in `output.value` schreiben, sondern in einem **Buffer** halten. Erst wenn `detected_source_lang` im SSE-Stream ankam UND keine Re-Translation nötig ist, wird der Buffer in das Output-Feld geschrieben.

```javascript
// Pseudocode:
let buffer = '';
let langConfirmed = false;

// Bei chunk-Event:
buffer += event.chunk;
if (langConfirmed) output.value = buffer;

// Bei done-Event (mit detected_source_lang):
detected = event.detected_source_lang;
const needsRetry = shouldAutoSwitch(detected);
if (!needsRetry) {
    output.value = buffer; // Erst jetzt anzeigen
    langConfirmed = true;
} else {
    buffer = '';
    output.value = '';
    // Starte zweiten Request mit korrekter Zielsprache
}
```

**Nachteil**: Der User sieht nichts, bis der erste Request fertig ist — kein progressives Streaming. Bei kurzen Texten ist das OK (< 1s), bei langen Texten spürbar.

### Lösung B — Sprache vorab ermitteln (Backend, robuster)

Vor dem eigentlichen LLM-Call **kurz** die Eingabesprache erkennen — entweder:
- Durch einen kleinen Vorab-LLM-Call (`detect_language()` — existiert bereits im Backend)
- Oder durch `langdetect` Python-Bibliothek (kein LLM, sehr schnell, ~5ms)

Dann mit der korrekten Zielsprache **direkt** den einzigen LLM-Call starten. Kein zweiter Request.

```python
# Pseudocode Backend:
if not source_lang:
    detected = await llm_service.detect_language(text)
    # Wenn detected == target_lang: Zielsprache wechseln (z.B. DE→EN-US)
    target_lang = adjust_target_for_detected(detected, target_lang)
```

**Nachteil**: Zusätzlicher LLM-Call oder neue Dependency (`langdetect`).

### Lösung C — Default-Zielsprache aus Benutzerprofil (kurzfristiger Workaround)

Wenn das Benutzerprofil bereits eine bevorzugte Quellsprache enthält, diese für den ersten Request verwenden → weniger Fehlversuche.

---

## Empfehlung

**Lösung A** (Buffer im Frontend) für Streaming-Tab, kombiniert mit dem bereits vorhandenen `shouldAutoSwitch`-Check. Die Anzeige verzögert sich minimal, aber es gibt kein sichtbares Flackern.

Für den non-streaming Write-Tab ist das Problem weniger akut, da kein progressives Rendering existiert.

---

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `static/js/app.js` | `_translateLLMStream()` — Buffer-Logik vor Output-Anzeige |
| `static/js/app.js` | `_writeLLMStream()` (falls vorhanden) — analog |
| `app/services/llm_service.py` | Optional: `detect_language()` für Lösung B |

---

## Akzeptanzkriterien

- [ ] Kein deutsches Zwischenergebnis sichtbar wenn Eingabesprache ≠ Deutsch
- [ ] Streaming funktioniert weiterhin (Output erscheint progressiv oder gesammelt — kein leerer Zustand)
- [ ] Zweiter Re-Translation-Request wird nur noch ausgelöst wenn wirklich nötig
- [ ] Kein neuer Bug: Wenn Eingabe tatsächlich Deutsch ist, wird korrekt auf EN übersetzt

---

## Testplan

- Manueller Test: Englischen Text eingeben → LLM-Modus → kein Deutsch im Output
- Unit-Test für `_applyDetectedLang`-Logik (Frontend-Test mit Jest — optional)
