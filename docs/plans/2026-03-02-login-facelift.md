# Login-Seite Facelift Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Login-Seite optisch aufwerten mit Passwort-Toggle (Auge-Icon), verbessertem Anmelden-Button und einem subtilen visuellen Facelift — ohne das minimalistische Design zu brechen.

**Architecture:** Reine Frontend-Änderung an `templates/login.html` und `static/css/input.css`. Keine Backend-Änderung nötig. Font Awesome ist bereits lokal verfügbar unter `/static/css/fontawesome.min.css` (referenziert via `../webfonts/`). Kein CDN, kein neues JS.

**Tech Stack:** HTML, CSS (input.css → styles.css via npm), Vanilla JS (inline Script-Block in login.html), Font Awesome 6 (lokal)

---

## Task 1: Font Awesome in login.html einbinden

**Files:**
- Modify: `templates/login.html` (Zeile 7–8, `<head>`-Block)

**Kontext:** `index.html` bindet Font Awesome via `<link rel="stylesheet" href="/static/css/fontawesome.min.css">` ein. `login.html` tut das bisher nicht — deshalb kann kein FA-Icon verwendet werden.

**Step 1: Link-Tag einfügen**

Füge in `login.html` direkt nach der Zeile `<link rel="stylesheet" href="/static/css/styles.css">` ein:

```html
<link rel="stylesheet" href="/static/css/fontawesome.min.css">
```

**Step 2: Prüfen ob Icons rendern**

Starte den Dev-Server (`uvicorn app.main:app --reload`) und öffne `http://localhost:8000/login`. Füge testweise `<i class="fas fa-eye"></i>` irgendwo in den Body, prüfe ob das Icon erscheint, dann wieder entfernen.

**Step 3: Commit**

```bash
git add templates/login.html
git commit -m "feat(login): add Font Awesome for password toggle icon"
```

---

## Task 2: CSS — Facelift für Login-Seite

**Files:**
- Modify: `static/css/input.css` (Abschnitt `.login-*`, ca. Zeile 130–219)

**Kontext:** Alle Login-Styles sind in `input.css`. Nach Änderungen muss `npm run build:css` ausgeführt werden, damit `styles.css` aktualisiert wird.

**Step 1: Hintergrund mit Gradient aufwerten**

Ersetze `.login-page`:
```css
.login-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--bg, #f0f4ff) 0%, var(--bg, #f9fafb) 60%);
}
```

**Step 2: Card polieren**

Ersetze `.login-card`:
```css
.login-card {
    background: var(--surface, #ffffff);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 16px;
    padding: 2.5rem 2rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, .10), 0 1px 4px rgba(0, 0, 0, .06);
}
```

**Step 3: Label-Kontrast verbessern**

Ersetze `.form-group label`:
```css
.form-group label {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text, #111827);
}
```

**Step 4: Passwort-Feld-Wrapper für Toggle-Button vorbereiten**

Füge nach `.form-group label { ... }` ein:
```css
.form-input-wrap {
    position: relative;
    display: flex;
    align-items: center;
}

.form-input-wrap .form-input {
    padding-right: 2.75rem; /* Platz für Toggle-Button */
}

.password-toggle {
    position: absolute;
    right: 0.75rem;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    color: var(--text-muted, #6b7280);
    font-size: 0.9rem;
    line-height: 1;
    display: flex;
    align-items: center;
    transition: color 0.15s;
}

.password-toggle:hover {
    color: var(--text, #111827);
}
```

**Step 5: Anmelden-Button aufwerten**

Füge nach `.btn-full { ... }` ein (oder ersetze falls bereits vorhanden):
```css
.login-submit {
    width: 100%;
    padding: 0.75rem 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    transition: background 0.15s, box-shadow 0.15s, transform 0.1s;
}

.login-submit:hover:not(:disabled) {
    box-shadow: 0 4px 12px rgba(0, 102, 255, 0.3);
    transform: translateY(-1px);
}

.login-submit:active:not(:disabled) {
    transform: translateY(0);
}

.login-submit:disabled {
    opacity: 0.7;
    cursor: not-allowed;
}
```

**Step 6: CSS neu bauen**

```bash
npm run build:css
```

**Step 7: Commit**

```bash
git add static/css/input.css static/css/styles.css
git commit -m "style(login): facelift — gradient bg, polished card, label contrast, password toggle CSS, improved submit button"
```

---

## Task 3: HTML — Passwort-Toggle und Button-Upgrade in login.html

**Files:**
- Modify: `templates/login.html` (Formular-Bereich, ca. Zeile 35–56)

**Kontext:** Das Passwort-Feld wird in einen `.form-input-wrap`-Div gewickelt, der den absolut positionierten Toggle-Button enthält. Der Submit-Button bekommt die neue Klasse `.login-submit` und ein Icon.

**Step 1: Passwort-Feld mit Toggle-Wrapper ersetzen**

Ersetze den bestehenden Passwort-`<div class="form-group">` Block:

**Vorher (Zeile 42–47):**
```html
<div class="form-group">
  <label for="password">Passwort</label>
  <input type="password" id="password" name="password"
         autocomplete="current-password" required
         class="form-input">
</div>
```

**Nachher:**
```html
<div class="form-group">
  <label for="password">Passwort</label>
  <div class="form-input-wrap">
    <input type="password" id="password" name="password"
           autocomplete="current-password" required
           class="form-input">
    <button type="button" id="password-toggle" class="password-toggle"
            aria-label="Passwort anzeigen" title="Passwort anzeigen">
      <i class="fas fa-eye" id="password-toggle-icon" aria-hidden="true"></i>
    </button>
  </div>
</div>
```

**Step 2: Submit-Button aufwerten**

Ersetze den bestehenden Button (Zeile 53–55):

**Vorher:**
```html
<button type="submit" class="btn btn-primary btn-full" id="login-btn">
  Anmelden
</button>
```

**Nachher:**
```html
<button type="submit" class="btn btn-primary login-submit" id="login-btn">
  Anmelden
  <i class="fas fa-arrow-right" aria-hidden="true"></i>
</button>
```

**Step 3: Commit**

```bash
git add templates/login.html
git commit -m "feat(login): add password toggle button and upgrade submit button"
```

---

## Task 4: JS — Passwort-Toggle Logik in login.html

**Files:**
- Modify: `templates/login.html` (inline `<script>`-Block, ca. Zeile 60–102)

**Kontext:** Der Login-Script-Block enthält bereits den Form-Submit-Handler. Der Toggle-Handler wird direkt darunter ergänzt — kein externes JS-File, da login.html eine eigenständige Seite ist.

**Step 1: Toggle-Handler zum Script-Block hinzufügen**

Füge direkt nach dem `});` des Submit-Handlers (nach Zeile 101) ein:

```js
// Password visibility toggle
document.getElementById('password-toggle').addEventListener('click', () => {
  const input = document.getElementById('password');
  const icon  = document.getElementById('password-toggle-icon');
  const btn   = document.getElementById('password-toggle');
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  icon.className = isHidden ? 'fas fa-eye-slash' : 'fas fa-eye';
  btn.setAttribute('aria-label', isHidden ? 'Passwort verbergen' : 'Passwort anzeigen');
  btn.setAttribute('title',      isHidden ? 'Passwort verbergen' : 'Passwort anzeigen');
});
```

**Step 2: Verhalten prüfen (manuell)**

- Passwort-Feld: Tippe ein Passwort → klicke Auge → Text wird sichtbar, Icon wechselt zu `fa-eye-slash`
- Klicke nochmal → Text wird wieder verborgen, Icon wechselt zurück zu `fa-eye`
- Tab-Navigation: Toggle-Button ist per Tab erreichbar, Enter/Space aktiviert ihn (dank `type="button"`)
- Submit mit sichtbarem Passwort funktioniert weiterhin (type="text" wird korrekt ans Formular übergeben)

**Step 3: Commit**

```bash
git add templates/login.html
git commit -m "feat(login): implement password visibility toggle with icon swap"
```

---

## Task 5: Manuelle Smoke-Tests

**Kontext:** Kein automatisierter Test nötig — login.html hat keinen Backend-Test-Counterpart und die Logik ist rein visuell/interaktiv.

### 5a — Light Mode
Öffne `http://localhost:8000/login` im Browser (kein gespeichertes Theme → default light-blue).

Checkliste:
- [ ] Hintergrund hat dezenten Gradient (nicht Flat-Grau)
- [ ] Card hat leicht mehr Padding, weichere Box-Shadow
- [ ] Labels sind dunkler/kräftiger als vorher
- [ ] Passwort-Feld hat Auge-Icon rechts (nicht abgeschnitten)
- [ ] Klick auf Auge → Passwort sichtbar + Icon wechselt zu durchgestrichenem Auge
- [ ] Klick nochmal → Passwort verborgen + Icon zurück
- [ ] Anmelden-Button: groß, volle Breite, Pfeil-Icon rechts, Hover-Effekt (leichtes Anheben + Schatten)
- [ ] Login funktioniert tatsächlich (Username + Passwort eingeben, Submit)

### 5b — Dark Mode
Setze `localStorage.setItem('theme', 'dark-blue')` in der Browser-Console, lade neu.

Checkliste:
- [ ] Gradient-Hintergrund passt zum dunklen Theme (nutzt `--bg` Variable)
- [ ] Card-Hintergrund ist `--surface` (dunkel), Text hell
- [ ] Auge-Icon und Button gut sichtbar

### 5c — Fehlerzustand
Gib falsche Credentials ein → Submit.

Checkliste:
- [ ] Error-Box erscheint (rote Fehlermeldung)
- [ ] Button-Text wechselt zu "Anmelden…" während Anfrage läuft
- [ ] Button ist während Anfrage disabled (kein Doppel-Submit)

---

## Task 6: Version-Bump und Release

**Files:**
- Modify: `app/config.py` (VERSION)
- Modify: `CHANGELOG.md`

**Step 1: VERSION erhöhen**

In `app/config.py`: `VERSION = "2.9.4"` → `VERSION = "2.9.5"`

*(Falls engine-availability bereits als v2.9.4 released wurde — sonst ist login-facelift v2.9.4)*

**Step 2: CHANGELOG-Eintrag**

```markdown
## [2.9.5] - 2026-03-02

### Changed
- Login-Seite: Subtiles Facelift — dezenter Hintergrund-Gradient, polierte Card, kräftigere Labels
- Login-Seite: Anmelden-Button jetzt groß, volle Breite mit Pfeil-Icon und Hover-Effekt
- Login-Seite: Passwort-Feld mit Sichtbarkeits-Toggle (Auge-Icon) — Passwort ein-/ausblenden
```

**Step 3: Tests sicherstellen**

```bash
pytest tests/ -q
```

Erwartung: alle Tests grün (keine Backend-Änderung → keine Regression).

**Step 4: Commit, Tag, Push**

```bash
git add app/config.py CHANGELOG.md
git commit -m "chore: release v2.9.5"
git tag v2.9.5
git push && git push --tags
```

---

## Rollback-Notiz

Alle Änderungen sind auf `templates/login.html` und `static/css/input.css` beschränkt. Rollback: `git revert` der entsprechenden Commits oder `git checkout <sha> -- templates/login.html static/css/input.css`.
