# Bug: LLM-Ausgabe hat fehlende Leerzeichen zwischen Wörtern

**Status:** Open  
**Erstellt:** 2026-03-01  
**Typ:** Bug (Regression / persistenter Fehler)  
**Priorität:** High — sichtbarer Qualitätsmangel bei jeder LLM-Nutzung  
**Betrifft:** `app/services/llm_service.py` (`_strip_markdown`), `app/config.py` (Prompts)  

---

## Symptom

Die LLM-Ausgabe (Übersetzen und Optimieren) enthält zusammengeschriebene Wörter ohne Leerzeichen, z.B.:

- `"DieseAufgabeistinteressant"` statt `"Diese Aufgabe ist interessant"`
- `"Stuttgart'sMostBeautiful"` statt `"Stuttgart's Most Beautiful"`
- `"Buildings:18thCentury"` statt `"Buildings: 18th Century"`

Das Problem tritt trotz bereits vorhandener Post-Processing-Logik in `_strip_markdown()` und trotz expliziter Verbote im Prompt auf.

---

## Root-Cause-Analyse

### Bekannter Kontext

In v2.6.1 und v2.7.3 wurden bereits Fixes eingebaut:
- `_strip_markdown()` hat Schritte für CamelCase, Kolon-Digit-Pattern, Possessiv+Großbuchstabe
- Prompts verbieten explizit Leerzeichen-Fehler mit WRONG/CORRECT-Beispielen

Das Problem **persistiert**, was auf eine unvollständige Post-Processing-Regex-Abdeckung hinweist.

### Kategorien fehlender Leerzeichen (vermutlich)

| Muster | Beispiel | Aktuell gefixt? |
|--------|----------|-----------------|
| CamelCase zwischen Wörtern | `DieseAufgabe` | Teilweise — nur ASCII |
| Nach Komma ohne Leerzeichen | `eins,zwei,drei` | Nein |
| Vor Klammer | `Text(Erklärung)` | Nein |
| Nach schließender Klammer | `(Text)und` | Nein |
| Zahl direkt an Buchstabe | `100kg` oder `5Personen` | Nein |
| Punkt/Ausrufezeichen ohne Leerzeichen | `Satz.Nächster` | Teilweise |
| Gedankenstrich ohne Leerzeichen | `Text-kein` (Bindestrich ok, Gedankenstrich nicht) | Nein |
| Nicht-ASCII CamelCase | `NervöseBörsen` → `Nervöse Börsen` | In v2.7.1 eingebaut |
| Bindestriche fälschlicherweise entfernt | `wohl-bekannt` | Risiko bei Over-Correction |

### Problem mit CamelCase-Regex und Unicode

Die aktuelle Regex für CamelCase-Splitting verwendet `[A-Z]` (nur ASCII-Großbuchstaben). Deutschen Texten mit Umlauten (`Ä`, `Ö`, `Ü`) werden nicht korrekt erkannt:
- `"ÄnderungenInDeutschland"` → nicht gesplittet

---

## Fix-Plan

### Fix A — `_strip_markdown()` erweitern (Backend)

Neue Regex-Schritte in `llm_service.py`:

```python
# Komma/Semikolon ohne folgendes Leerzeichen vor Buchstabe
text = re.sub(r'([,;])([^\s\d])', r'\1 \2', text)

# Klammer auf/zu ohne Leerzeichen
text = re.sub(r'([^\s])\(', r'\1 (', text)
text = re.sub(r'\)([^\s\.,;!?])', r') \1', text)

# Zahl direkt gefolgt von Buchstabe (50kg → 50 kg), außer Einheiten die zusammengehören
text = re.sub(r'(\d)([A-Za-zÄÖÜäöüß])', r'\1 \2', text)

# Buchstabe direkt gefolgt von Zahl, wenn kein Bindestrich (Text5 → Text 5)
text = re.sub(r'([A-Za-zÄÖÜäöüß])(\d)', r'\1 \2', text)

# CamelCase mit Unicode-Support (Großbuchstaben inkl. Umlaute)
text = re.sub(r'([a-zäöüß])([A-ZÄÖÜ])', r'\1 \2', text)
```

**Wichtig**: Reihenfolge der Regexes sorgfältig prüfen — Bindestriche in zusammengesetzten Wörtern (`wohl-bekannt`, `E-Mail`) dürfen nicht aufgebrochen werden.

### Fix B — Prompt-Verbesserung (config.py)

Weitere konkrete WRONG/CORRECT-Beispiele für Umlaute und Sonderzeichen:
```
- WRONG: "ÄnderungInDeutschland"  → CORRECT: "Änderung In Deutschland"
- WRONG: "eins,zwei"              → CORRECT: "eins, zwei"
- WRONG: "Text(Erklärung)"        → CORRECT: "Text (Erklärung)"
```

### Fix C — Unit-Tests für alle Regex-Patterns

```python
# tests/test_llm_service.py
@pytest.mark.parametrize("input,expected", [
    ("eins,zwei", "eins, zwei"),
    ("Text(Erklärung)", "Text (Erklärung)"),
    ("50kg", "50 kg"),
    ("ÄnderungInDeutschland", "Änderung In Deutschland"),
    ("Satz.Nächster", "Satz. Nächster"),
])
def test_strip_markdown_spacing(input, expected):
    assert _strip_markdown(input) == expected
```

---

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `app/services/llm_service.py` | `_strip_markdown()` — neue Regex-Schritte |
| `app/config.py` | Prompt-Ergänzungen für weitere WRONG/CORRECT-Beispiele |
| `tests/test_llm_service.py` | Parametrisierte Unit-Tests für alle Spacing-Patterns |

---

## Akzeptanzkriterien

- [ ] Alle bekannten Leerzeichen-Muster sind durch Unit-Tests abgedeckt und grün
- [ ] Kein bestehender Test bricht durch die neuen Regexes
- [ ] Bindestriche in Komposita (`E-Mail`, `wohl-bekannt`) bleiben erhalten
- [ ] Unicode-Großbuchstaben (Ä, Ö, Ü) werden im CamelCase korrekt erkannt

---

## Risiken

- **Over-Correction**: Zu aggressive Leerzeichen-Regeln können gültige Zeichenkombinationen aufbrechen (z.B. `E-Mail` → `E- Mail`). Muss durch Tests abgesichert werden.
- **Performance**: Jede neue Regex läuft über den gesamten Output — bei langen Texten ggf. messbar, aber vernachlässigbar.
