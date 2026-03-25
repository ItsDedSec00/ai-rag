// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Config Manager (ADM-06): view/edit config, JSON preview,
 * export/import, snapshot management.
 */

const Config = (() => {

    const API = '/api/admin/config';
    let _cfg = null;      // current config mirror
    let _loaded = false;

    // Config field mapping: id prefix → section.key
    // LLM settings are managed in the Models tab — only RAG + Server here
    const FIELDS = [
        { id: 'cfg-rag-embedding_model',       section: 'rag',    key: 'embedding_model',type: 'text' },
        { id: 'cfg-rag-chunk_size',            section: 'rag',    key: 'chunk_size',     type: 'number' },
        { id: 'cfg-rag-chunk_overlap',         section: 'rag',    key: 'chunk_overlap',  type: 'number' },
        { id: 'cfg-rag-top_k',                 section: 'rag',    key: 'top_k',          type: 'number' },
        { id: 'cfg-server-max_upload_mb',      section: 'server', key: 'max_upload_mb',  type: 'number' },
        { id: 'cfg-server-session_timeout_min',section: 'server', key: 'session_timeout_min', type: 'number' },
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
            _renderJSON();
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
            if (val !== undefined) {
                el.value = val;
            }
        }
    }

    function _readFields() {
        // Start from current config, then overlay form values
        const out = JSON.parse(JSON.stringify(_cfg || {}));
        for (const f of FIELDS) {
            if (f.readonly) continue;
            const el = document.getElementById(f.id);
            if (!el) continue;
            if (!out[f.section]) out[f.section] = {};
            let val = el.value;
            if (f.type === 'number') val = Number(val);
            out[f.section][f.key] = val;
        }
        return out;
    }

    function _renderJSON() {
        const pre = document.getElementById('config-json-preview');
        if (pre && _cfg) {
            pre.textContent = JSON.stringify(_cfg, null, 2);
        }
    }


    // =================================================================
    // Save
    // =================================================================

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
            _populateFields();
            _renderJSON();
            _flash('config-saved-msg');
        } catch (e) {
            alert('Speichern fehlgeschlagen: ' + e.message);
        }
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
            _renderJSON();
            _loadSnapshots();
            _flash('config-saved-msg', 'Importiert');
        } catch (e) {
            alert('Import fehlgeschlagen: ' + e.message);
        }
    }


    // =================================================================
    // Copy JSON
    // =================================================================

    function copyJSON() {
        const json = JSON.stringify(_cfg || {}, null, 2);
        navigator.clipboard.writeText(json).then(() => {
            const btn = document.getElementById('btn-config-copy');
            if (btn) { btn.textContent = 'Kopiert!'; setTimeout(() => btn.textContent = 'Kopieren', 1500); }
        });
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
        if (label === null) return; // cancelled
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
            await load(); // reload everything
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
    // Init (called once on DOMContentLoaded)
    // =================================================================

    function init() {
        document.getElementById('btn-config-save')?.addEventListener('click', save);
        document.getElementById('btn-config-export')?.addEventListener('click', exportConfig);
        document.getElementById('btn-config-copy')?.addEventListener('click', copyJSON);
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
    }

    document.addEventListener('DOMContentLoaded', init);

    return { load, save, exportConfig, createSnapshot, restoreSnapshot, deleteSnapshot };

})();
