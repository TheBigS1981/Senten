# Bug Fixes: Diff Paragraph Loss, LLM Token Anzeige, History Deduplication

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Drei Bugs beheben: (B) Absätze verschwinden nach Diff-Toggle, (C) LLM-Token-Summe zeigt 0 im Header, (D) History wird inkonsistent/doppelt gespeichert.

**Architecture:**
- Bug B: Frontend-only fix in `app.js` — `_toggleDiffView` liest Originaltext aus Session-State statt aus DOM-textContent
- Bug C: Backend-fix in `app/routers/usage.py` — LLM-Block immer zurückgeben, unabhängig von `llm_configured`
- Bug D: Frontend + Backend — sessionStorage-Dedup durch server-seitige Dedup ersetzen; Backend prüft auf gleiche Einträge innerhalb eines kurzen Zeitfensters

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Vanilla JS

---

## Bug B — Absätze verschwinden nach Diff-Toggle

### Root Cause

In `_toggleDiffView()` (`static/js/app.js:750-762`) wird beim Ausschalten der Diff-Ansicht der aktuelle Output-Text so gelesen:

```js
const clone = output.cloneNode(true);
clone.querySelectorAll('.diff-removed').forEach(el => el.remove());
const outputText = (clone.textContent || clone.innerText || '').trim();
```

Problem: Wenn Diff aktiv war, enthält `output` HTML-Markup mit `<span>` und `<ins>`/`<del>` Elementen. `textContent` auf einem HTML-Element gibt den **verketteten Text aller Kind-Knoten ohne Trennzeichen** zurück — Absätze (durch `\n` im Original) werden nicht wiederhergestellt, weil Inline-Spans keine Block-Breaks erzeugen.

Dann wird `output.textContent = outputText` gesetzt — und der Text ist einzeilig, alle Absätze sind weg.

### Fix

Statt den Text aus dem DOM zu rekonstruieren, den Originaltext aus `this.state.writeSession.targetText` verwenden. Dieser wird beim Abschluss der Optimierung korrekt gespeichert (mit Zeilenumbrüchen). Fallback: DOM-Extraktion nur wenn Session leer ist.

---

### Task 1: Bug B — Fix `_toggleDiffView` in app.js

**Files:**
- Modify: `static/js/app.js` (Funktion `_toggleDiffView`, ca. Zeile 738)

**Warum:** `textContent` entfernt Zeilenumbrüche aus HTML-Markup. Session-State enthält den korrekten Originaltext.

**Step 1: Lokalisiere die Funktion**

```bash
grep -n "_toggleDiffView\|outputText = " static/js/app.js
```

**Step 2: Ersetze die DOM-Extraktion durch Session-State-Lookup**

Alter Code (Zeilen ~750-760):
```js
const clone = output.cloneNode(true);
clone.querySelectorAll('.diff-removed').forEach(el => el.remove());
const outputText = (clone.textContent || clone.innerText || '').trim();
if (!inputText || !outputText) return;

if (this.state.diffViewEnabled && window.Diff) {
    output.innerHTML = this.renderDiff(inputText, outputText);
} else {
    output.textContent = outputText;
}
```

Neuer Code:
```js
// Use session state as source of truth for the optimized text.
// DOM extraction via textContent strips paragraph breaks from diff HTML markup.
const outputText = (this.state.writeSession && this.state.writeSession.targetText)
    ? this.state.writeSession.targetText
    : (() => {
        // Fallback: extract from DOM, preserving \n from block elements
        const clone = output.cloneNode(true);
        clone.querySelectorAll('.diff-removed').forEach(el => el.remove());
        return (clone.textContent || clone.innerText || '').trim();
    })();
if (!inputText || !outputText) return;

if (this.state.diffViewEnabled && window.Diff) {
    output.innerHTML = this.renderDiff(inputText, outputText);
} else {
    output.textContent = outputText;
}
```

**Step 3: Syntax-Check**

```bash
node --check static/js/app.js
echo "Exit: $?"
```
Expected: `Exit: 0`

**Step 4: CSS rebuild**

```bash
npm run build:css
```

**Step 5: Manueller Test (lokal oder live)**

1. Tab "Optimieren" öffnen
2. Text mit mehreren Absätzen eingeben (z.B. "Absatz 1.\n\nAbsatz 2.\n\nAbsatz 3.")
3. Optimieren klicken
4. Diff-Button einschalten → Diff sichtbar
5. Diff-Button ausschalten → **Absätze müssen erhalten bleiben**

**Step 6: Commit**

```bash
git add static/js/app.js static/css/styles.css
git commit -m "fix(frontend): preserve paragraphs when toggling diff view off

_toggleDiffView() rekonstruierte den Output-Text mit textContent() aus dem
DOM, was bei Diff-Markup (inline spans) alle Zeilenumbrüche entfernte.
Fix: Originaltext aus writeSession.targetText lesen (Source of Truth),
DOM-Extraktion nur als Fallback wenn Session leer ist."
```

---

## Bug C — LLM Token Anzeige zeigt 0

### Root Cause

In `app/routers/usage.py` (Zeile ~130) wird der `llm`-Block nur zurückgegeben wenn `llm_configured = True`:

```python
"llm": {
    "input_tokens": llm_in,
    "output_tokens": llm_out,
}
if llm_configured
else None,
```

`llm_service.is_configured()` prüft ob ein LLM-API-Key in der Konfiguration gesetzt ist. Wenn der Key über LiteLLM läuft (der Key steht in `LLM_API_KEY`, aber `is_configured()` gibt trotzdem False zurück wegen eines Konfigurationsproblems), oder wenn der LLM-Service technisch konfiguriert ist aber `is_configured()` falsch kalibriert ist, werden die Token-Daten aus der DB nie zurückgegeben.

Außerdem: Selbst wenn der User LLM nutzt (Tokens werden in DB gespeichert), soll die Anzeige immer erscheinen, solange Tokens > 0 in der DB sind — unabhängig davon ob der LLM-Service aktuell konfiguriert ist.

### Fix

Backend: `llm`-Block immer zurückgeben (nie `None`). Frontend: keine Änderung nötig, weil `data.llm ? ... : 0` dann immer greift.

---

### Task 2: Bug C — Fix usage.py — LLM-Block immer zurückgeben

**Files:**
- Modify: `app/routers/usage.py` (Zeile ~112-135)
- Test: `tests/test_usage.py`

**Warum:** LLM-Tokens sollen im Header sichtbar sein unabhängig davon ob der LLM-Dienst aktuell konfiguriert ist. Die Daten liegen in der DB — sie sollen immer angezeigt werden.

**Step 1: Finde die betroffene Stelle**

```bash
grep -n "llm_configured\|llm_in\|llm_out" app/routers/usage.py
```

**Step 2: Schreibe zuerst den fehlschlagenden Test**

Füge in `tests/test_usage.py` hinzu:

```python
def test_usage_summary_llm_block_always_present_when_llm_not_configured(client, db_session):
    """llm-Block muss immer im Response enthalten sein, auch wenn LLM nicht konfiguriert."""
    from unittest.mock import patch
    with patch('app.routers.usage.llm_service') as mock_llm:
        mock_llm.is_configured.return_value = False
        response = client.get('/api/usage/summary')
    assert response.status_code == 200
    data = response.json()
    assert 'llm' in data, "llm-Schlüssel fehlt im Response"
    assert data['llm'] is not None, "llm-Wert ist None, sollte Dict sein"
    assert 'input_tokens' in data['llm']
    assert 'output_tokens' in data['llm']
```

**Step 3: Führe den Test aus (erwartet: FAIL)**

```bash
pytest tests/test_usage.py::test_usage_summary_llm_block_always_present_when_llm_not_configured -v
```

**Step 4: Implementiere den Fix**

In `app/routers/usage.py`, ersetze:

```python
    "llm": {
        "input_tokens": llm_in,
        "output_tokens": llm_out,
    }
    if llm_configured
    else None,
```

durch:

```python
    # LLM-Block immer zurückgeben (auch wenn LLM nicht konfiguriert).
    # Tokens werden in der DB gespeichert sobald LLM genutzt wird — sie sollen
    # immer im Header angezeigt werden, unabhängig vom aktuellen Konfigurations-Status.
    "llm": {
        "input_tokens": llm_in,
        "output_tokens": llm_out,
        "configured": llm_configured,
    },
```

**Step 5: Führe alle Tests aus**

```bash
pytest tests/test_usage.py -v
```

Expected: Alle grün inkl. neuer Test.

**Step 6: Frontend — LLM Stats immer anzeigen (auch bei 0 Tokens)**

In `static/js/app.js`, Funktion `_loadUsageSummary()` (~Zeile 2137):

Der Code macht bereits `data.llm ? ... : 0` — das funktioniert jetzt. Aber die `cum-llm-stats` Sichtbarkeit: aktuell wird `cum-llm-stats` initial ohne `display:none` gerendert (HTML zeigt sie immer). Das ist korrekt — kein Frontend-Fix nötig.

**Step 7: Commit**

```bash
git add app/routers/usage.py tests/test_usage.py
git commit -m "fix(api): always return llm token block in usage summary

Vorher wurde llm=null zurückgegeben wenn llm_service.is_configured()
False war. Das verhinderte die Anzeige der 4-Wochen-Token-Summe auch
wenn Tokens in der DB vorhanden waren (z.B. über LiteLLM).

Fix: llm-Block immer zurückgeben. Zusätzlich 'configured'-Flag
hinzugefügt, damit Frontend weiss ob LLM aktuell verfügbar ist.
Neuer Test verifiziert das Verhalten."
```

---

## Bug D — History inkonsistent gespeichert

### Root Cause (ausführlich)

Die History-Speicherung hat zwei Probleme:

**Problem 1: sessionStorage-Dedup ist zu aggressiv**

`_saveSessionToHistory` prüft `sessionStorage.getItem('history_saved_' + session.id)`. Wenn die Session-ID bereits in sessionStorage ist, wird nicht gespeichert. Das ist gut für Duplikate, aber:
- Die Session-ID ist ein Hash von `text + targetLang`
- Wenn `_applyDetectedLang` nach einem Auto-Switch die Session-ID ändert (neues `targetLang`), wird eine neue ID generiert
- Beide IDs (alte und neue) werden im sessionStorage als "gespeichert" markiert
- Bei einer kurzen Folge von Anfragen kann es passieren, dass eine ID als "gespeichert" gilt, obwohl der HTTP-Request noch läuft oder fehlgeschlagen ist

**Problem 2: Keine server-seitige Dedup**

Das Backend hat keine Logik um doppelte Einträge zu verhindern. Bei einem Page-Reload (sessionStorage wird geleert) kann dieselbe Übersetzung doppelt gespeichert werden.

### Fix-Strategie

**Frontend:**
- `sessionStorage`-Dedup bleibt (verhindert Doppel-Saves innerhalb einer Session)
- Zusätzlich: Beim erfolgreichen API-Save den `saveKey` korrekt setzen — NACH dem Response, nicht davor
- Die Logik `sessionStorage.setItem(saveKey, 'true')` wird aus dem Funktions-Anfang NACH den fetch-then-Callbacks verschoben. Wait — das ist ein Race-Condition-Fix in die andere Richtung. Besser: Pessimistisch markieren, aber bei Fehler zurücksetzen (das macht der Code schon).

**Backend (Dedup):**
- History-POST prüft ob in den letzten 60 Sekunden ein identischer Eintrag (gleicher `source_text` + `target_lang` + `operation_type`) für denselben User existiert
- Falls ja: 200 OK zurückgeben ohne neuen Eintrag (idempotent)
- Das verhindert Doppel-Saves nach Page-Reload

**Frontend-Fix (Save-Zuverlässigkeit):**
- Beim `clearTranslate()`/`clearWrite()` die Session *nach* dem API-Save löschen, nicht vorher
- Im `switchTab()` immer speichern wenn `targetText` vorhanden ist (bereits implementiert)
- Beim Button-Click: Session wird bereits nach erfolgreichem Request gespeichert

---

### Task 3: Bug D — Backend Dedup in POST /api/history

**Files:**
- Modify: `app/routers/translate.py` oder wo immer `/api/history` POST definiert ist
- Test: `tests/test_translate.py` oder `tests/test_history.py`

**Step 1: Finde den History-Endpunkt**

```bash
grep -rn "api/history\|router.*history\|@router.*history" app/
```

**Step 2: Schreibe fehlschlagenden Test**

```python
def test_history_post_deduplicates_within_60_seconds(client):
    """Gleicher Eintrag innerhalb von 60 Sek. soll nicht doppelt gespeichert werden."""
    payload = {
        "operation_type": "translate",
        "source_text": "Hello world",
        "target_text": "Hallo Welt",
        "source_lang": "EN",
        "target_lang": "DE",
    }
    r1 = client.post("/api/history", json=payload)
    r2 = client.post("/api/history", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200  # Kein Fehler, aber kein doppelter Eintrag
    
    entries = client.get("/api/history").json()
    matching = [e for e in entries if e["source_text"] == "Hello world" and e["target_lang"] == "DE"]
    assert len(matching) == 1, f"Erwartet 1 Eintrag, gefunden: {len(matching)}"
```

**Step 3: Führe den Test aus (erwartet: FAIL)**

```bash
pytest tests/ -k "test_history_post_deduplicates" -v
```

**Step 4: Implementiere Dedup im History-Endpunkt**

Finde den `POST /api/history` Handler und füge vor dem `db.add(record)` ein:

```python
from datetime import datetime, timezone, timedelta

# Dedup: Verhindere doppelte Einträge innerhalb von 60 Sekunden.
# Schützt gegen Page-Reload und Race-Conditions im Frontend.
cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
existing = db.query(HistoryRecord).filter(
    HistoryRecord.user_id == user_id,
    HistoryRecord.operation_type == request.operation_type,
    HistoryRecord.source_text == request.source_text,
    HistoryRecord.target_lang == request.target_lang,
    HistoryRecord.created_at >= cutoff,
).first()
if existing:
    logger.debug(f"[History] Duplicate suppressed for user {user_id} (within 60s window)")
    return existing  # Idempotent: gleiches Objekt zurückgeben
```

**Step 5: Führe alle Tests aus**

```bash
pytest --tb=short -q
```

Expected: Alle bisherigen Tests grün + neuer Test grün.

**Step 6: Commit**

```bash
git add app/ tests/
git commit -m "fix(history): deduplicate entries within 60-second window

Server-seitige Dedup verhindert doppelte History-Einträge bei Page-Reload
(sessionStorage wird geleert) oder Frontend-Race-Conditions. Gleicher
Eintrag (source_text + target_lang + operation_type) innerhalb von 60s
wird nicht doppelt gespeichert — stattdessen wird der existierende
Eintrag idempotent zurückgegeben."
```

---

### Task 4: Bug D — Frontend Session-Save zuverlässiger machen

**Files:**
- Modify: `static/js/app.js`

**Warum:** Auch mit Backend-Dedup sollte das Frontend robust sein. Konkret: Beim `clearTranslate()` wird `_saveSessionToHistory('translate')` (ohne `skipAgeCheck=true`) aufgerufen — das bedeutet bei einer Session jünger als 3 Sekunden wird NICHT gespeichert. Das ist ein stilles Verlorengehen.

**Step 1: Lokalisiere clearTranslate und clearWrite**

```bash
grep -n "clearTranslate\|clearWrite\|_saveSessionToHistory" static/js/app.js | head -20
```

**Step 2: Ändere clearTranslate und clearWrite**

In `clearTranslate()` (~Zeile 1693):
```js
// ALT:
this._saveSessionToHistory('translate');
// NEU (skipAgeCheck=true, damit auch neue Sessions gespeichert werden):
this._saveSessionToHistory('translate', true);
```

In `clearWrite()` (~Zeile 1739):
```js
// ALT:
this._saveSessionToHistory('write');
// NEU:
this._saveSessionToHistory('write', true);
```

**Step 3: Syntax-Check**

```bash
node --check static/js/app.js && echo "OK"
```

**Step 4: CSS rebuild**

```bash
npm run build:css
```

**Step 5: Commit**

```bash
git add static/js/app.js static/css/styles.css
git commit -m "fix(frontend): always save history on clear, skip age check

clearTranslate/clearWrite riefen _saveSessionToHistory ohne skipAgeCheck
auf. Sessions jünger als 3 Sekunden wurden still verworfen. Da 'Löschen'
eine explizite Benutzeraktion ist (kein Auto-Save), soll die Session immer
gespeichert werden wenn Source- und Target-Text vorhanden sind."
```

---

## Task 5: CHANGELOG und STATUS.md aktualisieren

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/STATUS.md`

**Step 1: CHANGELOG.md**

Füge unter `[Unreleased]` (oder erstelle neuen Eintrag) hinzu:

```markdown
### Fixed
- **Bug B**: Diff-Toggle entfernte Absätze — `_toggleDiffView()` liest jetzt Originaltext
  aus `writeSession.targetText` statt aus `DOM.textContent` (das Zeilenumbrüche in HTML verliert)
- **Bug C**: LLM-Token-Anzeige zeigte 0 — `GET /api/usage/summary` gibt jetzt immer den
  `llm`-Block zurück, unabhängig davon ob LLM aktuell konfiguriert ist
- **Bug D**: History-Doppeleinträge — Backend dedupliziert identische Einträge innerhalb von
  60 Sekunden; Frontend speichert auch beim Löschen ohne Age-Check
```

**Step 2: docs/STATUS.md**

Aktualisiere "Recent Decisions" und "Completed This Week".

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/STATUS.md
git commit -m "docs: document bug fixes B/C/D in changelog and status"
```

---

## Finale Verifikation

```bash
# Alle Tests grün
pytest --tb=short -q

# Syntax-Check
node --check static/js/app.js

# Push
git push
```

Dann live im Browser verifizieren:
1. Bug B: Optimieren mit mehrzeiligem Text → Diff an → Diff aus → Absätze intakt
2. Bug C: LLM-Anfrage machen → Header zeigt Tokens (nicht 0)
3. Bug D: Übersetzen → Tab wechseln → Verlauf prüfen → Eintrag vorhanden und einfach
