# Feature: Benutzerverwaltung & Profile

**Status:** Done — implementiert in v2.8.0, bugfixed in v2.8.1  
**Erstellt:** 2026-02-28  
**Erstellt von:** @deep-thinker  
**Implementiert:** 2026-03-01  
**Ziel-Version:** v2.8.0 / v2.8.1 (Patch)

---

## Übersicht

Benutzer sollen angelegt und verwaltet werden können. Jeder Benutzer hat ein eigenes Profil, in dem Einstellungen (Theme, Akzentfarbe, Sprach-Defaults, Engine-Präferenz etc.) serverseitig gespeichert werden. Der Verlauf (History) wird benutzerspezifisch zugeordnet. localStorage wird als Einstellungs-Speicher abgelöst.

**Anonymer Modus bleibt erhalten**, kann aber per `.env`-Variable (`ALLOW_ANONYMOUS=true/false`) ein-/ausgeschaltet werden. Wenn deaktiviert, ist Login zwingend erforderlich.

---

## Anforderungen

### Funktionale Anforderungen

1. **Benutzer anlegen** — Neue Benutzer können von einem Admin angelegt werden
   - [ ] Benutzername + Passwort (lokale Auth)
   - [ ] Eindeutiger `user_id` als Primärschlüssel (UUID)
   - [ ] OIDC-User werden beim ersten Login automatisch angelegt (Auto-Provisioning)
   - [ ] Erster User wird automatisch Admin (oder per `.env` definiert: `ADMIN_USERNAME`)

2. **Benutzer verwalten** — Admin-UI im Frontend
   - [ ] Benutzerliste mit Status (aktiv/deaktiviert)
   - [ ] Benutzer anlegen (Admin-only)
   - [ ] Benutzer deaktivieren / reaktivieren (Admin-only)
   - [ ] Benutzer löschen inkl. zugehöriger History + Usage + Settings (Admin-only)
   - [ ] Passwort zurücksetzen (Admin-only, bei lokaler Auth)

3. **Anonymer Modus** — Steuerbar per `.env`
   - [ ] `ALLOW_ANONYMOUS=true` (Default) — App nutzbar ohne Login (wie bisher)
   - [ ] `ALLOW_ANONYMOUS=false` — Login erforderlich, alle Requests ohne Session werden auf Login-Seite umgeleitet
   - [ ] Anonyme Benutzer haben keinen persistenten Verlauf und keine serverseitigen Settings

4. **Benutzerprofil mit Einstellungen** — Jeder Benutzer hat ein serverseitiges Profil
   - [ ] Theme (z.B. `dark-blue`, `light-violet`)
   - [ ] Custom Akzentfarbe (`#rrggbb` oder `null`)
   - [ ] Bevorzugte Quellsprache
   - [ ] Bevorzugte Zielsprache
   - [ ] Engine-Präferenz pro Tab (DeepL / LLM)
   - [ ] Formality-Einstellung
   - [ ] Diff-View-Toggle-Status
   - [ ] Weitere Einstellungen erweiterbar (JSON-Feld oder eigene Spalten)

5. **Settings-API** — CRUD-Endpunkte für Benutzereinstellungen
   - [ ] `GET /api/profile` — Eigenes Profil + Einstellungen laden
   - [ ] `PUT /api/profile/settings` — Einstellungen aktualisieren (partiell, nur geänderte Felder)
   - [ ] Frontend lädt beim Start das Profil und wendet Einstellungen an
   - [ ] Frontend schreibt Änderungen an Settings sofort an die API (statt localStorage)

6. **Benutzerspezifischer Verlauf** — History ist an den eingeloggten Benutzer gebunden
   - [ ] Bestehende History-Logik nutzt bereits `user_id` — wird als FK auf `users.id` verknüpft
   - [ ] Verlauf ist nur für den eigenen Benutzer sichtbar
   - [ ] Beim Löschen eines Users werden alle zugehörigen History-Records kaskadiert gelöscht

7. **Datenmigration** — Bestehende anonyme Daten werden bereinigt
   - [ ] Alle `history_records` mit `user_id = "anonymous"` werden beim DB-Upgrade gelöscht
   - [ ] Alle `usage_records` mit `user_id = "anonymous"` werden beim DB-Upgrade gelöscht
   - [ ] localStorage-Einstellungen werden beim ersten Login eines neuen Users einmalig an `PUT /api/profile/settings` gesendet, danach localStorage-Keys entfernt

---

## UI-Anforderungen

8. **Login-Seite** — Wenn `ALLOW_ANONYMOUS=false` oder Auth konfiguriert
   - [ ] Benutzername + Passwort Formular
   - [ ] "Angemeldet bleiben" Option (verlängerte Session-Dauer)
   - [ ] Fehlermeldung bei falschem Login
   - [ ] Redirect zur App nach erfolgreichem Login

9. **Profil-Bereich** — Zugänglich über Header (User-Icon / Benutzername)
   - [ ] Einstellungen einsehbar und änderbar (Theme, Sprach-Defaults etc.)
   - [ ] Passwort ändern (bei lokaler Auth)
   - [ ] Logout-Button

10. **Admin-Bereich** — Eigene Seite/Modal, nur für Admins sichtbar
    - [ ] Benutzerliste mit Status, letztem Login
    - [ ] Benutzer anlegen (Benutzername + Passwort)
    - [ ] Benutzer deaktivieren / reaktivieren
    - [ ] Benutzer löschen (mit Bestätigungsdialog)
    - [ ] Passwort zurücksetzen

---

## Nicht in Scope

- OAuth2 / Social Login (Google, GitHub etc.) — OIDC-Integration existiert bereits separat
- Rollen- und Berechtigungssystem (RBAC) über Admin/User hinaus (nur Admin/User)
- Multi-Tenancy (mehrere Organisationen)
- Profilbilder / Avatare
- E-Mail-Verifikation / Passwort-vergessen-Flow
- Selbst-Registrierung (nur Admin kann Benutzer anlegen; OIDC-User werden auto-provisioniert)

---

## Technische Spezifikation

### Neue `.env`-Variablen

| Variable | Pflicht | Default | Beschreibung |
|----------|---------|---------|-------------|
| `ALLOW_ANONYMOUS` | Nein | `true` | Erlaubt anonyme Nutzung ohne Login |
| `ADMIN_USERNAME` | Nein | — | Benutzername des initialen Admin-Accounts (wird beim ersten Start angelegt) |
| `ADMIN_PASSWORD` | Nein | — | Passwort des initialen Admin-Accounts |
| `SESSION_LIFETIME_HOURS` | Nein | `24` | Session-Dauer in Stunden |
| `SESSION_LIFETIME_REMEMBER_HOURS` | Nein | `720` (30 Tage) | Session-Dauer bei "Angemeldet bleiben" |

### Session-Management: HttpOnly Cookie + serverseitige Session

**Entscheidung:** HttpOnly Secure Cookie mit serverseitiger Session-Tabelle in SQLite.

**Begründung (vs. JWT):**
- Serverseitige Invalidierung: Admin kann User deaktivieren → Session sofort ungültig
- Kein Token-Leak im JavaScript (HttpOnly = kein XSS-Zugriff)
- Logout funktioniert zuverlässig (Session wird serverseitig gelöscht)
- Senten ist Single-Instance → kein Nachteil durch serverseitigen State
- JWT hätte Blacklist-Problem bei User-Deaktivierung und Logout

**Session-Flow:**
1. `POST /api/auth/login` → validiert Credentials → erstellt Session in DB → setzt HttpOnly Cookie
2. Jeder Request: Cookie → Session-ID → Lookup in `sessions`-Tabelle → User-Objekt auf `request.state`
3. `POST /api/auth/logout` → löscht Session aus DB + Cookie
4. OIDC: Token-Validierung → Auto-Provisioning → Session erstellen (gleicher Flow ab Schritt 1)

### Datenbankänderungen

**Neue Tabelle: `users`**
| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| `id` | String (UUID4) | Primärschlüssel |
| `username` | String, unique | Eindeutig, für Login |
| `password_hash` | String, nullable | bcrypt-Hash (null bei OIDC-only Users) |
| `display_name` | String, nullable | Anzeigename |
| `is_admin` | Boolean, default=false | Admin-Rechte |
| `is_active` | Boolean, default=true | Account aktiv/deaktiviert |
| `auth_provider` | String, default="local" | `local` oder `oidc` |
| `oidc_subject` | String, nullable, unique | OIDC Subject-Claim (für Auto-Provisioning Matching) |
| `last_login_at` | DateTime, nullable | Letzter Login-Zeitpunkt |
| `created_at` | DateTime | Erstellungsdatum |
| `updated_at` | DateTime | Letzte Änderung |

**Neue Tabelle: `sessions`**
| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| `id` | String (UUID4) | Session-ID (wird als Cookie-Wert gesetzt) |
| `user_id` | String (FK → users.id) | Zugehöriger User |
| `created_at` | DateTime | Session-Start |
| `expires_at` | DateTime | Ablaufzeit |
| `ip_address` | String, nullable | IP bei Session-Erstellung |
| `user_agent` | String, nullable | Browser User-Agent |

**Neue Tabelle: `user_settings`**
| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| `user_id` | String (FK → users.id, PK) | 1:1 Beziehung zum User |
| `theme` | String, default="light-blue" | Theme-ID |
| `accent_color` | String, nullable | Custom Farbe `#rrggbb` |
| `source_lang` | String, nullable | Bevorzugte Quellsprache |
| `target_lang` | String, default="DE" | Bevorzugte Zielsprache |
| `engine_translate` | String, default="deepl" | `deepl` oder `llm` |
| `engine_write` | String, default="deepl" | `deepl` oder `llm` |
| `formality` | String, default="default" | `default`, `more`, `less`, `prefer_more`, `prefer_less` |
| `diff_view` | Boolean, default=false | Diff-Ansicht aktiv |
| `updated_at` | DateTime | Letzte Änderung |

**Bestehende Tabellen — Änderungen:**
- `history_records.user_id` → wird FK auf `users.id` mit `ON DELETE CASCADE`
- `usage_records.user_id` → wird FK auf `users.id` mit `ON DELETE CASCADE`
- Migration: alle Records mit `user_id = "anonymous"` werden gelöscht

### API-Endpunkte (neu)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `POST` | `/api/auth/login` | Public | Login (Username + Passwort) |
| `POST` | `/api/auth/logout` | Authenticated | Session beenden |
| `GET` | `/api/profile` | Authenticated | Eigenes Profil + Settings |
| `PUT` | `/api/profile/settings` | Authenticated | Settings aktualisieren (partiell) |
| `PUT` | `/api/profile/password` | Authenticated | Eigenes Passwort ändern |
| `GET` | `/api/admin/users` | Admin | Benutzerliste |
| `POST` | `/api/admin/users` | Admin | Benutzer anlegen |
| `PUT` | `/api/admin/users/{id}` | Admin | Benutzer bearbeiten (active, admin) |
| `DELETE` | `/api/admin/users/{id}` | Admin | Benutzer löschen (kaskadiert) |
| `PUT` | `/api/admin/users/{id}/password` | Admin | Passwort zurücksetzen |

### Betroffene Dateien (voraussichtlich)

| Datei | Art der Änderung |
|-------|-----------------|
| `app/config.py` | Neue Settings: `allow_anonymous`, `admin_username`, `admin_password`, Session-Lifetime |
| `app/db/models.py` | Neue Models: `User`, `Session`, `UserSettings` |
| `app/db/database.py` | Migration: anonyme Records löschen, FKs hinzufügen |
| `app/models/schemas.py` | Neue Pydantic-Schemas: Login, UserProfile, UserSettings, AdminUser |
| `app/routers/auth.py` | **Neu**: Login/Logout-Endpunkte |
| `app/routers/profile.py` | **Neu**: Profil + Settings-Endpunkte |
| `app/routers/admin.py` | **Neu**: Admin-CRUD-Endpunkte |
| `app/services/user_service.py` | **Neu**: User-CRUD, Session-Management, Passwort-Hashing |
| `app/middleware/auth.py` | Umbau: Session-Cookie-Validierung, OIDC Auto-Provisioning, Anonymous-Check |
| `static/js/app.js` | Settings laden/speichern via API statt localStorage |
| `static/js/admin.js` | **Neu**: Admin-UI Logik |
| `templates/index.html` | Login-Formular, Profil-Button im Header, Admin-Link |
| `templates/login.html` | **Neu**: Login-Seite |
| `.env.example` | Neue Variablen |
| `requirements.txt` | `bcrypt` für Passwort-Hashing |

### Abhängigkeiten / Risiken

- **Auth-Middleware-Umbau** — Größte Risiko-Stelle: Die bestehende Middleware (OIDC / Basic / Anonym) muss um Session-Cookie-Validierung erweitert werden. Basic Auth bleibt als API-Auth erhalten, Login-Seite ist nur für Browser-Sessions.
- **OIDC Auto-Provisioning** — Bei erstem OIDC-Login wird automatisch ein User in der `users`-Tabelle angelegt (`auth_provider = "oidc"`, `oidc_subject` = Subject-Claim). Kein Passwort-Hash.
- **Passwort-Hashing** — `bcrypt` (via `bcrypt`-Paket). Kein eigener Algorithmus.
- **Session-Cleanup** — Abgelaufene Sessions müssen regelmäßig gelöscht werden (z.B. bei jedem Request oder per Background-Task).
- **Abwärtskompatibilität** — `ALLOW_ANONYMOUS=true` (Default) sorgt dafür, dass bestehende Installationen ohne Konfigurationsänderung weiter funktionieren.

---

## Open Questions

_Alle Fragen geklärt (siehe Decisions Made)._

---

## Akzeptanzkriterien

- [ ] Benutzer können vom Admin über ein UI angelegt und verwaltet werden
- [ ] Jeder Benutzer hat ein serverseitiges Profil mit Einstellungen
- [ ] Theme, Akzentfarbe, Sprach-Defaults und Engine-Präferenz werden im Profil gespeichert
- [ ] Verlauf (History) ist benutzerspezifisch und nur für den eigenen User sichtbar
- [ ] localStorage wird nicht mehr für Einstellungen verwendet (Migration beim ersten Login)
- [ ] `ALLOW_ANONYMOUS=true` (Default) erlaubt Nutzung ohne Login (Abwärtskompatibilität)
- [ ] `ALLOW_ANONYMOUS=false` erzwingt Login für alle Requests
- [ ] OIDC-User werden beim ersten Login automatisch angelegt
- [ ] Bestehende anonyme Records (`user_id = "anonymous"`) werden bei DB-Migration gelöscht
- [ ] Admin kann User deaktivieren → laufende Sessions werden sofort ungültig
- [ ] Login/Logout funktioniert zuverlässig über HttpOnly Session-Cookie
- [ ] Alle bestehenden Tests bleiben grün
- [ ] Neue Tests für User-CRUD, Settings-API, Session-Management, Admin-API und Migration

---

## Decisions Made

- [2026-02-28] User — Anonymer Modus bleibt erhalten, aber steuerbar per `ALLOW_ANONYMOUS` in `.env` (Default: `true`)
- [2026-02-28] User — OIDC-User werden beim ersten Login automatisch angelegt (Auto-Provisioning via `oidc_subject`)
- [2026-02-28] User — Admin-UI wird von Anfang an mitgebaut (nicht nur API)
- [2026-02-28] @deep-thinker — Session-Management: HttpOnly Secure Cookie + serverseitige Session-Tabelle in SQLite (kein JWT). Begründung: serverseitige Invalidierung bei User-Deaktivierung/Logout, kein XSS-Risiko, kein Blacklist-Problem. Senten ist Single-Instance → kein Nachteil.
- [2026-02-28] User — Bestehende anonyme Records (`user_id = "anonymous"`) in History + Usage werden bei Migration gelöscht (kein Transfer zu neuem User)

---

## Progress Log

- [2026-02-28] @deep-thinker — Feature-Request erstellt + alle Open Questions mit User geklärt — next: Implementierungsplan erstellen

---

## Testing Notes

- **User-CRUD:** Anlegen, Lesen, Aktualisieren, Deaktivieren, Löschen + kaskadierende Löschung (History, Usage, Settings, Sessions)
- **Settings-API:** Defaults bei neuem User, partielles Update, ungültige Werte, Settings nach Logout erhalten
- **Session-Management:** Login, Session-Cookie gesetzt (HttpOnly), Session-Validierung, Logout (Session gelöscht), Ablauf (expired), deaktivierter User → Session ungültig
- **Admin-API:** Nur Admin darf zugreifen, User anlegen/deaktivieren/löschen, Passwort zurücksetzen, letzter Admin kann sich nicht selbst löschen
- **OIDC Auto-Provisioning:** Erster Login erstellt User, zweiter Login findet bestehenden User via `oidc_subject`
- **Anonymer Modus:** `ALLOW_ANONYMOUS=true` → App nutzbar ohne Login; `ALLOW_ANONYMOUS=false` → Redirect auf Login
- **Migration:** Anonyme Records werden gelöscht, localStorage → Server (einmalig), danach localStorage bereinigt
- **History-Isolation:** User A sieht nicht den Verlauf von User B
- **Edge Cases:** Gleichzeitige Sessions desselben Users, Session-Cleanup abgelaufener Sessions, Admin deaktiviert sich selbst (verhindern)
