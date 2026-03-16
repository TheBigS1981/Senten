/**
 * Admin UI — Benutzerverwaltung
 * Handles user listing, creation, update, deletion and password reset.
 */
const Admin = {
    _toastContainer: null,

    async init() {
        await this.loadUsers();
        this._bindEvents();
    },

    _ensureToastContainer() {
        if (!this._toastContainer) {
            this._toastContainer = document.createElement('div');
            this._toastContainer.id = 'admin-toast';
            this._toastContainer.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                padding: 12px 20px;
                border-radius: 8px;
                color: #fff;
                font-size: 14px;
                z-index: 10000;
                opacity: 0;
                transition: opacity 0.3s ease;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            `;
            document.body.appendChild(this._toastContainer);
        }
    },

    _showToast(message, isError = true) {
        this._ensureToastContainer();
        this._toastContainer.textContent = message;
        this._toastContainer.style.background = isError ? '#dc2626' : '#16a34a';
        this._toastContainer.style.opacity = '1';
        setTimeout(() => {
            this._toastContainer.style.opacity = '0';
        }, 3000);
    },

    async loadUsers() {
        const list = document.getElementById('user-list');
        try {
            const res = await fetch('/api/admin/users', { credentials: 'same-origin' });
            if (res.status === 401) {
                list.innerHTML = '<p style="color:var(--text-muted)">Nicht angemeldet. <a href="/login">Anmelden</a></p>';
                return;
            }
            if (res.status === 403) {
                list.innerHTML = '<p style="color:var(--text-muted)">Kein Zugriff — Admin-Rechte erforderlich.</p>';
                return;
            }
            const users = await res.json();
            this._renderUsers(users);
        } catch {
            list.innerHTML = '<p style="color:var(--text-muted)">Fehler beim Laden der Benutzerliste.</p>';
        }
    },

    _renderUsers(users) {
        const list = document.getElementById('user-list');
        if (!users.length) {
            list.innerHTML = '<p style="color:var(--text-muted)">Keine Benutzer vorhanden.</p>';
            return;
        }
        list.innerHTML = users.map(u => `
            <div class="user-card ${u.is_active ? '' : 'user-card--inactive'}">
                <div class="user-info">
                    ${u.avatar_url ? `<img src="${this._escUrl(u.avatar_url)}" class="user-avatar" width="40" height="40" alt="" onerror="this.style.display='none'">` : ''}
                    <span class="user-name">${this._esc(u.display_name || u.username)}</span>
                    <span class="user-username">@${this._esc(u.username)}</span>
                    ${u.is_admin ? '<span class="badge badge-admin">Admin</span>' : ''}
                    ${!u.is_active ? '<span class="badge badge-inactive">Deaktiviert</span>' : ''}
                    ${u.email ? `<span class="user-email" title="${this._esc(u.email)}">${this._esc(u.email)}</span>` : ''}
                    <span class="user-meta">
                        ${u.auth_provider} &middot;
                        Erstellt: ${new Date(u.created_at).toLocaleDateString('de-DE')} &middot;
                        Letzter Login: ${u.last_login_at ? new Date(u.last_login_at).toLocaleDateString('de-DE') : 'Noch nie'}
                    </span>
                </div>
                <div class="user-actions">
                    <button class="btn btn-ghost btn-sm"
                            data-action="edit-email"
                            data-user-id="${this._esc(u.id)}"
                            data-current-email="${this._esc(u.email || '')}">
                        <i class="fas fa-at" aria-hidden="true"></i> E-Mail
                    </button>
                    <button class="btn btn-ghost btn-sm"
                            data-action="toggle"
                            data-user-id="${this._esc(u.id)}"
                            data-new-state="${!u.is_active}">
                        ${u.is_active ? 'Deaktivieren' : 'Aktivieren'}
                    </button>
                    <button class="btn btn-ghost btn-sm"
                            data-action="password"
                            data-user-id="${this._esc(u.id)}">
                        Passwort
                    </button>
                    <button class="btn btn-danger btn-sm"
                            data-action="delete"
                            data-user-id="${this._esc(u.id)}"
                            data-username="${this._esc(u.username)}">
                        Löschen
                    </button>
                </div>
            </div>
        `).join('');
    },

    async toggleActive(id, newState) {
        const res = await fetch(`/api/admin/users/${id}`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: newState }),
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            this._showToast(data.detail || 'Fehler beim Aktualisieren.');
        }
        await this.loadUsers();
    },

    async deleteUser(id, username) {
        if (!confirm(`Benutzer "${username}" wirklich löschen?\n\nAlle Daten (Verlauf, Einstellungen, Sessions) werden unwiderruflich gelöscht.`)) return;
        const res = await fetch(`/api/admin/users/${id}`, {
            method: 'DELETE',
            credentials: 'same-origin',
        });
        if (!res.ok && res.status !== 204) {
            const data = await res.json().catch(() => ({}));
            this._showToast(data.detail || 'Fehler beim Löschen.');
        }
        await this.loadUsers();
    },

    async resetPassword(id) {
        const pw = prompt('Neues Passwort eingeben (mind. 8 Zeichen):');
        if (!pw) return;
        if (pw.length < 8) {
            this._showToast('Passwort muss mindestens 8 Zeichen lang sein.');
            return;
        }
        const res = await fetch(`/api/admin/users/${id}/password`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_password: pw }),
        });
        if (res.ok) {
            this._showToast('Passwort erfolgreich geändert.', false);
        } else {
            const data = await res.json().catch(() => ({}));
            this._showToast(data.detail || 'Fehler beim Zurücksetzen.');
        }
    },

    async editEmail(id, currentEmail) {
        const email = prompt(
            `E-Mail-Adresse für diesen Benutzer (leer lassen zum Entfernen):\n\nAktuell: ${currentEmail || '(keine)'}`,
            currentEmail || ''
        );
        if (email === null) return; // Abgebrochen
        const res = await fetch(`/api/admin/users/${id}`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email.trim() || null }),
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            this._showToast(data.detail || 'Fehler beim Speichern der E-Mail.');
        }
        await this.loadUsers();
    },

    _bindEvents() {
        // Event delegation for dynamically-rendered user action buttons.
        // Using data-action attributes instead of inline onclick handlers avoids
        // CSP violations — script-src does not include 'unsafe-inline', so onclick
        // attributes injected via innerHTML would be silently blocked.
        document.getElementById('user-list').addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-action]');
            if (!btn) return;
            const { action, userId, newState, username, currentEmail } = btn.dataset;
            if (action === 'toggle')     Admin.toggleActive(userId, newState === 'true');
            if (action === 'password')   Admin.resetPassword(userId);
            if (action === 'delete')     Admin.deleteUser(userId, username);
            if (action === 'edit-email') Admin.editEmail(userId, currentEmail);
        });

        document.getElementById('btn-create-user').addEventListener('click', () => {
            document.getElementById('modal-create').showModal();
        });

        document.getElementById('btn-cancel-create').addEventListener('click', () => {
            document.getElementById('modal-create').close();
            document.getElementById('form-create').reset();
            document.getElementById('create-error').hidden = true;
        });

        document.getElementById('form-create').addEventListener('submit', async (e) => {
            e.preventDefault();
            const errEl = document.getElementById('create-error');
            errEl.hidden = true;
            const fd = new FormData(e.target);
            const body = {
                username: fd.get('username'),
                password: fd.get('password'),
                display_name: fd.get('display_name') || null,
                email: fd.get('email') || null,
                is_admin: fd.has('is_admin'),
            };
            const res = await fetch('/api/admin/users', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (res.ok) {
                document.getElementById('modal-create').close();
                e.target.reset();
                await this.loadUsers();
            } else {
                const data = await res.json().catch(() => ({}));
                errEl.textContent = data.detail || 'Fehler beim Anlegen.';
                errEl.hidden = false;
            }
        });

        // Close modal on backdrop click
        document.getElementById('modal-create').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) e.currentTarget.close();
        });
    },

    /**
     * Escape a plain text string for safe embedding in HTML text content or
     * attribute values that are NOT URLs (e.g. display names, usernames).
     */
    _esc(str) {
        return String(str).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[c]);
    },

    /**
     * Escape a URL string for safe embedding in an HTML attribute (e.g. src,
     * href).  Only characters that can break out of an attribute value are
     * escaped; the ampersand is intentionally preserved so that query-string
     * parameters remain valid (browsers already parse &amp; correctly in src,
     * but keeping bare & avoids double-encoding issues in edge cases and is
     * equally safe inside a quoted attribute).
     */
    _escUrl(str) {
        return String(str).replace(/[<>"']/g, c => ({
            '<': '%3C', '>': '%3E', '"': '%22', "'": '%27'
        })[c]);
    },
};

Admin.init();
