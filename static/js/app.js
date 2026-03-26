/**
 * Senten — Main Application
 *
 * Vanilla JS single-page app for the DeepL / LLM translation frontend.
 * Engine state (DeepL ↔ LLM), theme, and diff-view toggle are persisted
 * in localStorage. Global keyboard shortcuts live in keyboard-shortcuts.js.
 */
'use strict';

/** Maps LLM provider identifiers to human-readable display names. */
const PROVIDER_LABELS = {
    'openai':            'OpenAI',
    'anthropic':         'Anthropic',
    'ollama':            'Ollama',
    'openai-compatible': 'OpenAI-compatible',
};

const App = {
    state: {
        activeTab: 'translate',
        translateDebounceTimer: null,
        writeDebounceTimer: null,
        config: null,
        detectedLang: null,
        autoTargetChanged: false,
        useAutoDetection: true,
        langNames: {},  // Loaded from API /api/config
        // Engine selection per tab ('deepl' | 'llm') — independent per tab
        translateEngine: 'deepl',
        writeEngine: 'deepl',
        // AbortControllers for in-flight requests — cancelled when a new request starts
        translateAbortController: null,
        writeAbortController: null,
        // Diff view toggle — persisted in localStorage
        diffViewEnabled: true,
        // Session-based history tracking
        translateSession: { id: null, sourceText: '', sourceLang: '', targetLang: '', targetText: '', createdAt: 0 },
        writeSession: { id: null, sourceText: '', targetLang: '', targetText: '', createdAt: 0 },
        // i18n state
        uiLanguage: 'en',
        translations: {},
        availableLanguages: [],
    },

    // Currently logged-in user profile (null = anonymous mode)
    currentUser: null,

    // LLM debug data (Admin only — populated after clicking Debug button)
    _debugTranslate: null,
    _debugWrite: null,

    // ── Initialisation ──────────────────────────────────────────────────────

    async init() {
        try {
            this._loadEngineStates();   // ← localStorage FIRST before loadConfig
            this._loadDiffViewState();
            await this.loadConfig();
            await this.loadLanguages();  // Load available UI languages
            await this.initI18n();       // Initialize i18n after languages are loaded
            await this._loadProfile();   // Load user profile after i18n (may override language)
            this.bindEvents();
            this._loadUsageSummary();   // Load 4-week cumulative stats
            
            // Refresh usage stats every 60 s, but pause when page is hidden
            this._usageInterval = setInterval(() => {
                if (!document.hidden) {
                    this._loadUsageSummary();
                }
            }, 60_000);
            
            // Pause interval when tab becomes hidden, resume when visible
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    clearInterval(this._usageInterval);
                    this._usageInterval = null;
                } else {
                    this._loadUsageSummary(); // Immediate refresh when returning
                    this._usageInterval = setInterval(() => {
                        if (!document.hidden) {
                            this._loadUsageSummary();
                        }
                    }, 60_000);
                }
            });
            
            this.initTheme();
            this.checkUrlParams();
        } catch (e) {
            console.error('[App] Init error:', e);
        }
    },

    // ── Theme ───────────────────────────────────────────────────────────────

    initTheme() {
        const saved        = localStorage.getItem('theme');
        const customAccent = localStorage.getItem('theme-accent-custom');
        const prefersDark  = window.matchMedia('(prefers-color-scheme: dark)').matches;

        // Migrate legacy 'dark'/'light' values to new theme IDs
        let themeId = saved;
        if (saved === 'dark')  themeId = 'dark-blue';
        if (saved === 'light') themeId = 'light-blue';
        if (!themeId) themeId = prefersDark ? 'dark-blue' : 'light-blue';

        this.applyTheme(themeId, customAccent || null);
        this._bindThemeDropdown();

        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem('theme')) {
                this.applyTheme(e.matches ? 'dark-blue' : 'light-blue', null);
            }
        });
    },

    // ── i18n (Internationalization) ─────────────────────────────────────

    /**
     * Load available UI languages from the API.
     */
    async loadLanguages() {
        try {
            const res = await fetch('/api/i18n/languages');
            if (!res.ok) return;
            const data = await res.json();
            this.state.availableLanguages = data.languages || [];
            
            // Update language selector if it exists
            const langSelect = document.getElementById('ui-language-select');
            if (langSelect) {
                // Keep existing options but update based on available languages
                const currentValue = langSelect.value;
                langSelect.innerHTML = '';
                this.state.availableLanguages.forEach(lang => {
                    const option = document.createElement('option');
                    option.value = lang.code;
                    option.textContent = lang.native_name || lang.name;
                    langSelect.appendChild(option);
                });
                // Restore selection or set default
                if (currentValue && this.state.availableLanguages.some(l => l.code === currentValue)) {
                    langSelect.value = currentValue;
                }
            }
        } catch (e) {
            console.error('[App] Failed to load languages:', e);
            // Fallback to default languages
            this.state.availableLanguages = [
                { code: 'en', name: 'English', native_name: 'English' },
                { code: 'de', name: 'German', native_name: 'Deutsch' },
                { code: 'fr', name: 'French', native_name: 'Français' },
                { code: 'it', name: 'Italian', native_name: 'Italiano' },
                { code: 'es', name: 'Spanish', native_name: 'Español' },
            ];
        }
    },

    /**
     * Initialize i18n: detect language, load translations, apply to UI.
     * Priority: localStorage > browser language > default (en)
     */
    async initI18n() {
        // Detect language priority: localStorage > browser > default
        let lang = localStorage.getItem('senten_language');
        
        if (!lang) {
            // Try browser language
            const browserLang = navigator.language || navigator.userLanguage;
            if (browserLang) {
                const langCode = browserLang.split('-')[0].toLowerCase();
                // Check if supported
                if (this.state.availableLanguages.some(l => l.code === langCode)) {
                    lang = langCode;
                }
            }
        }
        
        // Fallback to English
        if (!lang) lang = 'en';
        
        await this.setLanguage(lang);
        
        // Bind language selector change event
        this._bindLanguageSelector();
    },

    /**
     * Load translations for a specific language from the API.
     * @param {string} lang - Language code (e.g., 'en', 'de', 'fr')
     */
    async loadTranslations(lang) {
        try {
            const res = await fetch(`/api/i18n/${lang}`);
            if (!res.ok) {
                console.warn(`[App] Failed to load translations for ${lang}, falling back to en`);
                if (lang !== 'en') {
                    return await this.loadTranslations('en');
                }
                return {};
            }
            const data = await res.json();
            return data.translations || {};
        } catch (e) {
            console.error(`[App] Error loading translations for ${lang}:`, e);
            if (lang !== 'en') {
                return await this.loadTranslations('en');
            }
            return {};
        }
    },

    /**
     * Set the UI language: load translations, update localStorage, save to profile.
     * @param {string} lang - Language code
     */
    async setLanguage(lang) {
        const translations = await this.loadTranslations(lang);
        this.state.uiLanguage = lang;
        this.state.translations = translations;
        localStorage.setItem('senten_language', lang);
        
        // Update the document language
        document.documentElement.lang = lang;
        
        // Apply translations to all elements with data-i18n
        this.applyTranslations();
        
        // Update language selector if exists
        const langSelect = document.getElementById('ui-language-select');
        if (langSelect) {
            langSelect.value = lang;
        }
        
        // Save to user profile if logged in
        this._saveProfileSetting('ui_language', lang);
    },

    /**
     * Get a translated string by key.
     * @param {string} key - Translation key (e.g., 'nav.translate', 'errors.ERR_TRANSLATE_FAILED')
     * @param {object} params - Optional parameters for interpolation (e.g., {max_chars: 5000})
     * @returns {string} Translated string or the key if not found
     */
    t(key, params = {}) {
        let text = this.state.translations[key] || key;
        
        // Handle interpolation (e.g., {max_chars})
        if (params && typeof params === 'object') {
            Object.keys(params).forEach(param => {
                text = text.replace(new RegExp(`\\{${param}\\}`, 'g'), params[param]);
            });
        }
        
        return text;
    },

    /**
     * Apply translations to all elements with data-i18n and data-i18n-placeholder attributes.
     */
     applyTranslations() {
         // Translate all elements with data-i18n attribute.
         // Guard: only set textContent on leaf elements (no child elements).
         // Container spans that hold icon + value-bearing child spans must not
         // be overwritten — el.textContent = x destroys all child nodes.
         document.querySelectorAll('[data-i18n]').forEach(el => {
             const key = el.getAttribute('data-i18n');
             const translation = this.t(key);
             if (translation && translation !== key && el.children.length === 0) {
                 el.textContent = translation;
             }
         });
        
        // Translate placeholders
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            const translation = this.t(key);
            if (translation && translation !== key) {
                el.placeholder = translation;
            }
        });
        
        // Translate tooltips (title attribute)
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            const translation = this.t(key);
            if (translation && translation !== key) {
                el.title = translation;
            }
        });
        
        // Update aria-labels
        document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
            const key = el.getAttribute('data-i18n-aria-label');
            const translation = this.t(key);
            if (translation && translation !== key) {
                el.setAttribute('aria-label', translation);
            }
        });
    },

    /**
     * Get the locale code for number formatting based on current UI language.
     * @returns {string} Locale code (e.g., 'en-US', 'de-DE')
     */
    getNumberLocale() {
        const lang = this.state.uiLanguage;
        const localeMap = {
            'en': 'en-US',
            'de': 'de-DE',
            'fr': 'fr-FR',
            'it': 'it-IT',
            'es': 'es-ES',
        };
        return localeMap[lang] || 'en-US';
    },

    /**
     * Format a number using the current UI language locale.
     * @param {number} num - Number to format
     * @returns {string} Formatted number
     */
    formatNumber(num) {
        try {
            return new Intl.NumberFormat(this.getNumberLocale()).format(num);
        } catch (e) {
            return num.toString();
        }
    },

    /**
     * Bind the language selector dropdown change event.
     */
    _bindLanguageSelector() {
        const langSelect = document.getElementById('ui-language-select');
        if (!langSelect) return;
        
        langSelect.addEventListener('change', async (e) => {
            const newLang = e.target.value;
            await this.setLanguage(newLang);
        });
    },

    applyTheme(themeId, customAccent) {
        // Set data-theme on <html>
        document.documentElement.setAttribute('data-theme', themeId);

        // Also keep legacy 'dark' attribute for any existing selectors
        const isDark = themeId.startsWith('dark');
        if (isDark) {
            document.documentElement.setAttribute('data-mode', 'dark');
        } else {
            document.documentElement.removeAttribute('data-mode');
        }

        // Apply custom accent color via CSS custom property on :root
        if (customAccent) {
            document.documentElement.style.setProperty('--color-interactive-default', customAccent);
            // Compute hover (slightly darker) and subtle (very light version)
            document.documentElement.style.setProperty('--color-interactive-hover', customAccent);
            document.documentElement.style.setProperty('--color-interactive-subtle', customAccent + '18');
            // Update color picker to show current value
            const picker = document.getElementById('theme-accent-color');
            if (picker) picker.value = customAccent;
        } else {
            // Remove custom overrides — let CSS token cascade take over
            document.documentElement.style.removeProperty('--color-interactive-default');
            document.documentElement.style.removeProperty('--color-interactive-hover');
            document.documentElement.style.removeProperty('--color-interactive-subtle');
            // Reset color picker to theme default
            const defaults = {
                'light-blue':   '#0066ff',
                'dark-blue':    '#60a5fa',
                'light-violet': '#7c3aed',
                'dark-violet':  '#a78bfa',
            };
            const picker = document.getElementById('theme-accent-color');
            if (picker) picker.value = defaults[themeId] || '#0066ff';
        }

        // Update toggle button label + icon
        const labels = {
            'light-blue':   { icon: 'fas fa-sun',  text: 'Hell (Blau)',      customText: 'Hell (Individuell)' },
            'dark-blue':    { icon: 'fas fa-moon', text: 'Dunkel (Blau)',    customText: 'Dunkel (Individuell)' },
            'light-violet': { icon: 'fas fa-sun',  text: 'Hell (Violett)',   customText: 'Hell (Individuell)' },
            'dark-violet':  { icon: 'fas fa-moon', text: 'Dunkel (Violett)', customText: 'Dunkel (Individuell)' },
        };
        const meta  = labels[themeId] || labels['light-blue'];
        const icon  = document.getElementById('theme-icon');
        const label = document.getElementById('theme-label');
        if (icon)  icon.className    = meta.icon;
        if (label) label.textContent = customAccent ? meta.customText : meta.text;

        // Update active state on options
        document.querySelectorAll('.theme-option').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.theme === themeId);
        });

        // Persist locally
        localStorage.setItem('theme', themeId);

        // Sync to server profile (no-op if anonymous)
        this._saveProfileSetting('theme', themeId);
        if (customAccent) {
            this._saveProfileSetting('accent_color', customAccent);
        } else {
            this._saveProfileSetting('accent_color', '');  // '' = reset to null on server
        }
    },

    _bindThemeDropdown() {
        const picker     = document.getElementById('theme-picker');
        const toggleBtn  = document.getElementById('theme-toggle-btn');
        const dropdown   = document.getElementById('theme-dropdown');
        const colorInput = document.getElementById('theme-accent-color');
        const resetBtn   = document.getElementById('theme-accent-reset');

        if (!picker || !toggleBtn || !dropdown) return;

        // Toggle dropdown open/close
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = !dropdown.hidden;
            dropdown.hidden = isOpen;
            toggleBtn.setAttribute('aria-expanded', String(!isOpen));
        });

        // Theme option clicks
        dropdown.querySelectorAll('.theme-option').forEach(btn => {
            btn.addEventListener('click', () => {
                const themeId = btn.dataset.theme;
                // Keep custom accent if set
                const custom = localStorage.getItem('theme-accent-custom');
                this.applyTheme(themeId, custom || null);
                dropdown.hidden = true;
                toggleBtn.setAttribute('aria-expanded', 'false');
            });
        });

        // Color picker input
        if (colorInput) {
            colorInput.addEventListener('input', () => {
                const color   = colorInput.value;
                const themeId = document.documentElement.getAttribute('data-theme') || 'light-blue';
                localStorage.setItem('theme-accent-custom', color);
                this.applyTheme(themeId, color);
            });
        }

        // Reset custom accent
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                localStorage.removeItem('theme-accent-custom');
                const themeId = document.documentElement.getAttribute('data-theme') || 'light-blue';
                this.applyTheme(themeId, null);
            });
        }

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!picker.contains(e.target)) {
                dropdown.hidden = true;
                toggleBtn.setAttribute('aria-expanded', 'false');
            }
        });

        // Close on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !dropdown.hidden) {
                dropdown.hidden = true;
                toggleBtn.setAttribute('aria-expanded', 'false');
                toggleBtn.focus();
            }
        });
    },

    // ── User Profile & Auth ──────────────────────────────────────────────────

    async _loadProfile() {
        try {
            const res = await fetch('/api/profile', { credentials: 'same-origin' });
            if (!res.ok) {
                // 401 = anonymous mode — no profile available
                this.currentUser = null;
                return;
            }
            const profile = await res.json();
            this.currentUser = profile;
            this._applyProfileSettings(profile.settings);
            this._showUserMenu(profile);
            this._updateDebugVisibility();
        } catch {
            // Network error or anonymous mode — fail silently
            this.currentUser = null;
        }
    },

    _applyProfileSettings(s) {
        if (!s) return;
        // Apply server-side settings (override localStorage defaults)
        if (s.theme) {
            const accent = s.accent_color || null;
            this.applyTheme(s.theme, accent);
            localStorage.setItem('theme', s.theme);
            if (accent) localStorage.setItem('theme-accent-custom', accent);
            else localStorage.removeItem('theme-accent-custom');
        }
        if (s.target_lang) {
            const sel = document.getElementById('target-lang-select');
            if (sel) sel.value = s.target_lang;
        }
        if (s.diff_view !== undefined && s.diff_view !== null) {
            this.state.diffViewEnabled = s.diff_view;
            const btn = document.getElementById('btn-diff-toggle');
            if (btn) btn.classList.toggle('active', s.diff_view);
        }
        // Apply UI language from server (if not already set by localStorage)
        if (s.ui_language && !localStorage.getItem('senten_language')) {
            this.setLanguage(s.ui_language);
        }
    },

    _showUserMenu(profile) {
        const wrap      = document.getElementById('user-menu-wrap');
        const name      = document.getElementById('user-display-name');
        const adminLink = document.getElementById('user-dropdown-admin');
        if (wrap) wrap.hidden = false;
        if (name) name.textContent = profile.display_name || profile.username;
        if (adminLink && profile.is_admin) adminLink.hidden = false;

        // Inject Gravatar avatar into the user menu button
        if (profile.avatar_url) {
            const btn = document.getElementById('user-menu-btn');
            if (btn && !btn.querySelector('.user-avatar')) {
                const icon = btn.querySelector('.fa-user-circle');
                const img = document.createElement('img');
                img.src = profile.avatar_url;
                img.alt = '';
                img.className = 'user-avatar';
                img.width = 24;
                img.height = 24;
                img.addEventListener('error', () => { img.style.display = 'none'; });
                if (icon) {
                    icon.replaceWith(img);
                } else {
                    btn.prepend(img);
                }
            }
        }

        this._bindUserMenu();
    },

    _bindUserMenu() {
        const wrap      = document.getElementById('user-menu-wrap');
        const btn       = document.getElementById('user-menu-btn');
        const dropdown  = document.getElementById('user-dropdown');
        const logoutBtn = document.getElementById('user-logout-btn');

        if (!btn || !dropdown) return;

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = !dropdown.hidden;
            dropdown.hidden = isOpen;
            btn.setAttribute('aria-expanded', String(!isOpen));
        });

        if (logoutBtn) {
            logoutBtn.addEventListener('click', async () => {
                try {
                    await fetch('/api/auth/logout', {
                        method: 'POST',
                        credentials: 'same-origin',
                    });
                } catch { /* ignore */ }
                window.location.reload();
            });
        }

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (wrap && !wrap.contains(e.target)) {
                dropdown.hidden = true;
                btn.setAttribute('aria-expanded', 'false');
            }
        });
    },

    async _saveProfileSetting(key, value) {
        if (!this.currentUser) return;  // Anonymous mode — skip API call
        try {
            await fetch('/api/profile/settings', {
                method: 'PUT',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [key]: value }),
            });
        } catch {
            // Silent fail — settings sync is not critical
        }
    },

    // ── URL parameters ──────────────────────────────────────────────────────

    checkUrlParams() {
        const params     = new URLSearchParams(window.location.search);
        const text       = params.get('text');
        const mode       = params.get('mode') || 'translate';
        const targetLang = params.get('target') || 'DE';

        if (!text) return;

        // Use params.get() directly - it already decodes the URL-encoded text
        if (mode === 'write') {
            this.switchTab('write');
            document.getElementById('input-text-write').value = text;
            this.onWriteInput();
        } else {
            document.getElementById('input-text-translate').value = text;
            this._selectRadio('target-lang', targetLang);
            this.onTranslateInput();
        }

        window.history.replaceState({}, document.title, window.location.pathname);
    },

    // ── Config ──────────────────────────────────────────────────────────────

    async loadConfig() {
        try {
            const res = await fetch('/api/config');
            if (!res.ok) {
                throw new Error('Config load failed: HTTP ' + res.status);
            }
            this.state.config = await res.json();
            if (!this.state.config.configured && this.state.config.mock_mode) {
                console.info('[App] DeepL im Mock-Modus. Ursache:', this.state.config.error);
            }
            // Load language names from API response
            if (this.state.config.languages) {
                this.state.langNames = {
                    ...(this.state.config.languages.sources || {}),
                    ...(this.state.config.languages.targets || {}),
                };
            }
            // Always init engine toggles — handles all 4 states internally
            this._initEngineToggles();
            this._updateDebugVisibility();
            // Diff toggle is visible for all users (works with both DeepL and LLM)
            document.getElementById('write-diff-toggle-wrap')?.classList.add('visible');
            // Load cumulative 4-week usage summary
            this._loadUsageSummary();
        } catch (e) {
            console.error('[App] Fehler beim Laden der Konfiguration:', e);
        }
    },

    // ── Events ──────────────────────────────────────────────────────────────

    bindEvents() {
        // Tab switching
        document.getElementById('tab-translate').addEventListener('click', () => this.switchTab('translate'));
        document.getElementById('tab-write').addEventListener('click',     () => this.switchTab('write'));
        document.getElementById('tab-history').addEventListener('click',  () => this.switchTab('history'));

        // Translate panel
        document.getElementById('btn-translate').addEventListener('click',       () => this.translate());
        document.getElementById('btn-clear-translate').addEventListener('click', () => this.clearTranslate());
        document.getElementById('btn-copy-translate').addEventListener('click',  () => this.copyToClipboard('output-text-translate'));
        document.getElementById('btn-optimize-input')?.addEventListener('click',  () => this.handleOptimizeInput());
        document.getElementById('btn-optimize-output')?.addEventListener('click', () => this.handleOptimizeOutput());

        // Write panel
        document.getElementById('btn-write').addEventListener('click',       () => this.write());
        document.getElementById('btn-clear-write').addEventListener('click', () => this.clearWrite());
        document.getElementById('btn-copy-write').addEventListener('click',  () => this.copyToClipboard('output-text-write'));
        document.getElementById('btn-translate-input')?.addEventListener('click',  () => this.handleTranslateInput());
        document.getElementById('btn-translate-output')?.addEventListener('click', () => this.handleTranslateOutput());
        document.getElementById('btn-diff-toggle').addEventListener('click', () => this._toggleDiffView());

        // Input listeners with debounce + auto-resize (combined)
        const tInput = document.getElementById('input-text-translate');
        tInput.addEventListener('input', () => {
            this.onTranslateInput();
            this._autoResizeTextarea(tInput);
        });
        tInput.addEventListener('keydown', (e) => { if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); this.translate(); } });

        const wInput = document.getElementById('input-text-write');
        wInput.addEventListener('input', () => {
            this.onWriteInput();
            this._autoResizeTextarea(wInput);
        });
        wInput.addEventListener('keydown', (e) => { if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); this.write(); } });

        // Language radio changes
        document.querySelectorAll('input[name="target-lang"]').forEach(r =>
            r.addEventListener('change', () => {
                // User selected target language - switch to manual mode
                this.state.useAutoDetection = false;
                // Clear dropdown selection when radio is clicked
                document.getElementById('target-lang-select').value = '';
                if (document.getElementById('input-text-translate').value.trim()) this.translate();
                this._updateSwapButtonVisibility();
            })
        );
        document.querySelectorAll('input[name="write-target-lang"]').forEach(r =>
            r.addEventListener('change', () => {
                // Clear dropdown selection when radio is clicked
                document.getElementById('write-target-lang-select').value = '';
                if (document.getElementById('input-text-write').value.trim()) this.write();
            })
        );

        // Target language dropdown changes (translate)
        document.getElementById('target-lang-select').addEventListener('change', (e) => {
            const value = e.target.value;
            const currentValue = this.getTargetLang('translate');
            if (value && value !== currentValue) {
                // User selected target language - switch to manual mode
                this.state.useAutoDetection = false;
                // Uncheck all radios and select the dropdown value
                document.querySelectorAll('input[name="target-lang"]').forEach(r => r.checked = false);
                this._saveProfileSetting('target_lang', value);
                if (document.getElementById('input-text-translate').value.trim()) this.translate();
            }
            this._updateSwapButtonVisibility();
        });

        // Target language dropdown changes (write)
        document.getElementById('write-target-lang-select').addEventListener('change', (e) => {
            const value = e.target.value;
            const currentValue = this.getTargetLang('write');
            if (value && value !== currentValue) {
                // Uncheck all radios and select the dropdown value
                document.querySelectorAll('input[name="write-target-lang"]').forEach(r => r.checked = false);
                this._saveProfileSetting('target_lang', value);
                if (document.getElementById('input-text-write').value.trim()) this.write();
            }
        });

        // Source language radio changes (Auto / Deutsch / Englisch)
        document.querySelectorAll('input[name="source-lang-radio"]').forEach(r =>
            r.addEventListener('change', () => {
                // Reset dropdown to placeholder (value='' deselects all options)
                document.getElementById('source-lang').value = '';
                if (r.value) {
                    // User selected a specific source language — disable auto detection
                    this.state.useAutoDetection = false;
                    document.getElementById('detected-lang-display').classList.remove('visible');
                } else {
                    // User selected "Auto" — enable auto detection
                    this.state.useAutoDetection = true;
                }
                // Re-translate if text exists
                if (document.getElementById('input-text-translate').value.trim()) this.translate();
                this._updateSwapButtonVisibility();
            })
        );

        // Source language dropdown changes (Weitere...)
        document.getElementById('source-lang').addEventListener('change', (e) => {
            const value = e.target.value;
            if (value) {
                // User selected a specific language from dropdown — uncheck all radios
                document.querySelectorAll('input[name="source-lang-radio"]').forEach(r => r.checked = false);
                this.state.useAutoDetection = false;
                document.getElementById('detected-lang-display').classList.remove('visible');
                // Re-translate if text exists
                if (document.getElementById('input-text-translate').value.trim()) this.translate();
            }
            this._updateSwapButtonVisibility();
        });

        // Language swap button (desktop)
        document.getElementById('btn-swap-langs')?.addEventListener('click', () => this._swapLanguages());

        // Mobile language dropdowns - Translate tab
        document.getElementById('source-lang-mobile-translate')?.addEventListener('change', (e) => {
            this._handleMobileLangChange('translate', 'source', e.target.value);
        });
        document.getElementById('target-lang-mobile-translate')?.addEventListener('change', (e) => {
            this._handleMobileLangChange('translate', 'target', e.target.value);
        });
        document.getElementById('btn-swap-langs-mobile-translate')?.addEventListener('click', () => this._swapLanguages());

        // Mobile language dropdowns - Write/Optimize tab
        document.getElementById('source-lang-mobile-write')?.addEventListener('change', (e) => {
            this._handleMobileLangChange('write', 'source', e.target.value);
        });
        // Write tab doesn't have mobile swap button (no source language)

        // Engine toggle events — wired here so they're always bound;
        // visibility is controlled via CSS class set in _initEngineToggles()
        // Only exists when both engines are configured (toggle mode)
        document.getElementById('translate-engine-checkbox')?.addEventListener('change', (e) => {
            this._handleEngineToggle('translate', e.target.checked);
        });
        document.getElementById('write-engine-checkbox')?.addEventListener('change', (e) => {
            this._handleEngineToggle('write', e.target.checked);
        });

        // History panel - clear all button (bound once at init, not in loadHistory)
        document.getElementById('clear-history-btn')?.addEventListener('click', (e) => {
            this._setupClearAllConfirmation(e.currentTarget);
        });

        // LLM debug buttons (admin only — visible only when LLM active + is_admin)
        document.getElementById('btn-debug-translate')?.addEventListener('click', () => {
            this._fetchDebugInfo('translate');
        });
        document.getElementById('btn-debug-write')?.addEventListener('click', () => {
            this._fetchDebugInfo('write');
        });
    },

    // ── Engine Toggle helpers ────────────────────────────────────────────────

    _initEngineToggles() {
        const cfg = this.state.config;
        const deeplActive = cfg.configured && !cfg.mock_mode;
        const llmActive   = cfg.llm_configured;

        // ── Case 4: No engine — show overlay ────────────────────────────────
        if (!deeplActive && !llmActive) {
            document.getElementById('no-engine-overlay')?.classList.add('visible');
            return;
        }

        // ── Case 2 + 3: Single engine — show label instead of toggle ────────
        if (!deeplActive || !llmActive) {
            const engineName = llmActive
                ? (cfg.llm_display_name
                    || PROVIDER_LABELS[cfg.llm_provider]
                    || (cfg.llm_provider
                        ? cfg.llm_provider.charAt(0).toUpperCase() + cfg.llm_provider.slice(1)
                        : 'LLM'))
                : 'DeepL';

            const forcedEngine = llmActive ? 'llm' : 'deepl';
            this.state.translateEngine = forcedEngine;
            this.state.writeEngine     = forcedEngine;

            ['translate', 'write'].forEach(tab => {
                const wrap = document.getElementById(`${tab}-engine-toggle`);
                if (!wrap) return;
                const row = wrap.querySelector('.engine-toggle-row');
                if (row) {
                    row.innerHTML = `<span class="engine-single-label">Engine: ${engineName}</span>`;
                }
                const info = document.getElementById(`${tab}-engine-info`);
                if (info) {
                    const model = tab === 'translate' ? cfg.llm_translate_model : cfg.llm_write_model;
                    info.textContent = llmActive && model ? model : '';
                }
                wrap.classList.add('visible');
            });
            return;
        }

        // ── Case 1: Both engines — toggle visible and movable ────────────────
        const providerLabel = cfg.llm_display_name
            || PROVIDER_LABELS[cfg.llm_provider]
            || (cfg.llm_provider
                ? cfg.llm_provider.charAt(0).toUpperCase() + cfg.llm_provider.slice(1)
                : 'LLM');

        ['translate', 'write'].forEach(tab => {
            const model = tab === 'translate'
                ? cfg.llm_translate_model
                : cfg.llm_write_model;

            document.getElementById(`${tab}-engine-toggle`).classList.add('visible');
            document.getElementById(`${tab}-engine-info`).textContent =
                `${providerLabel} · ${model || ''}`;

            this._updateEngineLabels(tab);
        });

        // Apply saved engine states to checkboxes
        document.getElementById('translate-engine-checkbox').checked = this.state.translateEngine === 'llm';
        document.getElementById('write-engine-checkbox').checked = this.state.writeEngine === 'llm';
    },

    _updateEngineLabels(tab) {
        const engineKey = tab === 'translate' ? 'translateEngine' : 'writeEngine';
        const isLlm = this.state[engineKey] === 'llm';

        const deepLLabel = document.getElementById(`${tab}-label-deepl`);
        const llmLabel   = document.getElementById(`${tab}-label-llm`);
        
        if (deepLLabel) deepLLabel.classList.toggle('active', !isLlm);
        if (llmLabel)   llmLabel.classList.toggle('active', isLlm);
    },

    _handleEngineToggle(tab, isLlm) {
        const engineKey = tab === 'translate' ? 'translateEngine' : 'writeEngine';
        this.state[engineKey] = isLlm ? 'llm' : 'deepl';
        localStorage.setItem(engineKey, this.state[engineKey]);
        this._updateEngineLabels(tab);
        this._updateDebugVisibility();
        
        // Update aria-checked attribute on the toggle checkbox
        const checkbox = document.getElementById(`${tab}-engine-checkbox`);
        if (checkbox) {
            checkbox.setAttribute('aria-checked', String(isLlm));
        }
    },

    // ── LLM Debug Panel (Admin only) ────────────────────────────────────────

    _isAdmin() {
        return this.currentUser && this.currentUser.is_admin === true;
    },

    _updateDebugVisibility() {
        const isAdmin = this._isAdmin();
        const translateLLM = document.getElementById('translate-engine-checkbox')?.checked;
        const writeLLM = document.getElementById('write-engine-checkbox')?.checked;

        const btnT = document.getElementById('btn-debug-translate');
        const btnW = document.getElementById('btn-debug-write');
        if (btnT) btnT.style.display = (isAdmin && translateLLM) ? '' : 'none';
        if (btnW) btnW.style.display = (isAdmin && writeLLM) ? '' : 'none';
    },

    _renderDebugPanel(tab, data) {
        const panel = document.getElementById(`debug-panel-${tab}`);
        if (!panel || !data) return;

        document.getElementById(`debug-${tab}-meta`).textContent =
            `Provider: ${data.provider}\nModell:    ${data.model}` +
            (data.detected_source_lang ? `\nErkannte Sprache: ${data.detected_source_lang}` : '');
        document.getElementById(`debug-${tab}-system`).textContent = data.system_prompt;
        document.getElementById(`debug-${tab}-user`).textContent = data.user_content;
        document.getElementById(`debug-${tab}-raw`).textContent = data.raw_response;
        document.getElementById(`debug-${tab}-processed`).textContent = data.processed_response;

        const badge = document.getElementById(`debug-${tab}-diff-badge`);
        if (badge) {
            if (data.strip_markdown_changed) {
                badge.className = 'debug-badge-changed';
                badge.textContent = 'verändert';
            } else {
                badge.className = 'debug-badge-same';
                badge.textContent = 'unverändert';
            }
        }

        const u = data.usage || {};
        document.getElementById(`debug-${tab}-usage`).textContent =
            `Input:  ${u.input_tokens ?? 0} Tokens\nOutput: ${u.output_tokens ?? 0} Tokens\nGesamt: ${u.total_tokens ?? 0} Tokens`;

        panel.style.display = '';
        document.getElementById(`btn-debug-${tab}`)?.classList.add('active');
        // Auto-open the details element
        const details = panel.querySelector('details');
        if (details) details.open = true;
    },

    async _fetchDebugInfo(tab) {
        const text = tab === 'translate'
            ? document.getElementById('input-text-translate')?.value?.trim()
            : document.getElementById('input-text-write')?.value?.trim();
        if (!text) return;

        const isTranslate = tab === 'translate';
        const targetLang = isTranslate
            ? (document.querySelector('input[name="target-lang"]:checked')?.value
               || document.getElementById('target-lang-select')?.value || 'DE')
            : (document.querySelector('input[name="write-target-lang"]:checked')?.value
               || document.getElementById('write-target-lang-select')?.value || 'DE');

        const body = { mode: tab === 'translate' ? 'translate' : 'write', text, target_lang: targetLang };

        try {
            const res = await fetch('/api/admin/debug/llm', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                this.showError(err.detail || this.t('notifications.debug_failed'));
                return;
            }
            const data = await res.json();
            if (tab === 'translate') this._debugTranslate = data;
            else this._debugWrite = data;
            this._renderDebugPanel(tab, data);
        } catch {
            if (e.name !== 'AbortError') this.showError(this.t('notifications.debug_failed'));
        }
    },

    _loadEngineStates() {
        const savedTranslate = localStorage.getItem('translateEngine');
        const savedWrite = localStorage.getItem('writeEngine');
        if (savedTranslate === 'llm' || savedTranslate === 'deepl') {
            this.state.translateEngine = savedTranslate;
        }
        if (savedWrite === 'llm' || savedWrite === 'deepl') {
            this.state.writeEngine = savedWrite;
        }
    },

    _loadDiffViewState() {
        const saved = localStorage.getItem('writeDiffView');
        // Default: enabled. Only explicitly stored 'false' disables it.
        this.state.diffViewEnabled = saved !== 'false';
        this._applyDiffViewButton();
    },

    _applyDiffViewButton() {
        const btn = document.getElementById('btn-diff-toggle');
        if (!btn) return;
        if (this.state.diffViewEnabled) {
            btn.classList.add('diff-active');
            btn.setAttribute('aria-pressed', 'true');
            btn.title = 'Änderungen hervorheben (ein) — klicken zum Ausschalten';
        } else {
            btn.classList.remove('diff-active');
            btn.setAttribute('aria-pressed', 'false');
            btn.title = 'Änderungen hervorheben (aus) — klicken zum Einschalten';
        }
    },

    _toggleDiffView() {
        this.state.diffViewEnabled = !this.state.diffViewEnabled;
        localStorage.setItem('writeDiffView', this.state.diffViewEnabled ? 'true' : 'false');
        this._saveProfileSetting('diff_view', this.state.diffViewEnabled);
        this._applyDiffViewButton();

        // Re-render the current output with the new setting (if content exists)
        const output = document.getElementById('output-text-write');
        const input  = document.getElementById('input-text-write');
        if (!output || !input) return;

        const inputText = input.value.trim();

        // Bug B fix: Use session state as source of truth for the optimized text.
        // DOM extraction via textContent strips paragraph breaks (\n) from HTML
        // markup — when diff is active, output contains inline <span> elements,
        // and textContent concatenates their text without any line separators.
        // writeSession.targetText holds the raw text with original newlines intact.
        const outputText = (this.state.writeSession && this.state.writeSession.targetText)
            ? this.state.writeSession.targetText
            : (() => {
                // Fallback: extract from DOM (no session available).
                // Remove diff-removed spans first so deleted words are not re-included.
                // Use innerHTML → replace <br> with \n to preserve paragraph breaks,
                // then strip remaining tags. textContent alone would strip <br> silently.
                const clone = output.cloneNode(true);
                clone.querySelectorAll('.diff-removed').forEach(el => el.remove());
                return clone.innerHTML
                    .replace(/<br\s*\/?>/gi, '\n')
                    .replace(/<[^>]+>/g, '')
                    .trim();
            })();
        if (!inputText || !outputText) return;

        if (this.state.diffViewEnabled && window.Diff) {
            output.innerHTML = this.renderDiff(inputText, outputText);
        } else {
            output.textContent = outputText;
        }
    },

    // ── Tab switching ────────────────────────────────────────────────────────

    switchTab(tab) {
        // Save current session before switching tabs (skip age check for immediate save)
        if (this.state.activeTab === 'translate' && this.state.translateSession.targetText) {
            this._saveSessionToHistory('translate', true);
        } else if (this.state.activeTab === 'write' && this.state.writeSession.targetText) {
            this._saveSessionToHistory('write', true);
        }
        
        this.state.activeTab = tab;
        document.querySelectorAll('.tab-btn').forEach(btn => {
            const isActive = btn.dataset.tab === tab;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        document.getElementById(`${tab}-panel`).classList.add('active');

        if (tab === 'history') {
            this.loadHistory();
        }
    },

    // ── Debounced input handlers ────────────────────────────────────────────

    _generateSessionId(text, targetLang = '') {
        // Simple hash function for session ID.
        // Includes targetLang so that translating the same text into different
        // languages produces distinct sessions — prevents spurious deduplication
        // when a user re-runs the same source text with a different target.
        const key = `${targetLang}::${text}`;
        let hash = 0;
        for (let i = 0; i < key.length; i++) {
            const char = key.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash | 0;  // Convert to 32-bit signed integer (prevents float overflow)
        }
        return hash.toString(36);
    },

    _saveSessionToHistory(type, skipAgeCheck = false) {
        const session = type === 'translate' ? this.state.translateSession : this.state.writeSession;
        
        // Only save if we have valid data
        if (!session.id || !session.sourceText || !session.targetText) {
            return;
        }

        // Use sessionStorage to prevent duplicate saves
        const saveKey = `history_saved_${session.id}`;
        if (sessionStorage.getItem(saveKey)) {
            return;
        }

        // Check session age - skip if explicitly requested (e.g., tab switch)
        if (!skipAgeCheck) {
            const sessionAge = Date.now() - (session.createdAt || 0);
            if (sessionAge < 3000) {
                return; // Don't save sessions younger than 3 seconds
            }
        }
        
        sessionStorage.setItem(saveKey, 'true');

        fetch('/api/history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                operation_type: type,
                source_text: session.sourceText,
                target_text: session.targetText,
                source_lang: session.sourceLang || null,
                target_lang: session.targetLang,
            }),
        }).then(res => {
            if (!res.ok) {
                console.error('[History] Save failed:', res.status);
                sessionStorage.removeItem(saveKey);
            }
        }).catch(err => {
            console.error('[History] Save error:', err);
            sessionStorage.removeItem(saveKey);
        });
    },

    /**
     * Shared input handler for both translate and write tabs.
     *
     * @param {string}   tab        'translate' | 'write'
     * @param {number}   debounceMs Debounce delay in ms before triggering the action.
     * @param {Function} action     Zero-arg function to call after the debounce.
     * @param {Function} [extraSetup] Optional callback called before session tracking,
     *                               used by translate to reset source-lang UI.
     */
    _onTextInput(tab, debounceMs, action, extraSetup) {
        const isTranslate = tab === 'translate';
        const inputId    = isTranslate ? 'input-text-translate' : 'input-text-write';
        const sessionKey = isTranslate ? 'translateSession' : 'writeSession';
        const timerKey   = isTranslate ? 'translateDebounceTimer' : 'writeDebounceTimer';

        const text = document.getElementById(inputId).value;
        this.updateCharCount(tab, text.length);
        clearTimeout(this.state[timerKey]);

        if (extraSetup) extraSetup(text);

        const targetLang = this.getTargetLang(tab);
        const sourceLang = isTranslate ? this.getSourceLang() : null;

        // Session ID includes targetLang so same text → different language = new session
        const newSessionId = text ? this._generateSessionId(text, targetLang) : null;
        const session = this.state[sessionKey];

        if (newSessionId && newSessionId !== session.id) {
            // Session changed: save old session if valid and old enough (>3 seconds)
            if (session.id && session.targetText) {
                const sessionAge = Date.now() - (session.createdAt || 0);
                if (sessionAge > 3000) {
                    this._saveSessionToHistory(tab, true);
                }
            }
            // Start new session
            this.state[sessionKey] = isTranslate
                ? { id: newSessionId, sourceText: text, sourceLang, targetLang, targetText: '', createdAt: Date.now() }
                : { id: newSessionId, sourceText: text, targetLang, targetText: '', createdAt: Date.now() };
        } else if (newSessionId) {
            // Same session, update source text
            session.sourceText = text;
            session.targetLang = targetLang;
            if (isTranslate) session.sourceLang = sourceLang;
        }

        if (text.trim()) {
            this.state[timerKey] = setTimeout(action, debounceMs);
        }
    },

    onTranslateInput() {
        this._onTextInput('translate', 2000, () => this.translate(), (text) => {
            // In auto mode: reset source to auto-detect BEFORE creating session
            if (this.state.useAutoDetection && text.trim()) {
                this._selectRadio('source-lang-radio', '');
                document.getElementById('source-lang').value = '';
                document.getElementById('detected-lang-display').classList.remove('visible');
                // Reset target to DE only if no explicit selection has been made yet
                if (!this.state.autoTargetChanged) {
                    this._selectRadio('target-lang', 'DE');
                    document.getElementById('target-lang-select').value = '';
                }
            }
        });
    },

    onWriteInput() {
        this._onTextInput('write', 2500, () => this.write());
    },

    // ── Language helpers ────────────────────────────────────────────────────

    getTargetLang(tab) {
        const name = tab === 'write' ? 'write-target-lang' : 'target-lang';
        
        // First check mobile dropdown (on mobile, this takes precedence)
        const mobileSelectId = tab === 'write' ? 'target-lang-mobile-write' : 'target-lang-mobile-translate';
        const mobileSelect = document.getElementById(mobileSelectId);
        if (mobileSelect && window.getComputedStyle(mobileSelect.parentElement).display !== 'none') {
            // Mobile dropdown is visible, use it
            if (mobileSelect.value) return mobileSelect.value;
        }
        
        // Then check radio buttons (desktop)
        const checked = document.querySelector(`input[name="${name}"]:checked`);
        if (checked) return checked.value;
        
        // Then check dropdown (desktop "Weitere...")
        const selectId = tab === 'write' ? 'write-target-lang-select' : 'target-lang-select';
        const select = document.getElementById(selectId);
        if (select && select.value) return select.value;
        
        return 'DE';
    },

    autoSelectTargetLang(tab, sourceLang) {
        if (!sourceLang) return;
        
        let targetLang;
        if (sourceLang === 'DE') {
            targetLang = 'EN-US';
        } else if (sourceLang.startsWith('EN')) {
            targetLang = 'DE';
        } else {
            return;
        }

        const radioName = tab === 'write' ? 'write-target-lang' : 'target-lang';
        const selectId = tab === 'write' ? 'write-target-lang-select' : 'target-lang-select';

        // Clear dropdown first
        document.getElementById(selectId).value = '';

        // Select the radio button
        const radios = document.querySelectorAll(`input[name="${radioName}"]`);
        radios.forEach(r => {
            r.checked = (r.value === targetLang);
        });
    },

    getSourceLang() {
        // First check mobile dropdown (on mobile, this takes precedence)
        const mobileSelect = document.getElementById('source-lang-mobile-translate');
        if (mobileSelect && window.getComputedStyle(mobileSelect.parentElement).display !== 'none') {
            // Mobile dropdown is visible, use it
            const value = mobileSelect.value;
            return value === '' ? null : value;  // Empty string = Auto
        }
        
        // Then check radio buttons (quick-select: Auto, Deutsch, Englisch)
        const checked = document.querySelector('input[name="source-lang-radio"]:checked');
        if (checked && checked.value) return checked.value;
        
        // Then check dropdown (Weitere...)
        const select = document.getElementById('source-lang');
        if (select && select.value) return select.value;
        
        return null;
    },

    getLangName(code) {
        // Use language names loaded from API, fallback to code if not found
        if (this.state.langNames && this.state.langNames[code]) {
            return this.state.langNames[code];
        }
        return code;
    },

    /**
     * Swaps source and target languages, then re-translates if there's text.
     * Only visible when both source and target are explicitly set.
     */
    _swapLanguages() {
        const sourceLang = this.getSourceLang();
        const targetLang = this.getTargetLang('translate');
        
        // Only swap if both are set (not "Auto" for source)
        if (!sourceLang || !targetLang) return;
        
        // Set new source = old target, new target = old source
        const newSource = targetLang;
        const newTarget = sourceLang;
        
        // Update source language UI (desktop)
        if (newSource === 'DE' || newSource === 'EN') {
            this._selectRadio('source-lang-radio', newSource);
            document.getElementById('source-lang').value = '';
        } else {
            this._selectRadio('source-lang-radio', '');
            document.getElementById('source-lang').value = newSource;
        }
        
        // Update target language UI (desktop)
        if (newTarget === 'DE' || newTarget === 'EN-US') {
            this._selectRadio('target-lang', newTarget);
            document.getElementById('target-lang-select').value = '';
        } else {
            this._selectRadio('target-lang', '');
            document.getElementById('target-lang-select').value = newTarget;
        }
        
        // Update mobile dropdowns
        const mobileSource = document.getElementById('source-lang-mobile-translate');
        const mobileTarget = document.getElementById('target-lang-mobile-translate');
        if (mobileSource) mobileSource.value = newSource;
        if (mobileTarget) mobileTarget.value = newTarget;
        
        // Re-translate if there's input text
        const input = document.getElementById('input-text-translate');
        if (input && input.value.trim()) {
            this.translate();
        }
    },

    /**
     * Updates visibility of the swap button based on language selection.
     */
    _updateSwapButtonVisibility() {
        const btn = document.getElementById('btn-swap-langs');
        const btnMobile = document.getElementById('btn-swap-langs-mobile-translate');
        
        const sourceLang = this.getSourceLang();
        const targetLang = this.getTargetLang('translate');
        
        // Only show when both source and target are explicitly selected
        const canSwap = !!(sourceLang && targetLang);
        
        if (btn) btn.disabled = !canSwap;
        if (btnMobile) btnMobile.disabled = !canSwap;
    },

    _selectRadio(name, value) {
        const radios = document.querySelectorAll(`input[name="${name}"]`);
        let found = false;
        radios.forEach(r => {
            if (r.value === value) { r.checked = true; found = true; }
        });
        if (!found && radios.length) radios[0].checked = true;
    },

    /**
     * Handle mobile language dropdown changes
     * @param {string} tab - 'translate' or 'write'
     * @param {string} type - 'source' or 'target'
     * @param {string} value - selected language code
     */
    _handleMobileLangChange(tab, type, value) {
        if (tab === 'translate' && type === 'source') {
            // Sync source language to desktop controls
            if (value === '' || value === 'DE' || value === 'EN') {
                this._selectRadio('source-lang-radio', value);
                document.getElementById('source-lang').value = '';
            } else {
                this._selectRadio('source-lang-radio', '');
                document.getElementById('source-lang').value = value;
            }
            
            // Update detected language display
            if (value) {
                this._hideDetectedLang();
            }
            
            // Update swap button visibility
            this._updateSwapButtonVisibility();
            
            // Re-translate if text exists
            const input = document.getElementById('input-text-translate');
            if (input && input.value.trim()) {
                this.translate();
            }
        } else if (tab === 'translate' && type === 'target') {
            // Sync target language to desktop controls
            const radioName = 'target-lang';
            const selectId = 'target-lang-select';
            
            if (value === 'DE' || value === 'EN-US') {
                this._selectRadio(radioName, value);
                document.getElementById(selectId).value = '';
            } else {
                this._selectRadio(radioName, '');
                document.getElementById(selectId).value = value;
            }
            
            // Update swap button visibility
            this._updateSwapButtonVisibility();
            
            // Re-translate if text exists
            const input = document.getElementById('input-text-translate');
            if (input && input.value.trim()) {
                this.translate();
            }
        } else if (tab === 'write' && type === 'source') {
            // Sync source language to desktop controls for Write tab
            const radioName = 'write-target-lang';
            const selectId = 'write-target-lang-select';
            
            if (value === 'DE' || value === 'EN') {
                this._selectRadio(radioName, value);
                document.getElementById(selectId).value = '';
            } else {
                this._selectRadio(radioName, '');
                document.getElementById(selectId).value = value;
            }
        }
    },

    /**
     * Set the Write-tab target language to the detected language.
     * For Write/Optimise the target language IS the text language — we optimise
     * the text in the language it was written in, so detected source == target.
     *
     * Only switches if the detected code has a radio button or dropdown option.
     */
    _selectWriteTargetLang(detected) {
        if (!detected || detected === 'unknown') return;

        const radioName = 'write-target-lang';
        const selectId  = 'write-target-lang-select';

        // Try radio buttons first (DE, EN-US)
        const radios = document.querySelectorAll(`input[name="${radioName}"]`);
        let matched = false;
        radios.forEach(r => {
            // Accept exact match or EN/EN-US equivalence
            const matches = r.value === detected ||
                (r.value === 'EN-US' && detected.startsWith('EN'));
            if (matches) { r.checked = true; matched = true; }
            else { r.checked = false; }
        });
        if (matched) {
            document.getElementById(selectId).value = '';
            return;
        }

        // Try the dropdown
        const select = document.getElementById(selectId);
        const optExists = Array.from(select.options).some(o => o.value === detected);
        if (optExists) {
            // Clear radios and select via dropdown
            radios.forEach(r => { r.checked = false; });
            select.value = detected;
        }
        // If not found at all, leave current selection unchanged
    },

    // ── Translate ───────────────────────────────────────────────────────────

    /**
     * Pre-detect source language before starting an LLM stream.
     *
     * Called only when useAutoDetection is true and no source language is
     * explicitly selected by the user. Sends the first 50 words to
     * POST /api/detect-lang and returns the detected DeepL language code
     * (e.g. "DE", "EN-US") or null on failure / when not applicable.
     *
     * @param {string} text  Full source text
     * @param {AbortSignal} signal  AbortController signal
     * @returns {Promise<string|null>}
     */
    async _preDetectLang(text, signal) {
        if (!this.state.useAutoDetection) return null;
        if (this.getSourceLang()) return null;  // user already picked a language
        if (!this.state.config?.llm_configured) return null;

        // Send only first 50 words — fast, cheap, sufficient
        const words = text.trim().split(/\s+/).slice(0, 50).join(' ');

        try {
            const res = await fetch('/api/detect-lang', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: words, max_words: 50 }),
                signal,
            });
            if (!res.ok) return null;
            const data = await res.json();
            return (data.detected_lang && data.detected_lang !== 'unknown')
                ? data.detected_lang
                : null;
        } catch {
            return null;  // AbortError or network failure — degrade gracefully
        }
    },

    /**
     * Update source language UI (badge + radio/dropdown) for a detected language.
     * Does NOT trigger re-translation. Pure UI update.
     *
     * @param {string} detected  DeepL language code e.g. "DE"
     */
    _applySourceLangUI(detected) {
        if (!detected || detected === 'unknown') return;

        this.state.detectedLang = detected;
        const badge = document.getElementById('detected-lang-display');
        if (badge) {
            badge.textContent = `${this.t('status.detected')} ${this.getLangName(detected)}`;
            badge.classList.add('visible');
        }

        // Sync radio buttons / dropdown
        const sourceRadioValue = detected === 'DE' ? 'DE'
            : detected.startsWith('EN') ? 'EN'
            : null;
        if (sourceRadioValue) {
            this._selectRadio('source-lang-radio', sourceRadioValue);
            const srcSelect = document.getElementById('source-lang');
            srcSelect.value = '';
            if (srcSelect.options[0]) srcSelect.options[0].selected = true;
        } else {
            this._selectRadio('source-lang-radio', '');
            const srcSelect = document.getElementById('source-lang');
            const optExists = Array.from(srcSelect.options).some(o => o.value === detected);
            if (optExists) srcSelect.value = detected;
        }
    },

    async translate() {
        const input  = document.getElementById('input-text-translate');
        const output = document.getElementById('output-text-translate');
        const text   = input.value.trim();
        if (!text) return;

        // Abort any in-flight translate request before starting a new one
        if (this.state.translateAbortController) {
            this.state.translateAbortController.abort();
        }
        this.state.translateAbortController = new AbortController();
        const signal = this.state.translateAbortController.signal;

        this.setLoading('translate', true);

        const sourceLang = this.getSourceLang();
        const targetLang = this.getTargetLang('translate');

        try {
            if (this.state.translateEngine === 'llm') {
                // ── LLM: Streaming path ──────────────────────────────────
                // Pre-detect source language so we know the correct target BEFORE streaming.
                // This eliminates the intermediate translation (Bug #2).
                const preDetected = await this._preDetectLang(text, signal);

                let effectiveTargetLang = targetLang;
                if (preDetected) {
                    // Show detected language badge and update source selection
                    this._applySourceLangUI(preDetected);
                    // Auto-switch target language (DE↔EN) based on detected source
                    this.autoSelectTargetLang('translate', preDetected);
                    effectiveTargetLang = this.getTargetLang('translate');
                }

                await this._translateLLMStream(text, preDetected || sourceLang, effectiveTargetLang, output, signal);
            } else {
                // ── DeepL: classic JSON path ─────────────────────────────
                await this._translateDeepL(text, sourceLang, targetLang, output, signal);
            }

            const btnCopyTranslate = document.getElementById('btn-copy-translate');
            if (btnCopyTranslate) btnCopyTranslate.style.display = '';
            
            // Show "Optimize Output" button after successful translation
            const btnOptimizeOutput = document.getElementById('btn-optimize-output');
            if (btnOptimizeOutput) btnOptimizeOutput.style.display = 'inline-flex';
            
            // Usage is refreshed on a 60 s interval; no need to reload after each translation.

        } catch (e) {
            // AbortError is expected when user starts a new request — suppress it
            if (e.name !== 'AbortError') this.showError(e.message);
        } finally {
            this.state.translateAbortController = null;
            this.setLoading('translate', false);
            this.state.autoTargetChanged = false;
        }
    },

    /**
     * Reads an SSE response body and calls onEvent(parsedEvent) for each
     * parsed SSE event. Throws on `event.error`. Handles reader lifecycle.
     */
    async _readSSEStream(res, onEvent) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete last line
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    let event;
                    try { event = JSON.parse(line.slice(6)); }
                    catch { continue; }
                    if (event.error) throw new Error(event.error);
                    onEvent(event);
                }
            }
        } catch (e) {
            // Cancel the underlying stream on error to release the connection cleanly.
            reader.cancel().catch(() => {});
            throw e;
        } finally {
            reader.releaseLock();
        }
    },

    async _translateLLMStream(text, sourceLang, targetLang, output, signal) {
        // Clear output and show streaming indicator
        output.value = '';
        this._setStreamingLabel('translate', true);
        this._setStreamingOverlay('translate', true);

        const res = await fetch('/api/translate/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                source_lang: sourceLang,
                target_lang: targetLang,
                engine: 'llm',
            }),
            signal,
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        if (!res.body) {
            throw new Error('Streaming wird von diesem Browser nicht unterstützt. Bitte aktualisiere deinen Browser.');
        }

        let accumulated = '';
        let detected = null;
        let reqTokensIn = 0, reqTokensOut = 0;

        await this._readSSEStream(res, (event) => {
            if (event.chunk) {
                accumulated += event.chunk;
                output.value = accumulated;
            }
            if (event.done) {
                detected = event.detected_source_lang || null;
                reqTokensIn = event.input_tokens || 0;
                reqTokensOut = event.output_tokens || 0;
            }
        });

        this._setStreamingLabel('translate', false);
        this._setStreamingOverlay('translate', false);
        if (reqTokensIn || reqTokensOut) this._showRequestTokens(reqTokensIn, reqTokensOut);

        // Stats bar: words/chars always; token/cost hidden (SSE has no usage data)
        this._updateOutputStats('translate', accumulated, null, true);

        // Fix A: Save session immediately after successful completion (targetText is now set)
        const sessionId = this._generateSessionId(text, targetLang);
        if (this.state.translateSession.id === sessionId) {
            this.state.translateSession.targetText = accumulated;
            this._saveSessionToHistory('translate', true);
        }

        // Handle language detection result - pass the AbortController signal
        this._applyDetectedLang('translate', detected, text, output, accumulated, signal);
    },

    async _translateDeepL(text, sourceLang, targetLang, output, signal) {
        const res = await fetch('/api/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                source_lang: sourceLang,
                target_lang: targetLang,
                engine: 'deepl',
            }),
            signal,
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();

        // Determine if we need to auto-switch target language BEFORE showing output
        const detected = data.detected_source_lang;
        const shouldAutoSwitch = this.state.useAutoDetection && detected &&
            ((detected === 'DE' && this.getTargetLang('translate') !== 'EN-US') ||
             (detected.startsWith('EN') && this.getTargetLang('translate') !== 'DE'));

        if (!shouldAutoSwitch) {
            output.value = data.translated_text;
        }

        const sessionId = this._generateSessionId(text, targetLang);
        if (this.state.translateSession.id === sessionId) {
            this.state.translateSession.targetText = data.translated_text;
            // Fix A: save immediately after successful completion
            this._saveSessionToHistory('translate', true);
        }

        // Stats bar: words/chars; no token/cost for DeepL
        this._updateOutputStats('translate', data.translated_text, null, false);

        // Apply detected language - signal already cleared since primary request is done
        this._applyDetectedLang('translate', detected, text, output, data.translated_text, undefined);

        // Token display (DeepL has none)
        document.getElementById('llm-token-display')?.style.setProperty('display', 'none');
    },

    _applyDetectedLang(tab, detected, text, output, translatedText, signal) {
        const detectedBadge = document.getElementById('detected-lang-display');
        const detectedBadgeMobile = document.getElementById('detected-lang-mobile-translate');

        if (!this.state.useAutoDetection) {
            detectedBadge?.classList.remove('visible');
            if (detectedBadgeMobile) detectedBadgeMobile.style.display = 'none';
            return;
        }

        if (!detected || detected === 'unknown') {
            detectedBadge?.classList.remove('visible');
            if (detectedBadgeMobile) detectedBadgeMobile.style.display = 'none';
            return;
        }

        this.state.detectedLang = detected;
        const detectedText = `${this.t('status.detected')} ${this.getLangName(detected)}`;
        
        // Update desktop badge
        if (detectedBadge) {
            detectedBadge.textContent = detectedText;
            detectedBadge.classList.add('visible');
        }
        
        // Update mobile badge
        if (detectedBadgeMobile) {
            detectedBadgeMobile.textContent = detectedText;
            detectedBadgeMobile.style.display = 'inline-flex';
        }

        // Sync detected language to source radio buttons / dropdown (desktop)
        // Only DE and EN variants have quick-select radios
        const sourceRadioValue = detected === 'DE' ? 'DE' : detected.startsWith('EN') ? 'EN' : null;
        if (sourceRadioValue) {
            this._selectRadio('source-lang-radio', sourceRadioValue);
            const srcSelect = document.getElementById('source-lang');
            if (srcSelect) {
                srcSelect.value = '';
                if (srcSelect.options[0]) srcSelect.options[0].selected = true;
            }
        } else {
            // Language not in radios — select via dropdown if possible, keep Auto radio
            this._selectRadio('source-lang-radio', '');
            const srcSelect = document.getElementById('source-lang');
            if (srcSelect) {
                // Try to select in dropdown
                const optExists = Array.from(srcSelect.options).some(o => o.value === detected);
                if (optExists) {
                    srcSelect.value = detected;
                }
            }
        }
        
        // Sync to mobile dropdown
        const mobileSource = document.getElementById('source-lang-mobile-translate');
        if (mobileSource) {
            mobileSource.value = detected;
        }

        const shouldAutoSwitch =
            (detected === 'DE' && this.getTargetLang(tab) !== 'EN-US') ||
            (detected.startsWith('EN') && this.getTargetLang(tab) !== 'DE');

        if (shouldAutoSwitch && this.state.translateEngine !== 'llm') {
            // DeepL only: re-translate with the corrected target language (non-streaming, fast).
            // For LLM engine, pre-detect already chose the right target before streaming started —
            // no second fetch needed.
            this.state.autoTargetChanged = true;
            this.autoSelectTargetLang(tab, detected);
            this.setLoading(tab, true);
            this.state.translateDebounceTimer = null;
            // Use the signal if provided (from primary request's AbortController)
            fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text,
                    source_lang: detected,
                    target_lang: this.getTargetLang(tab),
                    engine: 'deepl',
                }),
                signal,  // Use the AbortController signal if available
            })
            .then(r => r.ok ? r.json() : null)
            .then(data2 => {
                if (data2) {
                    output.value = data2.translated_text;
                    // Update session with the corrected target lang + text, then save.
                    // The session ID was generated with the old targetLang — regenerate it
                    // so _saveSessionToHistory can find and persist it correctly.
                    const session = tab === 'translate'
                        ? this.state.translateSession
                        : this.state.writeSession;
                    const newTargetLang = this.getTargetLang(tab);
                    session.targetLang = newTargetLang;
                    session.targetText = data2.translated_text;
                    session.id = this._generateSessionId(text, newTargetLang);
                    this._saveSessionToHistory(tab, true);
                }
                this.state.autoTargetChanged = false;
            })
            .catch(e => {
                // Ignore AbortError - expected when user starts a new request
                if (e.name !== 'AbortError') console.error('[App] Re-translate error:', e);
            })
            .finally(() => {
                this.setLoading(tab, false);
                this._setStreamingLabel(tab, false);
                this._setStreamingOverlay(tab, false);
            });
        } else if (shouldAutoSwitch && this.state.translateEngine === 'llm') {
            // LLM engine: pre-detect already corrected the target language before streaming.
            // Just update the target UI — no re-translate needed.
            this.autoSelectTargetLang(tab, detected);
            this.state.autoTargetChanged = false;
            if (output.value === '') output.value = translatedText;
            // Update session targetLang to the post-switch value and save.
            const session = tab === 'translate'
                ? this.state.translateSession
                : this.state.writeSession;
            const newTargetLang = this.getTargetLang(tab);
            if (session.id && session.targetText && session.targetLang !== newTargetLang) {
                session.targetLang = newTargetLang;
                session.id = this._generateSessionId(text, newTargetLang);
                this._saveSessionToHistory(tab, true);
            }
        } else {
            // Ensure output is set (for the case we held it back)
            if (output.value === '') output.value = translatedText;
        }
    },

    _setStreamingLabel(type, isStreaming) {
        const btn = document.getElementById(`btn-${type}`);
        if (!btn) return;
        if (isStreaming) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> ' + this.t('status.streaming');
        } else {
            btn.disabled = false;
            const label = type === 'translate' ? this.t('nav.translate') : this.t('nav.write');
            btn.innerHTML = `<i class="fas fa-bolt" aria-hidden="true"></i> ${label}`;
        }
    },

    /**
     * Show or hide the sticky streaming overlay banner at the bottom of the
     * output pane. Displayed while an LLM stream is in progress so the user
     * knows when streaming has finished — especially useful for long texts.
     * @param {'translate'|'write'} type
     * @param {boolean} visible
     */
    _setStreamingOverlay(type, visible) {
        const el = document.getElementById(`stream-overlay-${type}`);
        if (!el) return;
        el.style.display = visible ? 'flex' : 'none';
    },

    /**
     * Show per-request LLM token counts in the header stats area.
     * Called after each successful LLM streaming call.
     * @param {number} inputTokens
     * @param {number} outputTokens
     */
    _showRequestTokens(inputTokens, outputTokens) {
        const display = document.getElementById('llm-token-display');
        const sep     = document.getElementById('llm-req-sep');
        const inEl    = document.getElementById('llm-req-tokens-in');
        const outEl   = document.getElementById('llm-req-tokens-out');
        if (!display || !inEl || !outEl) return;
        inEl.textContent  = new Intl.NumberFormat('de-DE').format(inputTokens);
        outEl.textContent = new Intl.NumberFormat('de-DE').format(outputTokens);
        display.style.display = '';
        if (sep) sep.style.display = '';
    },

    /** Hide the per-request token display (e.g. on clear). */
    _hideRequestTokens() {
        const display = document.getElementById('llm-token-display');
        const sep     = document.getElementById('llm-req-sep');
        if (display) display.style.display = 'none';
        if (sep)     sep.style.display     = 'none';
    },

    /**
     * Auto-resize a textarea to fit its content using requestAnimationFrame.
     * Grows up to the CSS max-height, then scrolls.
     * Called on every input event.
     */
    _autoResizeTextarea(el) {
        // Cancel any pending frame request
        if (el._resizeFrameId) {
            cancelAnimationFrame(el._resizeFrameId);
        }
        
        // Schedule the resize for the next animation frame
        el._resizeFrameId = requestAnimationFrame(() => {
            el._resizeFrameId = null;
            el.style.height = 'auto';
            el.style.height = el.scrollHeight + 'px';
        });
    },

    // ── Write / Optimise ────────────────────────────────────────────────────

    async write() {
        const input  = document.getElementById('input-text-write');
        const output = document.getElementById('output-text-write');
        const text   = input.value.trim();
        if (!text) return;

        // Abort any in-flight write request before starting a new one
        if (this.state.writeAbortController) {
            this.state.writeAbortController.abort();
        }
        this.state.writeAbortController = new AbortController();
        const signal = this.state.writeAbortController.signal;

        this.setLoading('write', true);

        try {
            if (this.state.writeEngine === 'llm') {
                // ── LLM: Streaming path ──────────────────────────────────
                await this._writeLLMStream(text, output, signal);
            } else {
                // ── DeepL: classic JSON path ─────────────────────────────
                await this._writeDeepL(text, output, signal);
            }

            const btnCopyWrite = document.getElementById('btn-copy-write');
            if (btnCopyWrite) btnCopyWrite.style.display = '';
            
            // Show "Translate Output" button after successful optimization
            const btnTranslateOutput = document.getElementById('btn-translate-output');
            if (btnTranslateOutput) btnTranslateOutput.style.display = 'inline-flex';
            
            // Usage is refreshed on a 60 s interval; no need to reload after each write.

        } catch (e) {
            // AbortError is expected when user starts a new request — suppress it
            if (e.name !== 'AbortError') this.showError(e.message);
        } finally {
            this.state.writeAbortController = null;
            this.setLoading('write', false);
        }
    },

    async _writeLLMStream(text, output, signal) {
        // output-text-write is a <div> (uses textContent/innerHTML), unlike
        // output-text-translate which is a <textarea> (uses .value)
        output.textContent = '';
        this._setStreamingLabel('write', true);
        this._setStreamingOverlay('write', true);

        const res = await fetch('/api/write/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                target_lang: this.getTargetLang('write'),
                engine: 'llm',
            }),
            signal,
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        if (!res.body) {
            throw new Error('Streaming wird von diesem Browser nicht unterstützt. Bitte aktualisiere deinen Browser.');
        }

        let accumulated = '';
        let writeReqTokensIn = 0, writeReqTokensOut = 0;

        await this._readSSEStream(res, (event) => {
            if (event.chunk) {
                accumulated += event.chunk;
                // Show plain text while streaming; apply diff when done
                output.textContent = accumulated;
            }
            if (event.done) {
                writeReqTokensIn = event.input_tokens || 0;
                writeReqTokensOut = event.output_tokens || 0;
                if (event.detected_source_lang) {
                    // Auto-select the correct target language if LLM detected
                    // a different language than what is currently selected.
                    const detected = event.detected_source_lang;
                    const current = this.getTargetLang('write');
                    if (detected && detected !== 'unknown' && detected !== current) {
                        this._selectWriteTargetLang(detected);
                    }
                }
            }
        });

        this._setStreamingLabel('write', false);
        this._setStreamingOverlay('write', false);
        if (writeReqTokensIn || writeReqTokensOut) this._showRequestTokens(writeReqTokensIn, writeReqTokensOut);

        // Apply diff view now that we have the full text (respects toggle)
        if (this.state.diffViewEnabled && window.Diff) {
            output.innerHTML = this.renderDiff(text, accumulated);
        } else {
            output.textContent = accumulated;
        }

        this._updateChangesBadge(text, accumulated);

        // Stats bar: words/chars; token/cost hidden (SSE has no usage data)
        this._updateOutputStats('write', accumulated, null, true);

        // Update session and save immediately after successful completion (Fix A)
        const targetLang = this.getTargetLang('write');
        const sessionId = this._generateSessionId(text, targetLang);
        if (this.state.writeSession.id === sessionId) {
            this.state.writeSession.targetText = accumulated;
            this._saveSessionToHistory('write', true);
        }
    },

    async _writeDeepL(text, output, signal) {
        const res = await fetch('/api/write', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                target_lang: this.getTargetLang('write'),
                engine: 'deepl',
            }),
            signal,
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();

        // Display token usage (DeepL has none)
        document.getElementById('llm-token-display')?.style.setProperty('display', 'none');

        // Update session and save immediately after successful completion (Fix A)
        const sessionId = this._generateSessionId(text, this.getTargetLang('write'));
        if (this.state.writeSession.id === sessionId) {
            this.state.writeSession.targetText = data.optimized_text;
            this._saveSessionToHistory('write', true);
        }

        if (this.state.diffViewEnabled && window.Diff) {
            output.innerHTML = this.renderDiff(text, data.optimized_text);
        } else {
            output.textContent = data.optimized_text;
            if (this.state.diffViewEnabled && !window.Diff) {
                console.warn('[App] jsdiff nicht verfügbar — Diff-Anzeige deaktiviert.');
            }
        }

        this._updateChangesBadge(text, data.optimized_text);

        // Stats bar: words/chars; no token/cost for DeepL
        this._updateOutputStats('write', data.optimized_text, null, false);
    },

    // ── Diff rendering ──────────────────────────────────────────────────────

    /** Computes diff once and returns both HTML for output and word counts for badge.
     *  Caches the diff result to avoid computing it twice. */
    _computeDiff(original, optimized) {
        if (!window.Diff) return null;
        
        const diff = Diff.diffWords(original, optimized);
        
        // Build HTML for output
        let html = '';
        for (const part of diff) {
            const escaped = this.escapeHtml(part.value);
            if (part.added)        html += `<span class="diff-added">${escaped}</span>`;
            else if (part.removed) html += `<span class="diff-removed">${escaped}</span>`;
            else                   html += escaped;
        }
        
        // Count words for badge
        let add = 0, del = 0;
        diff.forEach(p => {
            if (p.added)   add++;
            if (p.removed) del++;
        });
        
        return { html, add, del };
    },

    renderDiff(original, optimized) {
        const result = this._computeDiff(original, optimized);
        return result ? result.html : '';
    },

    /** Renders the word-delta badge (+N -N) with split green/red coloring.
     *  Adds `has-changes` class to make the badge and its separator visible. */
    _updateChangesBadge(original, optimized) {
        const el = document.getElementById('write-changes');
        if (!el) return;
        if (!window.Diff) { el.classList.remove('has-changes'); el.innerHTML = ''; return; }

        const result = this._computeDiff(original, optimized);
        if (!result) { el.classList.remove('has-changes'); el.innerHTML = ''; return; }

        const { add, del } = result;

        if (add === 0 && del === 0) {
            el.classList.remove('has-changes');
            el.innerHTML = '';
            return;
        }

        const parts = [];
        if (add > 0) parts.push(`<span class="change-add">+${add}</span>`);
        if (del > 0) parts.push(`<span class="change-del">-${del}</span>`);
        el.innerHTML = parts.join('');
        el.classList.add('has-changes');
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        // Replace \n with <br> so that newlines render correctly when the
        // result is inserted via innerHTML (e.g. in renderDiff).
        // Without this, \n in HTML text-nodes has no visual effect, causing
        // words split across lines to appear concatenated (e.g. "Ein\nGedanke"
        // becomes "EinGedanke" instead of two separate lines).
        return div.innerHTML.replace(/\n/g, '<br>');
    },

    // ── Clear & pass-through ────────────────────────────────────────────────

    _clearPanel(tab) {
        const isTranslate = tab === 'translate';
        const abortKey  = isTranslate ? 'translateAbortController' : 'writeAbortController';
        const sessionKey = isTranslate ? 'translateSession' : 'writeSession';
        const timerKey  = isTranslate ? 'translateDebounceTimer' : 'writeDebounceTimer';
        const debugKey  = isTranslate ? '_debugTranslate' : '_debugWrite';

        // Cancel any in-flight request
        if (this.state[abortKey]) {
            this.state[abortKey].abort();
            this.state[abortKey] = null;
        }

        // Save current session before clearing (skipAgeCheck=true — explicit user action)
        const session = this.state[sessionKey];
        if (session.id && session.targetText) {
            this._saveSessionToHistory(tab, true);
        }

        // Clear input / output
        if (isTranslate) {
            document.getElementById('input-text-translate').value  = '';
            document.getElementById('output-text-translate').value = '';
            const badge = document.getElementById('detected-lang-display');
            if (badge) badge.classList.remove('visible');
            this.state.detectedLang = null;
            this.state.useAutoDetection = true;
            // Reset source radios to "Auto" and clear dropdown
            this._selectRadio('source-lang-radio', '');
            const srcSelect = document.getElementById('source-lang');
            srcSelect.value = '';
            if (srcSelect.options[0]) srcSelect.options[0].selected = true;
            // Reset target to defaults
            this._selectRadio('target-lang', 'DE');
            document.getElementById('target-lang-select').value = '';
        } else {
            document.getElementById('input-text-write').value      = '';
            document.getElementById('output-text-write').innerHTML = '';
            const writeChangesEl = document.getElementById('write-changes');
            if (writeChangesEl) { writeChangesEl.innerHTML = ''; writeChangesEl.classList.remove('has-changes'); }
            // Reset write target language to default (DE) so sticky LLM detection doesn't persist
            this._selectRadio('write-target-lang', 'DE');
            const writeLangSelect = document.getElementById('write-target-lang-select');
            if (writeLangSelect) writeLangSelect.value = '';
        }

        // Hide copy button and stats bar
        const btnCopy = document.getElementById(`btn-copy-${tab}`);
        if (btnCopy) btnCopy.style.display = 'none';
        const stats = document.getElementById(`output-stats-${tab}`);
        if (stats) stats.classList.remove('visible');
        
        // Hide output-related action buttons (optimize-output / translate-output)
        if (tab === 'translate') {
            const btnOptimizeOutput = document.getElementById('btn-optimize-output');
            if (btnOptimizeOutput) btnOptimizeOutput.style.display = 'none';
        } else if (tab === 'write') {
            const btnTranslateOutput = document.getElementById('btn-translate-output');
            if (btnTranslateOutput) btnTranslateOutput.style.display = 'none';
        }

        // Always hide streaming overlay on clear (guards against aborted streams)
        this._setStreamingOverlay(tab, false);

        this.updateCharCount(tab, 0);
        clearTimeout(this.state[timerKey]);

        // Clear debug panel.
        // Note: _debugTranslate/_debugWrite live on `this` (not this.state) because
        // they hold large debug objects added dynamically; access via this[debugKey].
        const debugPanel = document.getElementById(`debug-panel-${tab}`);
        if (debugPanel) debugPanel.style.display = 'none';
        document.getElementById(`btn-debug-${tab}`)?.classList.remove('active');
        this[debugKey] = null;

        // Hide per-request token display
        this._hideRequestTokens();

        // Reset session
        this.state[sessionKey] = isTranslate
            ? { id: null, sourceText: '', sourceLang: '', targetLang: '', targetText: '', createdAt: 0 }
            : { id: null, sourceText: '', targetLang: '', targetText: '', createdAt: 0 };
    },

    clearTranslate() {
        this._clearPanel('translate');
    },

    clearWrite() {
        this._clearPanel('write');
    },

    passToWrite() {
        const text = document.getElementById('output-text-translate').value;
        if (text) {
            this.switchTab('write');
            document.getElementById('input-text-write').value = text;
            this.onWriteInput();
        }
    },

    passToTranslate() {
        const output = document.getElementById('output-text-write');
        // Strip diff-removed spans, then read text
        const clone = output.cloneNode(true);
        clone.querySelectorAll('.diff-removed').forEach(el => el.remove());
        const text = (clone.textContent || clone.innerText || '').trim();
        if (text) {
            this.switchTab('translate');
            document.getElementById('input-text-translate').value = text;
            this.onTranslateInput();
        }
    },

    // ── New dual-optimize/translate button handlers ─────────────────────────

    handleOptimizeInput() {
        const inputText = document.getElementById('input-text-translate').value.trim();
        if (!inputText) {
            this.showError(this.t('errors.empty_input'));
            return;
        }
        
        // Text in Tab "Optimieren" übernehmen
        document.getElementById('input-text-write').value = inputText;
        this.switchTab('write');
        
        // Focus auf Input setzen
        document.getElementById('input-text-write').focus();
    },

    handleOptimizeOutput() {
        const outputText = this.state.translateSession.targetText || 
                           document.getElementById('output-text-translate').value.trim();
        
        if (!outputText) {
            this.showError(this.t('errors.no_translation'));
            return;
        }
        
        // Übersetzung in Tab "Optimieren" übernehmen
        document.getElementById('input-text-write').value = outputText;
        this.switchTab('write');
        
        document.getElementById('input-text-write').focus();
    },

    handleTranslateInput() {
        const inputText = document.getElementById('input-text-write').value.trim();
        if (!inputText) {
            this.showError(this.t('errors.empty_input'));
            return;
        }
        
        // Text in Tab "Übersetzen" übernehmen
        document.getElementById('input-text-translate').value = inputText;
        this.switchTab('translate');
        
        document.getElementById('input-text-translate').focus();
    },

    handleTranslateOutput() {
        const output = document.getElementById('output-text-write');
        // Strip diff-removed spans, then read text
        const clone = output.cloneNode(true);
        clone.querySelectorAll('.diff-removed').forEach(el => el.remove());
        const outputText = (clone.textContent || clone.innerText || '').trim();
        
        if (!outputText) {
            this.showError(this.t('errors.no_optimization'));
            return;
        }
        
        // Optimierung in Tab "Übersetzen" übernehmen
        document.getElementById('input-text-translate').value = outputText;
        this.switchTab('translate');
        
        document.getElementById('input-text-translate').focus();
    },

    // ── Clipboard ───────────────────────────────────────────────────────────

    async copyToClipboard(elementId) {
        const element = document.getElementById(elementId);
        let text;
        if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
            text = element.value;
        } else {
            const clone = element.cloneNode(true);
            clone.querySelectorAll('.diff-removed').forEach(el => el.remove());
            text = (clone.textContent || clone.innerText || '').trim();
        }
        try {
            await navigator.clipboard.writeText(text);
            this.showToast(this.t('notifications.copied'));
        } catch (e) {
            this.showError(this.t('notifications.copy_failed'));
        }
    },

    // ── UI helpers ──────────────────────────────────────────────────────────

    updateCharCount(type, count) {
        const el = document.getElementById(`chars-used-${type}`);
        if (el) el.textContent = this.formatNumber(count);
    },

    setLoading(type, loading) {
        const btn = document.getElementById(`btn-${type}`);
        if (!btn) return;
        if (loading) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> …';
        } else {
            btn.disabled  = false;
            const label   = type === 'translate' ? this.t('nav.translate') : this.t('nav.write');
            btn.innerHTML = `<i class="fas fa-bolt" aria-hidden="true"></i> ${label}`;
        }
    },

    // ── Usage display ────────────────────────────────────────────────────────

    _setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    },

    formatNumber(num) {
        if (num === null || num === undefined || isNaN(num)) return '0';
        return new Intl.NumberFormat(this.getNumberLocale()).format(Number(num));
    },

    // ── History ─────────────────────────────────────────────────────────────────

    async loadHistory() {
        const container = document.getElementById('history-list');
        try {
            const resp = await fetch('/api/history?limit=100');
            if (!resp.ok) throw new Error('Failed to load history');
            const data = await resp.json();

            if (!data.records || data.records.length === 0) {
                container.innerHTML = `
                    <div class="history-empty" style="text-align:center;padding:40px 20px;color:var(--text-muted);">
                        <i class="fas fa-history" style="font-size:32px;margin-bottom:12px;opacity:0.5;"></i>
                        <p>Noch keine Übersetzungen gespeichert.</p>
                    </div>`;
                return;
            }

            container.innerHTML = data.records.map(r => this._renderHistoryItem(r)).join('');

        // Bind delete events with custom confirmation
        container.querySelectorAll('.history-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = e.currentTarget.dataset.id;
                this._setupDeleteConfirmation(e.currentTarget, id);
            });
        });

        // Bind restore events
            container.querySelectorAll('.history-restore').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const id = e.currentTarget.dataset.id;
                    this.restoreHistory(id, data.records);
                });
            });

            // Bind to-write events
            container.querySelectorAll('.history-to-write').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const id = e.currentTarget.dataset.id;
                    this.passHistoryToWrite(id, data.records);
                });
            });

        } catch (e) {
            console.error('[History] Load error:', e);
            container.innerHTML = `<div class="history-empty" style="text-align:center;padding:40px 20px;color:var(--text-muted);"><p>Fehler beim Laden des Verlaufs.</p></div>`;
        }
    },

    _renderHistoryItem(record) {
        const date = new Date(record.created_at).toLocaleString('de-DE', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
        const sourcePreview = record.source_text.length > 80
            ? record.source_text.substring(0, 80) + '...'
            : record.source_text;
        const opIcon = record.operation_type === 'translate' ? 'fa-language' : 'fa-pencil-alt';
        const opLabel = record.operation_type === 'translate' ? 'Übersetzung' : 'Optimierung';
        const sourceLang = record.source_lang ? ` von ${this._escapeHtml(this.state.langNames[record.source_lang] || record.source_lang)}` : '';
        const targetLang = this._escapeHtml(this.state.langNames[record.target_lang] || record.target_lang);

        return `
            <div class="history-item" data-id="${record.id}">
                <div class="history-item-header">
                    <span class="history-op"><i class="fas ${opIcon}" aria-hidden="true"></i> ${this._escapeHtml(opLabel)}</span>
                    <span class="history-lang">${this._escapeHtml(sourceLang)} → ${targetLang}</span>
                    <span class="history-date">${this._escapeHtml(date)}</span>
                </div>
                <div class="history-item-content">
                    <div class="history-source">${this._escapeHtml(sourcePreview)}</div>
                </div>
                <div class="history-item-actions">
                    <button class="btn btn-sm btn-ghost history-restore" data-id="${record.id}" title="Wiederherstellen">
                        <i class="fas fa-redo" aria-hidden="true"></i> Laden
                    </button>
                    <button class="btn btn-sm btn-ghost history-to-write" data-id="${record.id}" title="An Optimierer senden">
                        <i class="fas fa-pencil-alt" aria-hidden="true"></i> Optimieren
                    </button>
                    <button class="btn btn-sm btn-ghost history-delete" data-id="${record.id}" title="Löschen">
                        <i class="fas fa-trash-alt" aria-hidden="true"></i><span class="sr-only">Löschen</span>
                    </button>
                </div>
            </div>`;
    },

    /**
     * Converts a delete button to confirmation mode, then deletes on second click.
     * @param {HTMLElement} btn - The delete button element
     * @param {string} id - The history record ID to delete
     */
    _setupDeleteConfirmation(btn, id) {
        const originalHTML = btn.innerHTML;
        const isConfirmMode = btn.dataset.confirm === 'true';
        
        if (isConfirmMode) {
            // Second click - actually delete
            this._deleteHistoryItem(id);
            return;
        }
        
        // First click - show confirmation state
        btn.dataset.confirm = 'true';
        btn.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> Ja?';
        btn.classList.add('btn-danger');
        
        // Reset after 3 seconds if user doesn't confirm
        setTimeout(() => {
            btn.dataset.confirm = 'false';
            btn.innerHTML = originalHTML;
            btn.classList.remove('btn-danger');
        }, 3000);
    },

    async _deleteHistoryItem(id) {
        try {
            const resp = await fetch(`/api/history/${id}`, { method: 'DELETE' });
            if (!resp.ok) throw new Error('Delete failed');
            this.showToast('Eintrag gelöscht');
            this.loadHistory();
        } catch (e) {
            console.error('[History] Delete error:', e);
            this.showError(this.t('notifications.delete_failed'));
        }
    },

    restoreHistory(id, records) {
        const record = records.find(r => r.id == id);
        if (!record) return;

        document.getElementById('input-text-translate').value = record.source_text;
        document.getElementById('output-text-translate').value = record.target_text;
        this._selectRadio('target-lang', record.target_lang);
        if (record.source_lang) {
            // Sync source language to radio buttons or dropdown
            const radioValue = record.source_lang === 'DE' ? 'DE' : (record.source_lang === 'EN' || record.source_lang.startsWith('EN')) ? 'EN' : null;
            if (radioValue) {
                this._selectRadio('source-lang-radio', radioValue);
                const srcSelect = document.getElementById('source-lang');
                srcSelect.value = '';
                if (srcSelect.options[0]) srcSelect.options[0].selected = true;
            } else {
                this._selectRadio('source-lang-radio', '');
                document.getElementById('source-lang').value = record.source_lang;
            }
        } else {
            this._selectRadio('source-lang-radio', '');
            const srcSelect = document.getElementById('source-lang');
            srcSelect.value = '';
            if (srcSelect.options[0]) srcSelect.options[0].selected = true;
        }
        
        // Set session to restored data (but mark as already saved)
        const sessionId = this._generateSessionId(record.source_text, record.target_lang);
        this.state.translateSession = {
            id: sessionId,
            sourceText: record.source_text,
            sourceLang: record.source_lang || '',
            targetLang: record.target_lang,
            targetText: record.target_text,
            createdAt: Date.now(),
        };
        // Mark this session as already saved
        sessionStorage.setItem(`history_saved_${sessionId}`, 'true');
        
        this.switchTab('translate');
        
        // Show copy button
        document.getElementById('btn-copy-translate')?.style.setProperty('display', '');
        
        // Reset auto detection state since we're restoring old translation
        this.state.useAutoDetection = false;
    },

    passHistoryToWrite(id, records) {
        const record = records.find(r => r.id == id);
        if (!record) return;

        document.getElementById('input-text-write').value = record.source_text;
        document.getElementById('output-text-write').textContent = record.target_text;
        this._selectRadio('write-target-lang', record.target_lang);
        
        // Set session to restored data (but mark as already saved)
        const sessionId = this._generateSessionId(record.source_text, record.target_lang);
        this.state.writeSession = {
            id: sessionId,
            sourceText: record.source_text,
            targetLang: record.target_lang,
            targetText: record.target_text,
            createdAt: Date.now(),
        };
        // Mark this session as already saved
        sessionStorage.setItem(`history_saved_${sessionId}`, 'true');
        
        this.switchTab('write');
        
        // Show copy button
        document.getElementById('btn-copy-write')?.style.setProperty('display', '');
    },

    /**
     * Converts the "Clear All" button to confirmation mode.
     * @param {HTMLElement} btn - The clear all button element
     */
    _setupClearAllConfirmation(btn) {
        const originalHTML = btn.innerHTML;
        const isConfirmMode = btn.dataset.confirm === 'true';
        
        if (isConfirmMode) {
            // Second click - actually delete all
            this._clearAllHistory();
            return;
        }
        
        // First click - show confirmation state
        btn.dataset.confirm = 'true';
        btn.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> Alles löschen?';
        btn.classList.add('btn-danger');
        
        // Reset after 4 seconds if user doesn't confirm
        setTimeout(() => {
            btn.dataset.confirm = 'false';
            btn.innerHTML = originalHTML;
            btn.classList.remove('btn-danger');
        }, 4000);
    },

    async _clearAllHistory() {
        try {
            const resp = await fetch('/api/history', { method: 'DELETE' });
            if (!resp.ok) throw new Error('Delete all failed');
            this.showToast('Verlauf gelöscht');
            this.loadHistory();
        } catch (e) {
            console.error('[History] Clear all error:', e);
            this.showError(this.t('notifications.delete_failed'));
        }
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // ── Output Statistics ─────────────────────────────────────────────────────

    /**
     * Update the output stats bar for a given tab.
     *
     * @param {string}      tab         'translate' | 'write'
     * @param {string}      text        The output text (plain, stripped of diff markup)
     * @param {object|null} usage       { input_tokens, output_tokens } or null (unused, kept for API compat)
     * @param {boolean}     isStreaming  True when called from SSE stream (no usage data)
     */
    _updateOutputStats(tab, text, usage, isStreaming) {
        const container = document.getElementById(`output-stats-${tab}`);
        if (!container) return;

        // ── Word / char count (always shown) ──────────────────────────────
        const charCount = text.length;
        const wordCount = text.trim() === '' ? 0 : text.trim().split(/\s+/).length;

        this._setText(`output-words-${tab}`, this.formatNumber(wordCount));
        this._setText(`output-chars-${tab}`, this.formatNumber(charCount));

        // Show the stats bar
        container.classList.add('visible');
    },

    async _loadUsageSummary() {
        try {
            const res = await fetch('/api/usage/summary');
            if (!res.ok) return;
            const data = await res.json();

            const fmt = (n) => this.formatNumber(n);

            const el = document.getElementById('cumulative-stats');
            if (!el) return;

            document.getElementById('cum-words-translate').textContent = fmt(data.translate.words);
            document.getElementById('cum-words-write').textContent = fmt(data.write.words);

            // Always show LLM tokens (even if 0 or null)
            const llmIn = data.llm ? data.llm.input_tokens : 0;
            const llmOut = data.llm ? data.llm.output_tokens : 0;
            const llmTotal = llmIn + llmOut;
            document.getElementById('cum-tokens-in').textContent = fmt(llmIn);
            document.getElementById('cum-tokens-out').textContent = fmt(llmOut);
            document.getElementById('cum-tokens-total').textContent = fmt(llmTotal);
            const cumStats = document.getElementById('cum-llm-stats');
            if (cumStats) cumStats.style.display = 'inline';
            const cumSep = document.getElementById('cum-llm-sep');
            if (cumSep) cumSep.style.display = 'inline';

            el.style.display = 'flex';
        } catch (e) {
            console.warn('[App] Usage summary failed:', e);
        }
    },

    // ── Notifications ────────────────────────────────────────────────────────

    /**
     * Show an error message to the user.
     * If the message is an error code (e.g., 'ERR_TRANSLATE_FAILED'), translate it.
     * @param {string} message - Error message or error code
     */
    showError(message) {
        // Check if message is an error code and translate it
        if (typeof message === 'string' && message.startsWith('ERR_')) {
            message = this.t(`errors.${message}`);
        }
        this._showNotification(message, 'error-toast', 4000);
    },

    /**
     * Show a success toast to the user.
     * @param {string} message - Success message
     */
    showToast(message) {
        // Check if message is a translation key
        if (typeof message === 'string' && this.state.translations[message]) {
            message = this.t(message);
        }
        this._showNotification(message, 'success-toast', 2000);
    },

    _showNotification(message, cssClass, duration) {
        const existing = document.querySelector(`.${cssClass}`);
        if (existing) existing.remove();
        const el = document.createElement('div');
        el.className   = cssClass;
        el.textContent = message;
        el.setAttribute('role', 'alert');
        el.setAttribute('aria-live', 'assertive');
        document.body.appendChild(el);
        setTimeout(() => el.remove(), duration);
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
