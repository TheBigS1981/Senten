# Usage Statistics (Words + LLM Tokens) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Track and display cumulative word counts (translated/optimized) and LLM token usage for the last 4 weeks. Replace the broken DeepL character/token display with this new system.

**Architecture:** 
- Backend: Extend UsageRecord model with word_count + token fields, new `/api/usage/summary` endpoint
- Frontend: New top stats bar showing cumulative 4-week stats, tooltip on hover
- DeepL token/cost display is REMOVED entirely (as requested)

**Tech Stack:** Python/SQLAlchemy (migration + endpoint), Vanilla JS, CSS

---

## Task 1: Database Migration — Add word_count and token fields

**Files:**
- Modify: `app/db/models.py`
- Create: `alembic/versions/` (SQLAlchemy migration)

**Kontext:** UsageRecord currently only has `characters_used`. We need:
- `word_count` (Integer) — words in source text
- `input_tokens` (Integer) — LLM input tokens (0 for DeepL)
- `output_tokens` (Integer) — LLM output tokens (0 for DeepL)

**Schritt 1: Modell erweitern**

In `app/db/models.py`, UsageRecord:
```python
characters_used = Column(Integer, nullable=False)
word_count = Column(Integer, nullable=False, default=0)  # NEW
input_tokens = Column(Integer, nullable=False, default=0)  # NEW
output_tokens = Column(Integer, nullable=False, default=0)  # NEW
```

**Schritt 2: Migration erstellen**

```bash
alembic revision --autogenerate -m "add word_count and token fields to usage_records"
```

**Schritt 3: Commit**

```bash
git add app/db/models.py alembic/versions/
git commit -m "feat(usage): add word_count and token fields to UsageRecord"
```

---

## Task 2: Backend — Update _record_usage() to accept word_count and tokens

**Files:**
- Modify: `app/services/usage_service.py` (Funktion `_record_usage`)

**Kontext:** Die Funktion muss die neuen Felder speichern. Rufer sind:
- `app/services/deepl_service.py` → übergibt characters, muss word_count ergänzen
- `app/services/llm_service.py` → übergibt bereits tokens, muss ans Backend weitergeben

**Schritt: Parameter erweitern**

```python
def _record_usage(
    user_id: str,
    characters_used: int,
    operation_type: str,
    target_language: str | None = None,
    word_count: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
):
    # ... existing code ...
    # Add: record.word_count = word_count
    # Add: record.input_tokens = input_tokens
    # Add: record.output_tokens = output_tokens
```

**Schritt 2: DeepL Service anpassen**

In `deepl_service.py`:
- `translate()` und `write_optimize()` berechnen `word_count` aus dem Input-Text
- Übergeben `word_count` an `_record_usage()`

**Schritt 3: LLM Service anpassen**

In `llm_service.py`:
- Die Response enthält bereits `usage.input_tokens` und `usage.output_tokens`
- Diese werden an `_record_usage()` übergeben

**Schritt 4: Commit**

```bash
git add app/services/usage_service.py app/services/deepl_service.py app/services/llm_service.py
git commit -m "feat(usage): pass word_count and tokens to _record_usage"
```

---

## Task 3: New Endpoint — GET /api/usage/summary

**Files:**
- Modify: `app/routers/usage.py` (neue Route)
- Modify: `app/models/schemas.py` (Response-Schema)

**Kontext:** Neuer Endpoint gibt kumulative Stats für die letzten 4 Wochen zurück.

**Schritt 1: Response-Schema**

In `app/models/schemas.py`:
```python
class UsageSummaryOperation(BaseModel):
    words: int
    characters: int

class UsageSummaryLLM(BaseModel):
    input_tokens: int
    output_tokens: int

class UsageSummary(BaseModel):
    period: str = "4 weeks"
    translate: UsageSummaryOperation
    write: UsageSummaryOperation
    llm: UsageSummaryLLM | None = None  # nur wenn LLM konfiguriert
```

**Schritt 2: Endpoint**

In `app/routers/usage.py`:
```python
@router.get("/usage/summary")
async def get_usage_summary():
    """Return cumulative usage stats for the last 4 weeks."""
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)
    
    with SessionLocal() as db:
        # Translate stats
        translate_stats = db.query(
            func.sum(UsageRecord.word_count),
            func.sum(UsageRecord.characters_used)
        ).filter(
            UsageRecord.operation_type == "translate",
            UsageRecord.created_at >= four_weeks_ago
        ).first()
        
        # Write stats
        write_stats = db.query(
            func.sum(UsageRecord.word_count),
            func.sum(UsageRecord.characters_used)
        ).filter(
            UsageRecord.operation_type == "write",
            UsageRecord.created_at >= four_weeks_ago
        ).first()
        
        # LLM tokens (only where tokens > 0)
        llm_stats = db.query(
            func.sum(UsageRecord.input_tokens),
            func.sum(UsageRecord.output_tokens)
        ).filter(
            UsageRecord.created_at >= four_weeks_ago,
            UsageRecord.input_tokens > 0
        ).first()
        
    llm_configured = llm_service.is_configured()
    
    return {
        "period": "4 weeks",
        "translate": {
            "words": translate_stats[0] or 0,
            "characters": translate_stats[1] or 0,
        },
        "write": {
            "words": write_stats[0] or 0,
            "characters": write_stats[1] or 0,
        },
        "llm": {
            "input_tokens": llm_stats[0] or 0,
            "output_tokens": llm_stats[1] or 0,
        } if llm_configured else None,
    }
```

**Schritt 3: Commit**

```bash
git add app/routers/usage.py app/models/schemas.py
git commit -m "feat(usage): add /api/usage/summary endpoint for 4-week stats"
```

---

## Task 4: Frontend — Fetch and Display Cumulative Stats

**Files:**
- Modify: `static/js/app.js`
- Modify: `templates/index.html` (CSS + HTML)
- Build: `npm run build:css`

**Kontext:** Die obere Stats-Leiste (neben "0 / 10.000 Zeichen") zeigt jetzt die kumulativen 4-Wochen-Werte.

**Schritt 1: HTML — Obere Stats-Leiste**

In `templates/index.html`, suche die obere Leiste (neben `chars-used-translate`):
```html
<div class="top-stats">
    <span id="stats-cumulative-translate" title="Übersetzt in den letzten 4 Wochen">
        🔄 <span id="cumulative-words-translate">0</span> Wörter
    </span>
    <span class="stats-sep">·</span>
    <span id="stats-cumulative-write" title="Optimiert in den letzten 4 Wochen">
        ✏️ <span id="cumulative-words-write">0</span> Wörter
    </span>
    <span class="stats-sep" id="stats-llm-sep">·</span>
    <span id="stats-cumulative-llm" class="stat-llm-only" title="LLM-Nutzung in den letzten 4 Wochen">
        📥 <span id="cumulative-tokens-in">0</span> · 📤 <span id="cumulative-tokens-out">0</span> · Σ <span id="cumulative-tokens-total">0</span>
    </span>
</div>
```

**Schritt 2: CSS — Styling**

In `input.css`:
```css
.top-stats {
    display: none;  /* shown by JS when data loaded */
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-muted);
}
.top-stats.visible { display: flex; }
.stats-sep { color: var(--border); }
.stat-llm-only { display: none; }
.stat-llm-only.visible { display: inline; }
```

**Schritt 3: JS — Fetch und Update**

In `app.js`:
```js
// In loadConfig() or a new _loadUsageSummary()
async _loadUsageSummary() {
    try {
        const res = await fetch('/api/usage/summary');
        const data = await res.json();
        
        // Update translate words
        this._setText('cumulative-words-translate', this.formatNumber(data.translate.words));
        
        // Update write words
        this._setText('cumulative-words-write', this.formatNumber(data.write.words));
        
        // Update LLM tokens (only if configured)
        if (data.llm) {
            const inTok = data.llm.input_tokens;
            const outTok = data.llm.output_tokens;
            const total = inTok + outTok;
            this._setText('cumulative-tokens-in', this.formatNumber(inTok));
            this._setText('cumulative-tokens-out', this.formatNumber(outTok));
            this._setText('cumulative-tokens-total', this.formatNumber(total));
            document.getElementById('stats-cumulative-llm').classList.add('visible');
            document.getElementById('stats-llm-sep').style.display = 'inline';
        }
        
        document.querySelector('.top-stats').classList.add('visible');
    } catch (e) {
        console.warn('[App] Usage summary failed:', e);
    }
}
```

**Schritt 4: Init aufrufen**

In `loadConfig()` nach dem Laden:
```js
this._loadUsageSummary();
```

**Schritt 5: CSS bauen**
```bash
npm run build:css
```

**Schritt 6: Commit**

```bash
git add static/js/app.js templates/index.html static/css/input.css static/css/styles.css
git commit -m "feat(usage): display cumulative 4-week stats — words and LLM tokens"
```

---

## Task 5: Remove DeepL Token/Cost Display (as requested)

**Files:**
- Modify: `static/js/app.js` (_updateOutputStats)
- Modify: `templates/index.html` (Stats-Bar HTML)

**Kontext:** Die aktuelle Token/Cost-Zeile in der unteren Stats-Bar (Output) wird komplett entfernt.

**Schritt 1: JS — Token/Cost Zeile entfernen**

In `_updateOutputStats()`: Entferne den gesamten Block "Token / cost row (LLM non-streaming only)". Behalte nur Wort/Char-Anzeige.

**Schritt 2: HTML — Token/Cost Zeile entfernen**

In `templates/index.html`, suche und entferne:
```html
<span class="stat-llm-only" id="stat-tokens-translate">...
<span class="stat-llm-only" id="stat-cost-translate">...
<span class="stat-llm-only" id="stat-tokens-write">...
<span class="stat-llm-only" id="stat-cost-write">...
```

**Schritt 3: CSS bereinigen**

Entferne `.stat-llm-only` CSS falls nur für Output-Stats verwendet.

**Schritt 4: Commit**

```bash
git commit -m "refactor(usage): remove DeepL token/cost display — replaced with 4-week cumulative stats"
```

---

## Task 6: Tests

**Files:**
- Modify: `tests/test_usage.py` (neue Tests)

**Schritt 1: Tests für `/api/usage/summary`**

```python
def test_usage_summary_translate_only():
    # Record some translate usage
    # Call endpoint
    # Assert word_count and characters

def test_usage_summary_write_only():
    # Record some write usage
    # Call endpoint
    # Assert word_count

def test_usage_summary_llm_tokens():
    # Record LLM usage with tokens
    # Call endpoint
    # Assert input/output tokens

def test_usage_summary_4_week_filter():
    # Record one old (5 weeks), one recent (1 week)
    # Only recent should be in summary
```

**Schritt 2: Run tests**

```bash
pytest tests/test_usage.py -v
```

---

## Task 7: Version-Bump und Release

**Files:**
- Modify: `app/config.py`
- Modify: `CHANGELOG.md`

**Schritt:** Version auf z.B. `2.10.0` erhöhen (Minor — neues Feature).

---

## Summary der Änderungen

| Task | Scope |
|---|---|
| 1 | DB-Migration (word_count, tokens) |
| 2 | Backend: _record_usage() erweitern |
| 3 | Backend: GET /api/usage/summary |
| 4 | Frontend: Obere Stats-Leiste mit Hover-Tooltip |
| 5 | DeepL Token/Cost aus Output-Stats entfernen |
| 6 | Tests |
| 7 | Version + Release |
