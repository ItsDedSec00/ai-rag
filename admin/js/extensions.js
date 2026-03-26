// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Extensions page (ADM-EXT): catalog, toggle, config drawer.
 * Mockup — no backend integration yet.
 */

const Extensions = (() => {

    // Per-extension config schema (mockup data)
    const EXT_CONFIG = {
        websearch: {
            name: 'Websuche',
            icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
            fields: [
                { id: 'ws-engine', label: 'Suchmaschine', type: 'select', options: ['DuckDuckGo', 'SearXNG (selbst gehostet)'], value: 'DuckDuckGo' },
                { id: 'ws-results', label: 'Max. Ergebnisse', type: 'number', min: 1, max: 10, value: 3, hint: 'Wie viele Suchergebnisse in den Kontext geladen werden' },
                { id: 'ws-safe', label: 'SafeSearch', type: 'toggle', value: true, hint: 'Unangemessene Inhalte herausfiltern' },
                { id: 'ws-timeout', label: 'Timeout (Sekunden)', type: 'number', min: 1, max: 30, value: 5 },
            ],
        },
        webhook: {
            name: 'Webhook',
            icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
            fields: [
                { id: 'wh-url', label: 'Webhook-URL', type: 'text', value: '', placeholder: 'https://example.com/webhook' },
                { id: 'wh-secret', label: 'Secret (HMAC)', type: 'password', value: '', placeholder: 'Optionaler Signatur-Token' },
                { id: 'wh-on-chat', label: 'Bei Chat-Anfrage', type: 'toggle', value: true },
                { id: 'wh-on-upload', label: 'Bei Datei-Upload', type: 'toggle', value: false },
                { id: 'wh-on-error', label: 'Bei Fehler', type: 'toggle', value: true },
            ],
        },
        email: {
            name: 'E-Mail-Benachrichtigungen',
            icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`,
            fields: [
                { id: 'em-smtp', label: 'SMTP-Server', type: 'text', value: '', placeholder: 'smtp.example.com' },
                { id: 'em-port', label: 'Port', type: 'number', min: 1, max: 65535, value: 587 },
                { id: 'em-user', label: 'Benutzername', type: 'text', value: '', placeholder: 'user@example.com' },
                { id: 'em-pass', label: 'Passwort', type: 'password', value: '', placeholder: '••••••••' },
                { id: 'em-from', label: 'Absender', type: 'text', value: '', placeholder: 'rag-chat@example.com' },
                { id: 'em-to', label: 'Empfänger', type: 'text', value: '', placeholder: 'admin@example.com', hint: 'Mehrere Adressen kommagetrennt' },
                { id: 'em-on-error', label: 'Bei Systemfehler', type: 'toggle', value: true },
                { id: 'em-on-update', label: 'Bei verfügbarem Update', type: 'toggle', value: true },
            ],
        },
        autosummary: {
            name: 'Automatische Zusammenfassung',
            icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
            fields: [
                { id: 'as-lang', label: 'Sprache der Zusammenfassung', type: 'select', options: ['Automatisch', 'Deutsch', 'Englisch'], value: 'Automatisch' },
                { id: 'as-length', label: 'Max. Länge (Wörter)', type: 'number', min: 50, max: 500, value: 150 },
                { id: 'as-formats', label: 'Nur für Dateitypen', type: 'text', value: 'pdf, docx', hint: 'Kommagetrennte Dateierweiterungen' },
            ],
        },
    };

    // =================================================================
    // Drawer
    // =================================================================

    function _openDrawer(extId) {
        const cfg = EXT_CONFIG[extId];
        if (!cfg) return;

        document.getElementById('ext-drawer-name').textContent = cfg.name;
        document.getElementById('ext-drawer-icon').innerHTML = cfg.icon;

        const body = document.getElementById('ext-drawer-body');
        body.innerHTML = cfg.fields.map(f => _renderField(f)).join('');

        document.getElementById('ext-overlay').classList.remove('hidden');
        document.getElementById('ext-drawer').classList.remove('hidden');
        requestAnimationFrame(() => document.getElementById('ext-drawer').classList.add('open'));
    }

    function _closeDrawer() {
        const drawer = document.getElementById('ext-drawer');
        drawer.classList.remove('open');
        setTimeout(() => {
            drawer.classList.add('hidden');
            document.getElementById('ext-overlay').classList.add('hidden');
        }, 250);
    }

    function _renderField(f) {
        const hint = f.hint ? `<div class="param-hint">${f.hint}</div>` : '';
        if (f.type === 'toggle') {
            return `
            <div class="ext-field">
                <div class="ext-field-toggle-row">
                    <label class="ext-field-label">${f.label}</label>
                    <label class="toggle-switch">
                        <input type="checkbox" id="${f.id}" ${f.value ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                ${hint}
            </div>`;
        }
        if (f.type === 'select') {
            const opts = f.options.map(o => `<option ${o === f.value ? 'selected' : ''}>${o}</option>`).join('');
            return `
            <div class="ext-field">
                <label class="ext-field-label" for="${f.id}">${f.label}</label>
                <select id="${f.id}" class="param-select">${opts}</select>
                ${hint}
            </div>`;
        }
        if (f.type === 'password') {
            return `
            <div class="ext-field">
                <label class="ext-field-label" for="${f.id}">${f.label}</label>
                <input type="password" id="${f.id}" class="param-text-input ext-text-full" value="${f.value}" placeholder="${f.placeholder || ''}">
                ${hint}
            </div>`;
        }
        if (f.type === 'number') {
            return `
            <div class="ext-field">
                <label class="ext-field-label" for="${f.id}">${f.label}</label>
                <input type="number" id="${f.id}" class="param-text-input" value="${f.value}" min="${f.min ?? ''}" max="${f.max ?? ''}">
                ${hint}
            </div>`;
        }
        // text
        return `
        <div class="ext-field">
            <label class="ext-field-label" for="${f.id}">${f.label}</label>
            <input type="text" id="${f.id}" class="param-text-input ext-text-full" value="${f.value}" placeholder="${f.placeholder || ''}">
            ${hint}
        </div>`;
    }

    // =================================================================
    // Toggle + filter
    // =================================================================

    function _handleToggle(checkbox) {
        const extId = checkbox.dataset.ext;
        const card = checkbox.closest('.ext-card');
        const statusText = card.querySelector('.ext-status-text');
        const statusDot = card.querySelector('.ext-status-dot');
        if (checkbox.checked) {
            card.classList.add('ext-enabled');
            statusText.textContent = 'Aktiv';
            statusText.classList.remove('muted');
            statusDot.classList.add('active');
        } else {
            card.classList.remove('ext-enabled');
            statusText.textContent = 'Inaktiv';
            statusText.classList.add('muted');
            statusDot.classList.remove('active');
        }
    }

    function _applyFilter(filter) {
        document.querySelectorAll('.ext-filter').forEach(b => b.classList.remove('active'));
        document.querySelector(`.ext-filter[data-filter="${filter}"]`)?.classList.add('active');

        document.querySelectorAll('.ext-card').forEach(card => {
            const state = card.dataset.state;
            const isEnabled = card.classList.contains('ext-enabled');
            if (filter === 'all') {
                card.style.display = '';
            } else if (filter === 'active') {
                card.style.display = isEnabled ? '' : 'none';
            } else if (filter === 'available') {
                card.style.display = (state === 'available' || state === 'soon') ? '' : 'none';
            }
        });

        // Hide section labels if empty
        document.querySelectorAll('.ext-section-label').forEach(label => {
            const grid = label.nextElementSibling;
            if (!grid) return;
            const visible = [...grid.querySelectorAll('.ext-card')].some(c => c.style.display !== 'none');
            label.style.display = visible ? '' : 'none';
        });
    }

    function _applySearch(query) {
        const q = query.toLowerCase();
        document.querySelectorAll('.ext-card').forEach(card => {
            const name = card.querySelector('.ext-name')?.textContent.toLowerCase() || '';
            const desc = card.querySelector('.ext-desc')?.textContent.toLowerCase() || '';
            const tag = card.querySelector('.ext-tag')?.textContent.toLowerCase() || '';
            card.style.display = (!q || name.includes(q) || desc.includes(q) || tag.includes(q)) ? '' : 'none';
        });
    }

    // =================================================================
    // Init
    // =================================================================

    function init() {
        // Config buttons
        document.querySelectorAll('.btn-ext-config').forEach(btn => {
            btn.addEventListener('click', () => _openDrawer(btn.dataset.ext));
        });

        // Toggles
        document.querySelectorAll('.ext-toggle-wrap input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => _handleToggle(cb));
        });

        // Drawer close
        document.getElementById('ext-drawer-close')?.addEventListener('click', _closeDrawer);
        document.getElementById('ext-drawer-cancel')?.addEventListener('click', _closeDrawer);
        document.getElementById('ext-overlay')?.addEventListener('click', _closeDrawer);

        // Save (mockup — just closes)
        document.getElementById('ext-drawer-save')?.addEventListener('click', () => {
            _closeDrawer();
        });

        // Filter tabs
        document.querySelectorAll('.ext-filter').forEach(btn => {
            btn.addEventListener('click', () => _applyFilter(btn.dataset.filter));
        });

        // Search
        document.getElementById('ext-search')?.addEventListener('input', e => _applySearch(e.target.value));
    }

    return { init };

})();

document.addEventListener('DOMContentLoaded', Extensions.init);
