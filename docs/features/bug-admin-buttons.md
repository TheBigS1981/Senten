# Bug: Admin-Buttons ohne Funktion (Löschen, Deaktivieren, Passwort zurücksetzen)

**Status:** Open  
**Erstellt:** 2026-03-01  
**Typ:** Bug  
**Priorität:** High — Kernfunktion der Admin-UI kaputt  
**Betrifft:** `static/js/admin.js`, `templates/admin.html`  

---

## Symptom

In der Admin-UI (`/admin`) reagieren die Buttons **Deaktivieren**, **Passwort** (zurücksetzen) und **Löschen** nicht. Ein Klick auf diese Buttons hat keinerlei sichtbaren Effekt — kein Dialog, kein Netzwerk-Request, keine Fehlermeldung.

---

## Root-Cause-Analyse

### Hypothese 1 — CSP blockiert `inline onclick`

Die Buttons in `_renderUsers()` nutzen **Inline-Event-Handler** via `onclick`-Attribut in dynamisch erzeugtem HTML:

```javascript
// admin.js, Zeile 50–57
`<button ... onclick="Admin.toggleActive('${u.id}', ${!u.is_active})">...</button>`
`<button ... onclick="Admin.resetPassword('${u.id}')">...</button>`
`<button ... onclick="Admin.deleteUser('${u.id}', '${this._esc(u.username)}')">...</button>`
```

Die App setzt **Content-Security-Policy**-Header via `SecurityHeadersMiddleware`. Eine strikte CSP (`script-src 'nonce-...'` ohne `'unsafe-inline'`) blockiert alle inline `onclick`-Handler in dynamisch gesetztem `innerHTML` — **auch wenn die Seite selbst einen Nonce hat**, weil der Nonce nur für `<script>`-Tags gilt, nicht für `onclick`-Attribute.

**Dies ist der wahrscheinlichste Root Cause.**

### Hypothese 2 — `Admin` nicht im globalen Scope

Wenn `admin.js` als `type="module"` geladen wird, ist `Admin` nicht global. Dann schlägt `onclick="Admin.toggleActive(...)"` mit `ReferenceError: Admin is not defined` fehl — lautlos wenn keine DevTools offen sind.

### Hypothese 3 — `modal-create` Dialog nicht im DOM

`_bindEvents()` greift auf `document.getElementById('btn-create-user')` zu — falls das Element nicht im DOM ist, wirft `addEventListener` einen Fehler, der `Admin.init()` abbricht, bevor `loadUsers()` überhaupt läuft.

---

## Diagnose-Schritte

1. Browser-Konsole auf `/admin` öffnen → nach `CSP`-, `ReferenceError`- oder `TypeError`-Meldungen suchen
2. In DevTools Network prüfen: werden bei Button-Klick überhaupt Requests gesendet?
3. `SecurityHeadersMiddleware` prüfen: steht `'unsafe-inline'` in `script-src`?

---

## Fix-Plan

### Fix A — Inline-Handlers auf Event Delegation umstellen (empfohlen)

Statt `onclick`-Attributen: Event-Delegation auf den User-Listen-Container. Kein Inline-JS mehr → CSP-kompatibel.

```javascript
// In _bindEvents() oder loadUsers() nach dem Rendern:
document.getElementById('user-list').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const { action, userId, username } = btn.dataset;
    if (action === 'toggle')    Admin.toggleActive(userId, btn.dataset.newState === 'true');
    if (action === 'password')  Admin.resetPassword(userId);
    if (action === 'delete')    Admin.deleteUser(userId, username);
});
```

Buttons erhalten `data-action`, `data-user-id`, `data-username` statt `onclick`.

### Fix B — CSP `'unsafe-hashes'` oder `'unsafe-inline'` (Workaround, nicht empfohlen)

Würde das Security-Niveau senken. Nicht bevorzugt.

---

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `static/js/admin.js` | Inline-onclick → data-Attribute + Event-Delegation |
| `templates/admin.html` | ggf. keine Änderung nötig |
| `app/middleware/security.py` | CSP prüfen (Diagnose) |

---

## Akzeptanzkriterien

- [ ] "Deaktivieren"-Button deaktiviert/reaktiviert den Benutzer — Liste refresht sich
- [ ] "Passwort"-Button öffnet `prompt()` und setzt Passwort via API
- [ ] "Löschen"-Button öffnet `confirm()` und löscht Benutzer via API
- [ ] Keine CSP-Violations in der Browser-Konsole
- [ ] Bestehendes test_admin.py bleibt grün
- [ ] Kein `onclick`-Inline-JS in dynamisch gesetztem HTML mehr

---

## Testplan

- Browser-Konsole auf Fehler prüfen (manuelle Verifikation)
- Existierende API-Tests (`tests/test_admin.py`) bestätigen Backend-Korrektheit
- Optional: Playwright-Test für Button-Klick auf `/admin`
