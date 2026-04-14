// RAG-Chat — © 2026 David Dülle
// https://duelle.org

const ApiKeys = (() => {
    const API = '/api/admin/api-keys';

    // ── Load & render ─────────────────────────────────────────────────────────

    async function load() {
        try {
            const res = await fetch(API);
            if (!res.ok) throw new Error(await res.text());
            const { keys } = await res.json();
            _render(keys);
        } catch (e) {
            console.error('ApiKeys.load:', e);
        }
    }

    function _render(keys) {
        const empty = document.getElementById('apikeys-empty');
        const wrap  = document.getElementById('apikeys-table-wrap');
        const tbody = document.getElementById('apikeys-tbody');
        const count = document.getElementById('apikeys-count');

        if (!keys.length) {
            empty?.classList.remove('hidden');
            wrap?.classList.add('hidden');
            if (count) count.textContent = '';
            return;
        }

        empty?.classList.add('hidden');
        wrap?.classList.remove('hidden');
        if (count) count.textContent = `${keys.length} Schlüssel`;

        tbody.innerHTML = keys.map(k => `
            <tr>
                <td><strong>${_esc(k.name)}</strong></td>
                <td><code style="font-size:0.8rem;color:var(--text-muted)">${k.id.slice(0, 8)}…</code></td>
                <td>${_fmtDate(k.created_at)}</td>
                <td>${k.last_used ? _fmtDate(k.last_used) : '<span style="color:var(--text-muted)">Noch nie</span>'}</td>
                <td style="text-align:right">
                    <button class="btn btn-danger btn-sm" onclick="ApiKeys.revoke('${k.id}', '${_esc(k.name)}')">
                        Widerrufen
                    </button>
                </td>
            </tr>
        `).join('');
    }

    // ── Create ────────────────────────────────────────────────────────────────

    function _openCreateModal() {
        const modal = _modal(`
            <div class="modal-header">
                <h3>Neuen API-Schlüssel erstellen</h3>
            </div>
            <div class="modal-body">
                <label class="form-label">Name <span style="color:var(--text-muted)">(z.&thinsp;B. "Meine App" oder "n8n")</span></label>
                <input id="new-key-name" type="text" class="form-input" placeholder="Schlüsselname…" maxlength="64" autofocus>
            </div>
            <div class="modal-footer">
                <button id="btn-confirm-create" class="btn btn-primary">Erstellen</button>
                <button id="btn-cancel-create" class="btn btn-secondary">Abbrechen</button>
            </div>
        `);

        modal.querySelector('#btn-cancel-create').addEventListener('click', () => _closeModal(modal));
        modal.querySelector('#btn-confirm-create').addEventListener('click', async () => {
            const name = modal.querySelector('#new-key-name').value.trim();
            if (!name) { modal.querySelector('#new-key-name').focus(); return; }
            _closeModal(modal);
            await _create(name);
        });
        modal.querySelector('#new-key-name').addEventListener('keydown', e => {
            if (e.key === 'Enter') modal.querySelector('#btn-confirm-create').click();
        });
    }

    async function _create(name) {
        try {
            const res = await fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
            if (!res.ok) throw new Error(await res.text());
            const { key } = await res.json();
            _showKeyModal(key, name);
            await load();
        } catch (e) {
            alert('Fehler beim Erstellen: ' + e.message);
        }
    }

    function _showKeyModal(key, name) {
        const modal = _modal(`
            <div class="modal-header">
                <h3>API-Schlüssel erstellt</h3>
            </div>
            <div class="modal-body">
                <p style="margin-bottom:0.75rem">
                    <strong>${_esc(name)}</strong> wurde erstellt.
                    Kopiere den Schlüssel jetzt — er wird <strong>nicht erneut angezeigt</strong>.
                </p>
                <div style="display:flex;gap:0.5rem;align-items:center">
                    <input id="key-display" type="text" class="form-input" value="${_esc(key)}" readonly
                        style="font-family:monospace;font-size:0.85rem;flex:1">
                    <button id="btn-copy-key" class="btn btn-secondary" style="white-space:nowrap">Kopieren</button>
                </div>
                <p style="margin-top:0.75rem;color:var(--text-muted);font-size:0.85rem">
                    Verwende diesen Schlüssel als <code>Authorization: Bearer ${_esc(key)}</code>
                    und setze <code>base_url</code> auf <code>http://&lt;server&gt;:8080/v1</code>.
                </p>
            </div>
            <div class="modal-footer">
                <button id="btn-close-key" class="btn btn-primary">Verstanden</button>
            </div>
        `);

        modal.querySelector('#btn-copy-key').addEventListener('click', () => {
            navigator.clipboard.writeText(key).then(() => {
                modal.querySelector('#btn-copy-key').textContent = 'Kopiert!';
                setTimeout(() => { modal.querySelector('#btn-copy-key').textContent = 'Kopieren'; }, 2000);
            });
        });
        modal.querySelector('#btn-close-key').addEventListener('click', () => _closeModal(modal));
        // Select all on focus for easy copy
        modal.querySelector('#key-display').addEventListener('click', e => e.target.select());
    }

    // ── Revoke ────────────────────────────────────────────────────────────────

    async function revoke(id, name) {
        if (!confirm(`API-Schlüssel „${name}" wirklich widerrufen?\nDiese Aktion kann nicht rückgängig gemacht werden.`)) return;
        try {
            const res = await fetch(`${API}/revoke`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id }),
            });
            if (!res.ok) throw new Error(await res.text());
            await load();
        } catch (e) {
            alert('Fehler beim Widerrufen: ' + e.message);
        }
    }

    // ── Modal helpers ─────────────────────────────────────────────────────────

    function _modal(html) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `<div class="modal-box">${html}</div>`;
        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add('visible'));
        overlay.addEventListener('click', e => { if (e.target === overlay) _closeModal(overlay); });
        return overlay;
    }

    function _closeModal(el) {
        el.classList.remove('visible');
        setTimeout(() => el.remove(), 200);
    }

    // ── Utils ─────────────────────────────────────────────────────────────────

    function _esc(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function _fmtDate(iso) {
        if (!iso) return '—';
        try {
            return new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
        } catch { return iso; }
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function init() {
        document.getElementById('btn-create-key')
            ?.addEventListener('click', _openCreateModal);
    }

    return { init, load, revoke };
})();

// Wire into the tab system
document.addEventListener('DOMContentLoaded', () => {
    ApiKeys.init();

    // Load when the tab is activated
    document.querySelectorAll('.nav-item[data-tab]').forEach(link => {
        link.addEventListener('click', () => {
            if (link.dataset.tab === 'apikeys') ApiKeys.load();
        });
    });
});
