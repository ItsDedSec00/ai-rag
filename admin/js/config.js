// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Config Manager (ADM-06): view/edit config,
 * export/import, snapshot management.
 * Auto-saves on every change (debounced).
 */

const Config = (() => {

    const API = '/api/admin/config';
    let _cfg = null;      // current config mirror
    let _loaded = false;
    let _saveTimer = null;
    let _mode = 'simple'; // 'simple' or 'advanced'

    // Config field mapping: id → section.key
    // LLM settings (ollama.*) are managed in the Models tab
    const FIELDS = [
        // RAG
        { id: 'cfg-rag-embedding_model',       section: 'rag',      key: 'embedding_model',    type: 'text' },
        { id: 'cfg-rag-chunk_size',            section: 'rag',      key: 'chunk_size',          type: 'number' },
        { id: 'cfg-rag-chunk_overlap',         section: 'rag',      key: 'chunk_overlap',       type: 'number' },
        { id: 'cfg-rag-top_k',                 section: 'rag',      key: 'top_k',               type: 'number' },
        { id: 'cfg-rag-min_score',             section: 'rag',      key: 'min_score',           type: 'number' },
        { id: 'cfg-rag-display_sources',       section: 'rag',      key: 'display_sources',     type: 'number' },
        { id: 'cfg-rag-reindex_on_change',     section: 'rag',      key: 'reindex_on_change',   type: 'bool' },
        // Server
        { id: 'cfg-server-max_upload_mb',      section: 'server',   key: 'max_upload_mb',       type: 'number' },
        { id: 'cfg-server-session_timeout_min',section: 'server',   key: 'session_timeout_min', type: 'number' },
        { id: 'cfg-server-log_level',          section: 'server',   key: 'log_level',           type: 'text' },
        { id: 'cfg-server-indexer_interval_sec',section: 'server',  key: 'indexer_interval_sec',type: 'number' },
        // Chat
        { id: 'cfg-chat-welcome_message',      section: 'chat',     key: 'welcome_message',     type: 'text' },
        { id: 'cfg-chat-placeholder',          section: 'chat',     key: 'placeholder',         type: 'text' },
        { id: 'cfg-chat-history_limit',        section: 'chat',     key: 'history_limit',       type: 'number' },
        { id: 'cfg-chat-markdown_enabled',     section: 'chat',     key: 'markdown_enabled',    type: 'bool' },
        // Branding
        { id: 'cfg-branding-app_name',         section: 'branding', key: 'app_name',            type: 'text' },
        { id: 'cfg-branding-logo_url',         section: 'branding', key: 'logo_url',            type: 'text' },
        { id: 'cfg-branding-primary_color',    section: 'branding', key: 'primary_color',       type: 'text' },
    ];


    // =================================================================
    // Load & render
    // =================================================================

    async function load() {
        try {
            const r = await fetch(API);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            _cfg = await r.json();
            _loaded = true;
            _populateFields();
            _loadSnapshots();
        } catch (e) {
            console.error('Config load failed:', e);
        }
    }

    function _populateFields() {
        for (const f of FIELDS) {
            const el = document.getElementById(f.id);
            if (!el) continue;
            const val = (_cfg[f.section] || {})[f.key];
            if (val === undefined) continue;

            if (f.type === 'bool') {
                el.value = val ? 'true' : 'false';
            } else {
                el.value = val;
            }
        }
        // Sync color picker
        const colorText = document.getElementById('cfg-branding-primary_color');
        const colorPicker = document.getElementById('cfg-branding-primary_color_picker');
        if (colorText && colorPicker) colorPicker.value = colorText.value || '#3b82f6';
    }

    function _readFields() {
        // Start from current config, then overlay form values
        const out = JSON.parse(JSON.stringify(_cfg || {}));
        for (const f of FIELDS) {
            if (f.readonly) continue;
            const el = document.getElementById(f.id);
            if (!el) continue;
            if (!out[f.section]) out[f.section] = {};

            if (f.type === 'number') {
                out[f.section][f.key] = Number(el.value);
            } else if (f.type === 'bool') {
                out[f.section][f.key] = el.value === 'true';
            } else {
                out[f.section][f.key] = el.value;
            }
        }
        return out;
    }


    // =================================================================
    // Auto-save (debounced)
    // =================================================================

    function _debounceSave() {
        clearTimeout(_saveTimer);
        _saveTimer = setTimeout(save, 400);
    }

    async function save() {
        const updated = _readFields();
        try {
            const r = await fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config: updated }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            _cfg = data.config;
            _flash('config-saved-msg', 'Gespeichert');
        } catch (e) {
            console.error('Config save failed:', e);
        }
    }


    // =================================================================
    // Simple / Advanced mode
    // =================================================================

    function _setMode(mode) {
        _mode = mode;
        const btnSimple = document.getElementById('btn-mode-simple');
        const btnAdvanced = document.getElementById('btn-mode-advanced');
        if (btnSimple && btnAdvanced) {
            btnSimple.classList.toggle('btn-accent', mode === 'simple');
            btnAdvanced.classList.toggle('btn-accent', mode === 'advanced');
        }

        document.querySelectorAll('.config-group[data-mode="advanced"]').forEach(g => {
            g.style.display = mode === 'advanced' ? '' : 'none';
        });
    }


    // =================================================================
    // Export / Import
    // =================================================================

    function exportConfig() {
        const json = JSON.stringify(_cfg || {}, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'rag-config.json';
        a.click();
        URL.revokeObjectURL(url);
    }

    async function importConfig(file) {
        const fd = new FormData();
        fd.append('file', file);
        try {
            const r = await fetch(API + '/import', { method: 'POST', body: fd });
            if (!r.ok) {
                const err = await r.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${r.status}`);
            }
            const data = await r.json();
            _cfg = data.config;
            _populateFields();
            _loadSnapshots();
            _flash('config-saved-msg', 'Importiert');
        } catch (e) {
            alert('Import fehlgeschlagen: ' + e.message);
        }
    }


    // =================================================================
    // Snapshots
    // =================================================================

    async function _loadSnapshots() {
        try {
            const r = await fetch(API + '/snapshots');
            if (!r.ok) return;
            const data = await r.json();
            _renderSnapshots(data.snapshots || []);
        } catch (e) {
            console.error('Snapshots load failed:', e);
        }
    }

    function _renderSnapshots(snaps) {
        const cont = document.getElementById('snapshots-list');
        if (!cont) return;

        if (snaps.length === 0) {
            cont.innerHTML = '<div class="muted">Keine Snapshots vorhanden</div>';
            return;
        }

        cont.innerHTML = snaps.map(s => {
            const d = new Date(s.created);
            const dateStr = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
            const timeStr = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
            const label = s.id.replace(/^\d{8}_\d{6}_?/, '') || '';
            return `
                <div class="snapshot-row">
                    <div class="snapshot-info">
                        <span class="snapshot-date">${dateStr} ${timeStr}</span>
                        ${label ? `<span class="snapshot-label">${_esc(label)}</span>` : ''}
                        <span class="snapshot-size">${(s.size_bytes / 1024).toFixed(1)} KB</span>
                    </div>
                    <div class="snapshot-actions">
                        <button class="btn-sm" onclick="Config.restoreSnapshot('${_esc(s.id)}')">Wiederherstellen</button>
                        <button class="btn-sm btn-red" onclick="Config.deleteSnapshot('${_esc(s.id)}')">Löschen</button>
                    </div>
                </div>`;
        }).join('');
    }

    async function createSnapshot() {
        const label = prompt('Optionaler Name für den Snapshot:', '');
        if (label === null) return;
        try {
            const r = await fetch(API + '/snapshot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            _loadSnapshots();
        } catch (e) {
            alert('Snapshot fehlgeschlagen: ' + e.message);
        }
    }

    async function restoreSnapshot(id) {
        if (!confirm(`Snapshot "${id}" wiederherstellen? Die aktuelle Konfiguration wird vorher gesichert.`)) return;
        try {
            const r = await fetch(API + '/restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            await load();
            _flash('config-saved-msg', 'Wiederhergestellt');
        } catch (e) {
            alert('Wiederherstellen fehlgeschlagen: ' + e.message);
        }
    }

    async function deleteSnapshot(id) {
        if (!confirm(`Snapshot "${id}" löschen?`)) return;
        try {
            const r = await fetch(API + '/snapshot/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            _loadSnapshots();
        } catch (e) {
            alert('Löschen fehlgeschlagen: ' + e.message);
        }
    }


    // =================================================================
    // Helpers
    // =================================================================

    function _flash(elId, text) {
        const el = document.getElementById(elId);
        if (!el) return;
        if (text) el.textContent = text;
        el.classList.remove('hidden');
        setTimeout(() => el.classList.add('hidden'), 2500);
    }

    function _esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }


    // =================================================================
    // Init
    // =================================================================

    function init() {
        document.getElementById('btn-config-export')?.addEventListener('click', exportConfig);
        document.getElementById('btn-config-snapshot')?.addEventListener('click', createSnapshot);

        // Import trigger
        document.getElementById('btn-config-import')?.addEventListener('click', () => {
            document.getElementById('config-import-input')?.click();
        });
        document.getElementById('config-import-input')?.addEventListener('change', (e) => {
            const f = e.target.files[0];
            if (f) importConfig(f);
            e.target.value = '';
        });

        // Color picker ↔ text sync
        const colorPicker = document.getElementById('cfg-branding-primary_color_picker');
        const colorText = document.getElementById('cfg-branding-primary_color');
        if (colorPicker && colorText) {
            colorPicker.addEventListener('input', () => { colorText.value = colorPicker.value; _debounceSave(); });
            colorText.addEventListener('input', () => {
                if (/^#[0-9a-fA-F]{6}$/.test(colorText.value)) colorPicker.value = colorText.value;
                _debounceSave();
            });
        }

        // Mode toggle
        document.getElementById('btn-mode-simple')?.addEventListener('click', () => _setMode('simple'));
        document.getElementById('btn-mode-advanced')?.addEventListener('click', () => _setMode('advanced'));

        // Auto-save on any config field change
        for (const f of FIELDS) {
            const el = document.getElementById(f.id);
            if (!el) continue;
            // Skip color fields (handled above with picker sync)
            if (f.id === 'cfg-branding-primary_color') continue;
            el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', _debounceSave);
        }

        // Start in simple mode
        _setMode('simple');

        // Password change
        document.getElementById('btn-change-pw')?.addEventListener('click', _changePassword);
    }

    async function _changePassword() {
        const cur = document.getElementById('pw-current')?.value || '';
        const nw  = document.getElementById('pw-new')?.value || '';
        const cfm = document.getElementById('pw-confirm')?.value || '';
        const msg = document.getElementById('pw-msg');

        if (!cur || !nw || !cfm) { _showPwMsg('Alle Felder ausfüllen', true); return; }
        if (nw !== cfm) { _showPwMsg('Passwörter stimmen nicht überein', true); return; }
        if (nw.length < 4) { _showPwMsg('Mindestens 4 Zeichen', true); return; }

        const btn = document.getElementById('btn-change-pw');
        btn.disabled = true;
        try {
            const r = await fetch('/api/admin/auth/password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_password: cur, new_password: nw }),
            });
            if (r.ok) {
                _showPwMsg('Passwort geändert — bitte neu anmelden', false);
                document.getElementById('pw-current').value = '';
                document.getElementById('pw-new').value = '';
                document.getElementById('pw-confirm').value = '';
            } else {
                const d = await r.json().catch(() => ({}));
                _showPwMsg(d.detail || 'Fehler beim Ändern', true);
            }
        } catch (e) {
            _showPwMsg('Verbindungsfehler', true);
        } finally {
            btn.disabled = false;
        }
    }

    function _showPwMsg(text, isError) {
        const msg = document.getElementById('pw-msg');
        if (!msg) return;
        msg.textContent = text;
        msg.classList.remove('hidden');
        msg.style.color = isError ? 'var(--color-error, #ef4444)' : 'var(--color-success, #22c55e)';
        setTimeout(() => msg.classList.add('hidden'), 4000);
    }

    document.addEventListener('DOMContentLoaded', init);

    return { load, save, exportConfig, createSnapshot, restoreSnapshot, deleteSnapshot };

})();
