// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Updates page (ADM-04): version status, GitHub check,
 * update/rollback trigger, update log.
 */

const Updates = (() => {

    let _loaded = false;
    let _updateAvailable = false;

    // =================================================================
    // Init (called from tab switch in models.js initTabs)
    // =================================================================

    function init() {
        // Hook into tab navigation (initTabs runs from models.js)
        document.querySelectorAll('.nav-item[data-tab]').forEach(link => {
            link.addEventListener('click', () => {
                if (link.dataset.tab === 'updates' && !_loaded) {
                    _loaded = true;
                    _loadStatus();
                    _loadLog();
                }
            });
        });

        // Update header title for updates tab
        const origInitTabs = typeof Models !== 'undefined' ? Models : null;
        // Title is set by models.js initTabs — we just need to add "Updates"

        // Buttons
        document.getElementById('btn-check-updates')?.addEventListener('click', () => {
            _loaded = false;
            _loadStatus();
        });

        document.getElementById('btn-do-update')?.addEventListener('click', _triggerUpdate);
        document.getElementById('btn-rollback')?.addEventListener('click', _triggerRollback);
    }

    // =================================================================
    // Load version + GitHub status
    // =================================================================

    async function _loadStatus() {
        const localEl = document.getElementById('update-local-version');
        const remoteEl = document.getElementById('update-remote-version');
        const statusBar = document.getElementById('update-status-bar');
        const panel = document.getElementById('update-available-panel');

        if (localEl) localEl.textContent = '…';
        if (remoteEl) remoteEl.textContent = '…';

        try {
            const r = await fetch('/api/admin/updates/status');
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = await r.json();

            const local = data.local_version || 'dev';
            const github = data.github || {};
            const remote = github.latest || '—';

            if (localEl) localEl.textContent = local;
            if (remoteEl) remoteEl.textContent = remote || '—';

            _updateAvailable = data.update_available;

            // Status bar
            if (statusBar) {
                if (!data.github_repo) {
                    _showStatusBar('info', 'Kein GitHub-Repository konfiguriert (GITHUB_REPO in .env setzen)');
                } else if (github.status === 'error') {
                    _showStatusBar('warn', 'GitHub nicht erreichbar: ' + (github.error || 'Unbekannter Fehler'));
                } else if (github.status === 'no_releases') {
                    _showStatusBar('info', 'Noch kein Release auf GitHub veröffentlicht');
                } else if (data.update_available) {
                    _showStatusBar('update', `Update verfügbar: ${local} → ${remote}`);
                } else if (github.status === 'ok') {
                    _showStatusBar('ok', 'System ist auf dem neuesten Stand');
                }
            }

            // Update nav badge
            const badge = document.getElementById('update-nav-badge');
            if (badge) {
                if (_updateAvailable) {
                    badge.textContent = '1';
                    badge.classList.remove('hidden');
                } else {
                    badge.classList.add('hidden');
                }
            }

            // Update available panel
            if (panel) {
                if (data.update_available) {
                    panel.classList.remove('hidden');
                    const titleEl = document.getElementById('update-action-title');
                    if (titleEl) titleEl.textContent = `${local} → ${remote}`;

                    const link = document.getElementById('update-changelog-link');
                    if (link && github.url) link.href = github.url;

                    // Changelog
                    if (github.changelog) {
                        const cl = document.getElementById('update-changelog');
                        if (cl) {
                            cl.textContent = github.changelog;
                            cl.classList.remove('hidden');
                        }
                    }
                } else {
                    panel.classList.add('hidden');
                }
            }

        } catch (e) {
            if (statusBar) _showStatusBar('warn', 'Fehler beim Laden: ' + e.message);
        }
    }

    function _showStatusBar(type, msg) {
        const bar = document.getElementById('update-status-bar');
        if (!bar) return;
        bar.className = 'update-status-bar update-status-' + type;
        bar.textContent = msg;
        bar.classList.remove('hidden');
    }

    // =================================================================
    // Update log
    // =================================================================

    async function _loadLog() {
        const list = document.getElementById('update-log-list');
        if (!list) return;

        try {
            const r = await fetch('/api/admin/updates/log?n=20');
            if (!r.ok) return;
            const data = await r.json();
            const entries = data.log || [];

            if (entries.length === 0) {
                list.innerHTML = '<div class="muted" style="padding:16px">Kein Update-Verlauf vorhanden</div>';
                return;
            }

            list.innerHTML = entries.map(e => {
                const statusClass = {
                    success: 'log-success',
                    failed: 'log-error',
                    unhealthy: 'log-error',
                    rollback: 'log-warn',
                }[e.status] || 'log-info';

                const statusLabel = {
                    success: 'Erfolg',
                    failed: 'Fehler',
                    unhealthy: 'Health-Check fehlgeschlagen',
                    rollback: 'Rollback',
                }[e.status] || e.status;

                const ts = e.timestamp ? new Date(e.timestamp).toLocaleString('de-DE') : '—';
                const arrow = (e.from && e.to && e.from !== e.to)
                    ? `${_esc(e.from)} → ${_esc(e.to)}`
                    : _esc(e.from || e.to || '—');

                return `
                <div class="update-log-row">
                    <span class="update-log-status ${statusClass}">${statusLabel}</span>
                    <span class="update-log-version">${arrow}</span>
                    <span class="update-log-ts">${ts}</span>
                    ${e.message ? `<span class="update-log-msg">${_esc(e.message)}</span>` : ''}
                </div>`;
            }).join('');

        } catch (_) {}
    }

    // =================================================================
    // Trigger update / rollback
    // =================================================================

    async function _triggerUpdate() {
        if (!confirm('Update jetzt installieren? Der Server startet anschließend automatisch neu (ca. 1–3 Minuten).')) return;
        await _sendTrigger('/api/admin/updates/trigger', 'Update angefordert');
    }

    async function _triggerRollback() {
        if (!confirm('Wirklich auf die vorherige Version zurücksetzen? Der Server startet anschließend neu.')) return;
        await _sendTrigger('/api/admin/updates/rollback', 'Rollback angefordert');
    }

    async function _sendTrigger(url, successMsg) {
        try {
            const r = await fetch(url, { method: 'POST' });
            const data = await r.json();
            if (r.ok) {
                _showStatusBar('ok', successMsg + ' — wird im Hintergrund ausgeführt');
                // Reload log after short delay
                setTimeout(_loadLog, 3000);
            } else {
                _showStatusBar('warn', 'Fehler: ' + (data.detail || 'Unbekannt'));
            }
        } catch (e) {
            _showStatusBar('warn', 'Fehler: ' + e.message);
        }
    }

    // =================================================================
    // Helpers
    // =================================================================

    function _esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    return { init };

})();

document.addEventListener('DOMContentLoaded', Updates.init);
