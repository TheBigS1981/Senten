# Remove Formality Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Completely remove the "Formality" (Formality) feature from both backend and frontend.

**Architecture:** Remove all formality-related code, endpoints, UI elements, and CSS.

**Tech Stack:** Python/FastAPI, Vanilla JS, CSS

---

## Was entfernen

### Backend
- `app/routers/translate.py`: `formality` Parameter in `TranslateRequest` und `WriteRequest`
- `app/models/schemas.py`: `formality` Field in Request/Response Schemas
- `app/services/deepl_service.py`: `formality` Parameter an DeepL API

### Frontend
- `templates/index.html`: Formality dropdown in Translate- und Write-Toolbar
- `static/js/app.js`: Formality-related state, UI update logic
- `static/css/input.css`: Formality-related CSS (falls vorhanden)

---

## Implementation

**Schritt 1: Backend — Remove formality from schemas**

In `app/models/schemas.py`:
- Remove `formality` from `TranslateRequest`
- Remove `formality` from `WriteRequest`

**Schritt 2: Backend — Remove from translate.py**

In `app/routers/translate.py`:
- Remove `formality` from endpoint signatures
- Remove passing formality to DeepL service

**Schritt 3: Backend — Remove from deepl_service.py**

In `app/services/deepl_service.py`:
- Remove `formality` parameter from `translate()` and `write_optimize()`

**Schritt 4: Frontend — Remove HTML**

In `templates/index.html`:
- Remove `<select id="formality-translate">` in Translate toolbar
- Remove `<select id="formality-write">` in Write toolbar

**Schritt 5: Frontend — Remove JS**

In `static/js/app.js`:
- Remove `formalityTranslate` and `formalityWrite` state
- Remove `_updateFormalityVisibility()` function (or calls to it)
- Remove any event listeners for formality dropdowns

**Schritt 6: Frontend — Remove CSS (optional)**

In `input.css`:
- Remove `.formality-select` styles if any

**Schritt 7: Commit**

```bash
git commit -m "refactor: remove formality feature completely"
```
