# Feature: Gravatar-Profilbilder

**Status:** Planned  
**Erstellt:** 2026-03-01  
**Typ:** Feature (Enhancement)  
**Priorität:** Low  
**Ziel-Version:** offen  

---

## Übersicht

Benutzer sollen ein Profilbild erhalten. Da Senten keine eigene Bild-Upload-Infrastruktur hat, wird [Gravatar](https://gravatar.com/) als externe Quelle genutzt: Über die E-Mail-Adresse (oder einen Fallback auf den Benutzernamen) wird automatisch ein Avatar geladen. Für Benutzer ohne Gravatar-Account wird ein konsistenter Fallback (Initials-Avatar oder Identicon) angezeigt.

---

## Anforderungen

### Funktional

1. **Gravatar-URL ableiten** — MD5-Hash der E-Mail-Adresse (lowercase, getrimmt). Falls kein E-Mail-Feld vorhanden, Fallback auf einen generierten Avatar (z.B. `identicon` oder `initials`).
2. **E-Mail-Feld im User-Modell** — optionales `email`-Feld in der `users`-Tabelle hinzufügen. Admin kann es setzen; bei OIDC-Provisioning aus dem `email`-Claim befüllen.
3. **Avatar im Profil-Menü** — kleines Rundbild (32×32 px) statt des generischen User-Icons im Header.
4. **Avatar in der Admin-Benutzerliste** — 40×40 px Bild neben Benutzername.
5. **Lazy-Load + HTTPS** — Gravatar immer über `https://www.gravatar.com/avatar/...`. Bei Ladefehler auf Initials-Fallback wechseln (onerror).
6. **Datenschutz-Hinweis** — Gravatar lädt ein Bild von einem externen Server (Cloudflare-CDN). Kurzer Hinweis in der Profil-Einstellung.

### Nicht in Scope

- Eigener Bild-Upload (kein S3, kein lokaler Speicher)
- Libravatar oder alternative Avatar-Dienste
- Cropping/Resizing im Browser

---

## Technische Spezifikation

### DB-Änderung

```sql
ALTER TABLE users ADD COLUMN email VARCHAR UNIQUE;
```

Migration: idempotent via `migrate_db()` (Column existiert → skip).

### Gravatar-URL (Backend-Helper)

```python
import hashlib

def gravatar_url(email: Optional[str], size: int = 40) -> str:
    if not email:
        return f"https://www.gravatar.com/avatar/?d=identicon&s={size}"
    digest = hashlib.md5(email.strip().lower().encode()).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d=identicon"
```

Helper in `app/utils.py`. Gibt URL zurück — kein externer HTTP-Call im Backend.

### API-Änderungen

- `GET /api/profile` — neues Feld `avatar_url` (String, generiert aus `email` via `gravatar_url()`)
- `PUT /api/profile/settings` — `email` als optionales Feld akzeptieren (Validierung: E-Mail-Format)
- `GET /api/admin/users` — `avatar_url` im Response für Admin-Liste
- `POST /api/admin/users` + `PUT /api/admin/users/{id}` — `email` als optionales Feld

### Frontend-Änderungen

- `static/js/app.js` — `_loadProfile()` liest `avatar_url`, setzt `<img src="...">` im Header-Button
- `static/js/admin.js` — Avatar in `_renderUsers()`
- `templates/index.html` — User-Button: `<img>` statt Icon, Fallback via `onerror`
- `static/css/input.css` — `.avatar-img` Styles (border-radius: 50%, object-fit: cover)

### Pydantic-Schema-Änderungen

- `UserProfileResponse` — `avatar_url: str`
- `AdminUserResponse` — `avatar_url: str`
- `UserUpdateRequest` — `email: Optional[str]`

---

## Betroffene Dateien

| Datei | Art |
|-------|-----|
| `app/db/models.py` | `email`-Column in `User` |
| `app/db/database.py` | Migration für `email`-Column |
| `app/utils.py` | `gravatar_url()` Helper |
| `app/models/schemas.py` | `avatar_url` in Response-Schemas, `email` in Update-Schemas |
| `app/routers/profile.py` | `email` in Settings-Update, `avatar_url` in Response |
| `app/routers/admin.py` | `email` in Create/Update, `avatar_url` in Response |
| `app/middleware/auth.py` | OIDC: `email`-Claim bei Provisioning befüllen |
| `static/js/app.js` | Avatar im Header |
| `static/js/admin.js` | Avatar in Benutzerliste |
| `templates/index.html` | `<img>` im User-Button |
| `static/css/input.css` | `.avatar-img` Styles |

---

## Akzeptanzkriterien

- [ ] Benutzer mit gesetzter E-Mail-Adresse sehen ihr Gravatar-Bild im Header und in der Admin-Liste
- [ ] Benutzer ohne E-Mail oder ohne Gravatar sehen ein Identicon (automatisch generiert, kein broken-image-Icon)
- [ ] OIDC-Benutzer erhalten ihre E-Mail-Adresse automatisch beim Provisioning
- [ ] Admin kann E-Mail-Adresse eines Benutzers setzen/ändern
- [ ] Ladefehler (z.B. kein Netz) degradieren graceful auf Identicon-Fallback
- [ ] Alle bestehenden Tests bleiben grün; neue Tests für `gravatar_url()` und API-Felder

---

## Risiken / Abhängigkeiten

- **Datenschutz**: Gravatar-Aufruf sendet Hash der E-Mail an externen Server (Cloudflare). Für DSGVO-konforme Setups ggf. opt-in statt opt-out — aktuell als "low risk" bewertet (Hash, kein Klartext).
- **CSP**: `img-src` in `SecurityHeadersMiddleware` muss `https://www.gravatar.com` erlauben.
- **DB-Migration**: `ALTER TABLE` auf bestehender DB muss getestet werden.
