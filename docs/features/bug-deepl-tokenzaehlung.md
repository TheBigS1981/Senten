# Bug: DeepL Tokenzählung ist selbst berechnet, nicht von der DeepL API

**Status:** Open  
**Erstellt:** 2026-03-01  
**Typ:** Bug (falsche Datenquelle / Anforderungsverletzung)  
**Priorität:** Medium — funktional korrekte Anzeige, aber falsche Datenquelle  
**Betrifft:** `app/routers/translate.py` (`_record_usage`), `app/models/schemas.py`, Frontend-Stats  

---

## Symptom

Die Anzeige "X Zeichen" in der Output-Stats-Bar (unterhalb des Übersetzungsfeldes) zeigt die **Länge des Eingabetexts** an — nicht die tatsächlich von DeepL **abgerechneten Zeichen** (`billed_characters`), die das DeepL SDK im Response zurückgibt.

Beispiel:
- Eingabe: `"Hello World"` (11 Zeichen)
- Angezeigt: `11` (self-counted)
- DeepL API gibt intern zurück: z.B. `12` (DeepL zählt manchmal abweichend, z.B. durch interne Normalisierung)

---

## Root-Cause-Analyse

### Wo das Problem entsteht

**`app/routers/translate.py` — `_record_usage()`:**

```python
def _record_usage(user_id, text, operation_type, target_language, double_characters=False):
    chars_used = len(text) * (2 if double_characters else 1)  # ← Selbst berechnet!
    usage_service.record_usage(...)
    return chars_used  # ← Dieser Wert geht in die API-Response
```

Die Zeichenanzahl wird mit `len(text)` selbst berechnet. Das DeepL SDK gibt bei jeder Übersetzung tatsächlich **billed characters** zurück:

```python
# deepl SDK: result.billed_characters (vorhanden seit SDK v1.x)
result = self._translator.translate_text(...)
result.billed_characters  # ← tatsächlich abgerechnete Zeichen
```

### Warum das falsch ist

1. **Anforderung war**: Zeichenzählung aus DeepL-Response (tatsächlich verbrauchte Zeichen)
2. **DeepL zählt intern abweichend**: Tags, Whitespace, Encoding-Normalisierung können die Zahl leicht verändern
3. **Doppel-Übersetzung (write)**: `double_characters=True` ist eine grobe Schätzung — real werden die Zeichen zweier separater Calls addiert
4. **Mock-Modus**: Im Mock-Modus ist `len(text)` akzeptabel, aber das sollte klar unterschieden werden

---

## Fix-Plan

### Fix A — DeepL SDK `billed_characters` zurückgeben (Backend)

**`app/services/deepl_service.py` — `translate()` anpassen:**

```python
result = self._translator.translate_text(**kwargs)
return {
    "text": result.text,
    "detected_source": detected,
    "billed_characters": getattr(result, "billed_characters", len(text)),  # Fallback
}
```

**`app/services/deepl_service.py` — `write_optimize()` anpassen:**

```python
result1 = self._translator.translate_text(**fwd_kwargs)
result2 = self._translator.translate_text(**bwd_kwargs)
total_billed = (
    getattr(result1, "billed_characters", len(text)) +
    getattr(result2, "billed_characters", len(result1.text))
)
return {"text": result2.text, "detected_lang": detected, "billed_characters": total_billed}
```

**`app/routers/translate.py` — `_record_usage()` anpassen:**

```python
def _record_usage(user_id, text, operation_type, target_language, billed_characters=None):
    chars_used = billed_characters if billed_characters is not None else len(text)
    usage_service.record_usage(...)
    return chars_used
```

**Aufruf im Router:**

```python
result = deepl_service.translate(...)
chars_used = _record_usage(
    user_id, text, "translate", body.target_lang,
    billed_characters=result.get("billed_characters")
)
```

### Fix B — Schema anpassen

`billed_characters` in `TranslateResponse` und `WriteResponse` umbenennen zu `characters_used` (bereits vorhanden) — kein Breaking Change. Intern wird aber jetzt der echte Wert übermittelt.

### Fix C — Mock-Modus

Im Mock-Modus weiterhin `len(text)` verwenden (kein SDK-Response verfügbar). Das Mock-Ergebnis klar als Schätzung kennzeichnen.

---

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `app/services/deepl_service.py` | `translate()` + `write_optimize()` geben `billed_characters` zurück |
| `app/routers/translate.py` | `_record_usage()` nimmt `billed_characters` Parameter; Router übergibt Wert aus SDK-Result |
| `tests/test_deepl_service.py` | Tests für `billed_characters` im Return-Dict |
| `tests/test_translate.py` | Tests prüfen `characters_used` === `billed_characters` (nicht `len(text)`) |

---

## Akzeptanzkriterien

- [ ] `characters_used` in der API-Response entspricht dem `billed_characters`-Wert aus dem DeepL SDK
- [ ] Im Mock-Modus: `characters_used` = `len(text)` (Fallback, akzeptabel)
- [ ] `write_optimize` summiert `billed_characters` beider Calls
- [ ] Bestehende Tests grün; neue Tests für `billed_characters`-Propagation
- [ ] Frontend-Anzeige zeigt dadurch automatisch den korrekten Wert (keine Frontend-Änderung nötig)

---

## Hinweis: DeepL SDK-Kompatibilität

Das Attribut `billed_characters` ist seit DeepL SDK v1.3+ verfügbar. Die aktuelle Anforderung pinnt `deepl` ohne explizite Mindestversion — sollte geprüft werden.

```python
# requirements.txt aktuell:
deepl==1.17.0  # ← billed_characters ist vorhanden
```
