// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Models page (ADM-02): hardware-aware recommendations,
 * model catalog, pull/delete, generation params, custom models.
 *
 * Pull runs in background — user can navigate to other tabs
 * and return; progress bar persists.
 */

const Models = (() => {

    let _catalog = [];
    let _installed = [];
    let _activeModel = '';

    // Background pull state (survives tab switches)
    let _pulling = false;
    let _pullModelId = '';
    let _pullAbort = null;   // AbortController

    // =================================================================
    // Tab navigation (shared between pages)
    // =================================================================

    function initTabs() {
        document.querySelectorAll('.nav-item[data-tab]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const tab = link.dataset.tab;
                if (link.classList.contains('disabled')) return;

                // Toggle active nav
                document.querySelectorAll('.nav-item[data-tab]').forEach(l => l.classList.remove('active'));
                link.classList.add('active');

                // Toggle pages
                document.querySelectorAll('.page-content').forEach(p => p.classList.add('hidden'));
                const page = document.getElementById(tab);
                if (page) page.classList.remove('hidden');

                // Update header title
                const titles = { dashboard: 'Dashboard', models: 'Modelle', files: 'Dateien', config: 'Einstellungen' };
                const h1 = document.querySelector('.header-title h1');
                if (h1) h1.textContent = titles[tab] || tab;

                // Load models data on first visit
                if (tab === 'models' && _catalog.length === 0) {
                    _loadAll();
                }
                // Load files data on first visit
                if (tab === 'files' && typeof Files !== 'undefined') {
                    Files.load();
                }
                // Load config data on first visit
                if (tab === 'config' && typeof Config !== 'undefined') {
                    Config.load();
                }
            });
        });
    }

    // =================================================================
    // Load all data
    // =================================================================

    async function _loadAll() {
        await Promise.allSettled([
            _loadRecommendations(),
            _loadInstalled(),
            _loadActiveModel(),
        ]);
        _renderCatalog();
    }

    // =================================================================
    // Recommendations
    // =================================================================

    async function _loadRecommendations() {
        try {
            const r = await fetch('/api/admin/models/recommendations');
            if (!r.ok) return;
            const data = await r.json();

            // Hardware info
            const hw = data.hardware;
            document.getElementById('rec-hw-summary').textContent = hw.summary;
            document.getElementById('rec-hw-hint').textContent = hw.hint;

            // Best recommendation
            _catalog = data.models;
            const best = data.recommendation;

            if (best) {
                const isInstalled = _installed.some(m => m.name === best.id);
                const isActive = _activeModel === best.id;

                document.getElementById('rec-best').innerHTML = `
                    <div class="rec-card">
                        <div class="rec-card-badge">⭐</div>
                        <div class="rec-card-body">
                            <div class="rec-card-name">${_esc(best.name)}</div>
                            <div class="rec-card-desc">${_esc(best.description)}</div>
                            <div class="rec-card-tags">
                                <span class="rec-tag">${_esc(best.params)}</span>
                                <span class="rec-tag">${_esc(best.size_gb + ' GB')}</span>
                                <span class="rec-tag">${_esc(best.speed)}</span>
                                <span class="rec-tag green">${_esc(best.best_for)}</span>
                            </div>
                        </div>
                        <div class="rec-card-action">
                            ${isActive
                                ? '<span class="model-active-badge">Aktiv</span>'
                                : isInstalled
                                    ? `<button class="btn-sm btn-accent" onclick="Models.activate('${_esc(best.id)}')">Aktivieren</button>`
                                    : `<button class="btn-sm btn-green" onclick="Models.pull('${_esc(best.id)}')">Installieren</button>`
                            }
                        </div>
                    </div>`;
            }
        } catch (_) {}
    }

    // =================================================================
    // Installed models
    // =================================================================

    async function _loadInstalled() {
        try {
            const r = await fetch('/api/admin/models/installed');
            if (!r.ok) return;
            const data = await r.json();
            _installed = data.models || [];
        } catch (_) {}
    }

    // =================================================================
    // Active model + params
    // =================================================================

    async function _loadActiveModel() {
        try {
            const r = await fetch('/api/admin/models/active');
            if (!r.ok) return;
            const data = await r.json();

            _activeModel = data.model;
            document.getElementById('active-model-name').textContent = data.model;

            // Sliders
            const temp = document.getElementById('param-temp');
            const topp = document.getElementById('param-topp');
            const ctx = document.getElementById('param-ctx');
            const prompt = document.getElementById('param-prompt');

            if (temp) { temp.value = data.temperature; document.getElementById('param-temp-val').textContent = data.temperature; }
            if (topp) { topp.value = data.top_p; document.getElementById('param-topp-val').textContent = data.top_p; }
            if (ctx) { ctx.value = data.context_window; document.getElementById('param-ctx-val').textContent = data.context_window; }
            if (prompt) prompt.value = data.system_prompt || '';
        } catch (_) {}
    }

    // =================================================================
    // Render catalog
    // =================================================================

    function _renderCatalog() {
        const container = document.getElementById('model-catalog');
        const installedNames = new Set(_installed.map(m => m.name));
        let installedCount = 0;

        container.innerHTML = _catalog.map(m => {
            const installed = installedNames.has(m.id);
            const active = _activeModel === m.id;
            const isCustom = !!m.custom;
            const isPulling = _pulling && _pullModelId === m.id;
            if (installed) installedCount++;

            const stars = m.stars > 0
                ? '★'.repeat(m.stars) + '☆'.repeat(5 - m.stars)
                : '—';

            let actions = '';
            if (isPulling) {
                actions = '<span class="model-meta-tag">Wird heruntergeladen…</span>';
            } else if (active) {
                actions = '<span class="model-active-badge">Aktiv</span>';
            } else if (installed) {
                actions = `
                    <button class="btn-sm btn-accent" onclick="Models.activate('${_esc(m.id)}')">Aktivieren</button>
                    <button class="btn-sm btn-red" onclick="Models.remove('${_esc(m.id)}')">Löschen</button>`;
            } else if (m.compatible) {
                actions = `<button class="btn-sm btn-green" onclick="Models.pull('${_esc(m.id)}')">Installieren</button>`;
            } else {
                actions = `<span class="model-meta-tag">Nicht kompatibel</span>`;
            }

            // Custom models get a "remove from list" button
            if (isCustom && !isPulling) {
                actions += ` <button class="btn-sm btn-icon" onclick="Models.removeCustom('${_esc(m.id)}')" title="Aus Liste entfernen">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>`;
            }

            // Installed model: show info button
            let infoBtn = '';
            if (installed) {
                infoBtn = `<button class="btn-sm btn-icon" onclick="Models.showInfo('${_esc(m.id)}')" title="Modell-Details">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                </button>`;
            }

            return `
                <div class="model-row ${m.compatible ? '' : 'incompatible'}">
                    <div class="model-tier ${m.tier}"></div>
                    <div class="model-info">
                        <div class="model-name-row">
                            <span class="model-name">${_esc(m.name)}</span>
                            ${active ? '<span class="model-active-badge">Aktiv</span>' : ''}
                            ${installed && !active ? '<span class="model-installed-badge">Installiert</span>' : ''}
                            ${isCustom ? '<span class="model-custom-badge">Manuell</span>' : ''}
                        </div>
                        <div class="model-desc">${_esc(m.description)}</div>
                        <div class="model-meta">
                            ${m.params !== '—' ? `<span class="model-meta-tag">${_esc(m.params)}</span>` : ''}
                            ${m.size_gb > 0 ? `<span class="model-meta-tag">${m.size_gb} GB</span>` : ''}
                            ${m.speed !== '—' ? `<span class="model-meta-tag">${_esc(m.speed)}</span>` : ''}
                            ${m.best_for !== '—' ? `<span class="model-meta-tag">${_esc(m.best_for)}</span>` : ''}
                        </div>
                        <div class="model-info-detail hidden" id="model-info-${CSS.escape(m.id)}"></div>
                    </div>
                    <div class="model-stars">${stars}</div>
                    <div class="model-actions">${infoBtn}${actions}</div>
                </div>`;
        }).join('');

        document.getElementById('installed-count').textContent =
            installedCount + ' von ' + _catalog.length + ' installiert';
    }

    // =================================================================
    // Pull model — background, non-blocking
    // =================================================================

    async function pull(modelId) {
        if (_pulling) {
            alert('Es wird bereits ein Modell heruntergeladen. Bitte warte bis der aktuelle Download abgeschlossen ist.');
            return;
        }

        _pulling = true;
        _pullModelId = modelId;
        _pullAbort = new AbortController();

        const bar = document.getElementById('pull-bar');
        const fill = document.getElementById('pull-bar-fill');
        const status = document.getElementById('pull-bar-status');
        const nameEl = document.getElementById('pull-bar-name');
        const cancelBtn = document.getElementById('pull-bar-cancel');

        const catalogEntry = _catalog.find(m => m.id === modelId);
        nameEl.textContent = catalogEntry ? catalogEntry.name : modelId;
        fill.style.width = '0%';
        status.textContent = 'Verbinde mit Ollama…';
        bar.classList.remove('hidden', 'done', 'error');

        // Update catalog to show "downloading" state
        _renderCatalog();

        let totalSize = 0;

        try {
            const resp = await fetch('/api/admin/models/pull', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId }),
                signal: _pullAbort.signal,
            });

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.status === 'success') {
                            fill.style.width = '100%';
                            status.textContent = 'Fertig! Modell ist bereit.';
                            bar.classList.add('done');
                        } else if (data.status === 'error') {
                            status.textContent = 'Fehler: ' + (data.error || 'Unbekannt');
                            bar.classList.add('error');
                        } else {
                            // Track total download size from first layer
                            if (data.total && data.total > totalSize) {
                                totalSize += data.total;
                            }

                            if (data.total && data.completed) {
                                const pct = Math.round((data.completed / data.total) * 100);
                                fill.style.width = pct + '%';
                                const dlMB = (data.completed / 1048576).toFixed(0);
                                const totalMB = (data.total / 1048576).toFixed(0);
                                status.textContent = `${data.status} — ${dlMB} / ${totalMB} MB (${pct}%)`;
                            } else {
                                status.textContent = data.status || 'Wird verarbeitet…';
                            }
                        }
                    } catch (_) {}
                }
            }

            // Reload catalog after pull
            await _loadInstalled();
            _renderCatalog();
            await _loadRecommendations();

            // Auto-hide bar after 5s on success
            setTimeout(() => {
                if (bar.classList.contains('done')) {
                    bar.classList.add('hidden');
                }
            }, 5000);

        } catch (e) {
            if (e.name === 'AbortError') {
                status.textContent = 'Download abgebrochen';
                bar.classList.add('error');
            } else {
                status.textContent = 'Fehler: ' + e.message;
                bar.classList.add('error');
            }
        } finally {
            _pulling = false;
            _pullModelId = '';
            _pullAbort = null;
            cancelBtn.textContent = 'Schließen';
            _renderCatalog();
        }
    }

    function cancelPull() {
        if (_pullAbort) {
            _pullAbort.abort();
        }
        document.getElementById('pull-bar')?.classList.add('hidden');
    }

    // =================================================================
    // Model info (from Ollama /api/show)
    // =================================================================

    async function showInfo(modelId) {
        const detailId = 'model-info-' + CSS.escape(modelId);
        const el = document.getElementById(detailId);
        if (!el) return;

        // Toggle visibility
        if (!el.classList.contains('hidden')) {
            el.classList.add('hidden');
            return;
        }

        el.innerHTML = '<span class="muted" style="padding:0;font-size:0.75rem">Lädt…</span>';
        el.classList.remove('hidden');

        try {
            const r = await fetch('/api/admin/models/show?model=' + encodeURIComponent(modelId));
            if (!r.ok) {
                el.innerHTML = '<span class="muted" style="padding:0;font-size:0.75rem">Details nicht verfügbar</span>';
                return;
            }
            const data = await r.json();

            const tags = [];
            if (data.family) tags.push(`Familie: ${_esc(data.family)}`);
            if (data.parameter_size) tags.push(`Parameter: ${_esc(data.parameter_size)}`);
            if (data.quantization) tags.push(`Quantisierung: ${_esc(data.quantization)}`);
            if (data.format) tags.push(`Format: ${_esc(data.format)}`);
            if (data.context_length) tags.push(`Kontextfenster: ${data.context_length.toLocaleString()}`);
            if (data.layers) tags.push(`Schichten: ${data.layers}`);

            if (tags.length === 0) {
                el.innerHTML = '<span class="muted" style="padding:0;font-size:0.75rem">Keine Details verfügbar</span>';
                return;
            }

            el.innerHTML = `<div class="model-detail-tags">${tags.map(t =>
                `<span class="model-detail-tag">${t}</span>`
            ).join('')}</div>`;

        } catch (e) {
            el.innerHTML = '<span class="muted" style="padding:0;font-size:0.75rem">Fehler beim Laden</span>';
        }
    }

    // =================================================================
    // Activate model
    // =================================================================

    async function activate(modelId) {
        try {
            const r = await fetch('/api/admin/models/active', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId }),
            });
            if (r.ok) {
                _activeModel = modelId;
                document.getElementById('active-model-name').textContent = modelId;
                _renderCatalog();
                await _loadRecommendations();
            }
        } catch (_) {}
    }

    // =================================================================
    // Delete model
    // =================================================================

    async function remove(modelId) {
        if (!confirm(`Modell "${modelId}" wirklich löschen?`)) return;
        try {
            const r = await fetch('/api/admin/models/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId }),
            });
            if (r.ok) {
                _installed = _installed.filter(m => m.name !== modelId);
                _renderCatalog();
            }
        } catch (_) {}
    }

    // =================================================================
    // Save params
    // =================================================================

    async function _saveParams() {
        const body = {
            temperature: parseFloat(document.getElementById('param-temp').value),
            top_p: parseFloat(document.getElementById('param-topp').value),
            context_window: parseInt(document.getElementById('param-ctx').value),
            system_prompt: document.getElementById('param-prompt').value,
        };

        try {
            const r = await fetch('/api/admin/models/params', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (r.ok) {
                const msg = document.getElementById('params-saved-msg');
                msg.classList.remove('hidden');
                setTimeout(() => msg.classList.add('hidden'), 2000);
            }
        } catch (_) {}
    }

    // =================================================================
    // Custom models
    // =================================================================

    async function addCustom() {
        const input = document.getElementById('custom-model-input');
        const modelId = input.value.trim();

        if (!modelId) {
            _showCustomMsg('Bitte eine Modell-ID eingeben', true);
            return;
        }

        try {
            const r = await fetch('/api/admin/models/custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId }),
            });
            const data = await r.json();

            if (!r.ok) {
                _showCustomMsg(data.detail || 'Fehler', true);
                return;
            }

            input.value = '';
            _showCustomMsg(`"${modelId}" wurde hinzugefügt`, false);

            // Reload catalog
            await _loadRecommendations();
            await _loadInstalled();
            _renderCatalog();

        } catch (e) {
            _showCustomMsg('Fehler: ' + e.message, true);
        }
    }

    async function removeCustom(modelId) {
        if (!confirm(`"${modelId}" aus der Liste entfernen?`)) return;

        try {
            const r = await fetch('/api/admin/models/custom/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId }),
            });
            if (r.ok) {
                _catalog = _catalog.filter(m => m.id !== modelId);
                _renderCatalog();
            }
        } catch (_) {}
    }

    function _showCustomMsg(text, isError) {
        const msg = document.getElementById('custom-model-msg');
        msg.textContent = text;
        msg.className = 'custom-model-msg' + (isError ? ' error' : ' success');
        msg.classList.remove('hidden');
        setTimeout(() => msg.classList.add('hidden'), 3000);
    }

    // =================================================================
    // Helpers
    // =================================================================

    function _esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    // =================================================================
    // Init
    // =================================================================

    function init() {
        initTabs();

        // Slider live values
        document.getElementById('param-temp')?.addEventListener('input', (e) => {
            document.getElementById('param-temp-val').textContent = parseFloat(e.target.value).toFixed(2);
        });
        document.getElementById('param-topp')?.addEventListener('input', (e) => {
            document.getElementById('param-topp-val').textContent = parseFloat(e.target.value).toFixed(2);
        });
        document.getElementById('param-ctx')?.addEventListener('input', (e) => {
            document.getElementById('param-ctx-val').textContent = e.target.value;
        });

        document.getElementById('btn-save-params')?.addEventListener('click', _saveParams);

        // Custom model input
        document.getElementById('btn-add-custom')?.addEventListener('click', addCustom);
        document.getElementById('custom-model-input')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') addCustom();
        });

        // Pull bar cancel
        document.getElementById('pull-bar-cancel')?.addEventListener('click', cancelPull);
    }

    return { init, pull, activate, remove, removeCustom, showInfo, cancelPull };

})();

document.addEventListener('DOMContentLoaded', Models.init);
