/**
 * Senten — Keyboard Shortcuts
 *
 * Shortcuts:
 *   Ctrl+Enter   Trigger the active tab's action (translate / optimise)
 *   Ctrl+1       Switch to the Translate tab
 *   Ctrl+2       Switch to the Optimise (Write) tab
 *   Ctrl+D       Toggle dark/light mode (preserves colour palette)
 *   Escape       Clear the active tab's input and output
 */
(function () {
    'use strict';

    function getActiveTab() {
        const btn = document.querySelector('.tab-btn.active');
        return btn ? btn.dataset.tab : null;
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.addEventListener('keydown', function (e) {
            const tag = (document.activeElement && document.activeElement.tagName) || '';

            // --- Ctrl+Enter: trigger active action ---
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                const tab = getActiveTab();
                if (tab === 'translate') {
                    const btn = document.getElementById('btn-translate');
                    if (btn) btn.click();
                } else if (tab === 'write') {
                    const btn = document.getElementById('btn-write');
                    if (btn) btn.click();
                }
                return;
            }

            // Skip global shortcuts when the user is typing in an input/textarea
            const isTyping = (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT');

            // --- Ctrl+1: switch to Translate tab ---
            if (e.ctrlKey && e.key === '1') {
                e.preventDefault();
                const btn = document.getElementById('tab-translate');
                if (btn) btn.click();
                return;
            }

            // --- Ctrl+2: switch to Write tab ---
            if (e.ctrlKey && e.key === '2') {
                e.preventDefault();
                const btn = document.getElementById('tab-write');
                if (btn) btn.click();
                return;
            }

            // --- Ctrl+D: toggle dark/light mode (preserves colour palette) ---
            if (e.ctrlKey && (e.key === 'd' || e.key === 'D')) {
                e.preventDefault();
                const current = document.documentElement.getAttribute('data-theme') || 'light-blue';
                // Map current theme to its opposite mode, keeping the palette
                const toggleMap = {
                    'light-blue':   'dark-blue',
                    'dark-blue':    'light-blue',
                    'light-violet': 'dark-violet',
                    'dark-violet':  'light-violet',
                    // Legacy fallbacks
                    'dark':  'light-blue',
                    'light': 'dark-blue',
                };
                const next = toggleMap[current] || 'dark-blue';
                const custom = localStorage.getItem('theme-accent-custom');
                if (typeof App !== 'undefined' && App.applyTheme) {
                    App.applyTheme(next, custom || null);
                }
                return;
            }

            // --- Escape: clear active tab (only when not inside an editable field) ---
            if (e.key === 'Escape' && !isTyping) {
                e.preventDefault();
                const tab = getActiveTab();
                if (tab === 'translate') {
                    App.clearTranslate();
                } else if (tab === 'write') {
                    App.clearWrite();
                }
            }
        });
    });
}());
