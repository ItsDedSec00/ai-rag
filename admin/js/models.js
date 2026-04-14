// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Models page (ADM-02 v2): family-based model selection,
 * hardware-aware size recommendation, thinking mode toggle,
 * pull/delete, generation params, custom models.
 */

const Models = (() => {

    let _families = [];
    let _installed = [];
    let _activeModel = '';
    let _thinkingMode = false;
    let _customModels = [];
    let _hardware = {};

    // Background pull state (survives tab switches)
    let _pulling = false;
    let _pullModelId = '';
    let _pullAbort = null;

    // =================================================================
    // Tab navigation (shared between pages)
    // =================================================================

    function initTabs() {
        document.querySelectorAll('.nav-item[data-tab]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const tab = link.dataset.tab;
                if (link.classList.contains('disabled')) return;

                document.querySelectorAll('.nav-item[data-tab]').forEach(l => l.classList.remove('active'));
                link.classList.add('active');

                document.querySelectorAll('.page-content').forEach(p => p.classList.add('hidden'));
                const page = document.getElementById(tab);
                if (page) page.classList.remove('hidden');

                const titles = { dashboard: 'Dashboard', models: 'Modelle', files: 'Dateien', config: 'Einstellungen', performance: 'Performance', updates: 'Updates', extensions: 'Erweiterungen' };
                const h1 = document.querySelector('.header-title h1');
                if (h1) h1.textContent = titles[tab] || tab;

                if (tab === 'models' && _families.length === 0) {
                    _loadAll();
                }
                if (tab === 'files' && typeof Files !== 'undefined') {
                    Files.load();
                }
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
        _renderFamilies();
    }

    // =================================================================
    // Recommendations (family-based)
    // =================================================================

    async function _loadRecommendations() {
        try {
            const r = await fetch('/api/admin/models/recommendations');
            if (!r.ok) return;
            const data = await r.json();

            _hardware = data.hardware || {};
            _families = data.families || [];
            _customModels = data.custom_models || [];

            // Hardware info
            const hw = data.hardware;
            document.getElementById('rec-hw-summary').textContent = hw.summary;
            document.getElementById('rec-hw-hint').textContent = hw.hint;
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
            _thinkingMode = data.thinking_mode || false;
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

            const mt = document.getElementById('param-maxtokens');
            const rp = document.getElementById('param-repeat');
            const lang = document.getElementById('param-lang');
            if (mt && data.max_tokens) { mt.value = data.max_tokens; document.getElementById('param-maxtokens-val').textContent = data.max_tokens; }
            if (rp && data.repeat_penalty) { rp.value = data.repeat_penalty; document.getElementById('param-repeat-val').textContent = data.repeat_penalty; }
            if (lang && data.response_language) lang.value = data.response_language;
            const ka = document.getElementById('param-keepalive');
            if (ka && data.keep_alive != null) ka.value = data.keep_alive;

            // Thinking mode toggle
            const toggle = document.getElementById('thinking-toggle');
            if (toggle) toggle.checked = _thinkingMode;
            _updateThinkingVisibility();
        } catch (_) {}
    }

    // =================================================================
    // Render family cards
    // =================================================================

    function _renderFamilies() {
        const container = document.getElementById('model-families');
        const installedNames = new Set(_installed.map(m => m.name));

        let html = '';

        for (const fam of _families) {
            const recIdx = fam.recommended_idx;

            html += `
            <section class="panel family-card" data-family="${_esc(fam.key)}">
                <div class="family-header">
                    <div class="family-title-row">
                        <h2 class="family-name">${_esc(fam.name)}</h2>
                        <span class="family-vendor">${_esc(fam.vendor)}</span>
                        ${fam.supports_thinking ? '<span class="family-badge thinking-badge">Thinking</span>' : ''}
                    </div>
                    <div class="family-desc">${_esc(fam.description)}</div>
                </div>
                <div class="family-sizes">
                    ${fam.sizes.map((sz, i) => {
                        const installed = installedNames.has(sz.id);
                        const active = _activeModel === sz.id;
                        const isPulling = _pulling && _pullModelId === sz.id;
                        const isRecommended = i === recIdx;

                        let statusClass = '';
                        let statusLabel = '';
                        if (active) {
                            statusClass = 'active';
                            statusLabel = 'Aktiv';
                        } else if (installed) {
                            statusClass = 'installed';
                            statusLabel = 'Installiert';
                        } else if (isPulling) {
                            statusClass = 'pulling';
                            statusLabel = 'Lädt…';
                        } else if (!sz.compatible) {
                            statusClass = 'incompatible';
                            statusLabel = 'Zu groß';
                        }

                        let action = '';
                        if (isPulling) {
                            action = '<span class="size-status-text">Wird heruntergeladen…</span>';
                        } else if (active) {
                            action = `<span class="size-active-badge">Aktiv</span>
                                      <button class="btn-sm btn-red" onclick="Models.remove('${_esc(sz.id)}')">Löschen</button>`;
                        } else if (installed) {
                            action = `<button class="btn-sm btn-accent" onclick="Models.activate('${_esc(sz.id)}')">Aktivieren</button>
                                      <button class="btn-sm btn-red" onclick="Models.remove('${_esc(sz.id)}')">Löschen</button>`;
                        } else if (sz.compatible) {
                            action = `<button class="btn-sm btn-green" onclick="Models.pull('${_esc(sz.id)}')">Installieren</button>`;
                        } else {
                            action = '<span class="size-status-text incompatible-text">Nicht kompatibel</span>';
                        }

                        return `
                        <div class="size-row ${statusClass}">
                            <div class="size-info">
                                <span class="size-label">${_esc(sz.label)}</span>
                                ${isRecommended ? '<span class="size-rec-badge">Empfohlen</span>' : ''}
                                <span class="size-meta">${sz.size_gb} GB</span>
                            </div>
                            <div class="size-actions">${action}</div>
                        </div>`;
                    }).join('')}
                </div>
            </section>`;
        }

        // Custom models section (if any installed that aren't in families)
        if (_customModels.length > 0) {
            html += `
            <section class="panel family-card custom-family">
                <div class="family-header">
                    <div class="family-title-row">
                        <h2 class="family-name">Eigene Modelle</h2>
                        <span class="family-vendor">Manuell</span>
                    </div>
                    <div class="family-desc">Manuell hinzugefügte Ollama-Modelle.</div>
                </div>
                <div class="family-sizes">
                    ${_customModels.map(id => {
                        const installed = installedNames.has(id);
                        const active = _activeModel === id;
                        const isPulling = _pulling && _pullModelId === id;

                        let action = '';
                        if (isPulling) {
                            action = '<span class="size-status-text">Wird heruntergeladen…</span>';
                        } else if (active) {
                            action = '<span class="size-active-badge">Aktiv</span>';
                        } else if (installed) {
                            action = `<button class="btn-sm btn-accent" onclick="Models.activate('${_esc(id)}')">Aktivieren</button>
                                      <button class="btn-sm btn-red" onclick="Models.remove('${_esc(id)}')">Löschen</button>`;
                        } else {
                            action = `<button class="btn-sm btn-green" onclick="Models.pull('${_esc(id)}')">Installieren</button>`;
                        }
                        action += ` <button class="btn-sm btn-icon" onclick="Models.removeCustom('${_esc(id)}')" title="Aus Liste entfernen">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>`;

                        return `
                        <div class="size-row ${active ? 'active' : installed ? 'installed' : ''}">
                            <div class="size-info">
                                <span class="size-label">${_esc(id)}</span>
                            </div>
                            <div class="size-actions">${action}</div>
                        </div>`;
                    }).join('')}
                </div>
            </section>`;
        }

        container.innerHTML = html;
        _updateThinkingVisibility();
    }

    // =================================================================
    // Thinking mode
    // =================================================================

    function _updateThinkingVisibility() {
        const section = document.getElementById('thinking-section');
        if (!section) return;

        // Show thinking toggle only if active model belongs to a family that supports it
        const activeFam = _families.find(f =>
            f.sizes.some(s => s.id === _activeModel)
        );
        if (activeFam && activeFam.supports_thinking) {
            section.style.display = '';
        } else {
            section.style.display = 'none';
        }
    }

    async function _toggleThinking() {
        const toggle = document.getElementById('thinking-toggle');
        if (!toggle) return;
        _thinkingMode = toggle.checked;

        try {
            await fetch('/api/admin/models/params', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ thinking_mode: _thinkingMode }),
            });
            const msg = document.getElementById('params-saved-msg');
            msg.classList.remove('hidden');
            setTimeout(() => msg.classList.add('hidden'), 2000);
        } catch (_) {}
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

        nameEl.textContent = modelId;
        fill.style.width = '0%';
        status.textContent = 'Verbinde mit Ollama…';
        bar.classList.remove('hidden', 'done', 'error');
        cancelBtn.textContent = 'Abbrechen';

        _renderFamilies();

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

            await _loadInstalled();
            _renderFamilies();

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
            _renderFamilies();
        }
    }

    function cancelPull() {
        if (_pullAbort) {
            _pullAbort.abort();
        }
        document.getElementById('pull-bar')?.classList.add('hidden');
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
                _renderFamilies();
                _updateThinkingVisibility();
            }
        } catch (_) {}
    }

    // =================================================================
    // Delete model
    // =================================================================

    async function remove(modelId) {
        const isActive = _activeModel === modelId;
        const otherInstalled = _installed.filter(m => m.name !== modelId);

        if (isActive && otherInstalled.length === 0) {
            alert(`"${modelId}" ist das einzige installierte Modell und kann nicht gelöscht werden.\n\nInstalliere zuerst ein anderes Modell und aktiviere es.`);
            return;
        }

        const activeWarning = isActive
            ? `\n\nACHTUNG: Dieses Modell ist gerade aktiv. Nach dem Löschen wird kein Modell mehr gesetzt.`
            : '';
        if (!confirm(`Modell "${modelId}" wirklich löschen?${activeWarning}`)) return;

        try {
            const r = await fetch('/api/admin/models/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId }),
            });
            if (r.ok) {
                _installed = _installed.filter(m => m.name !== modelId);
                if (isActive) _activeModel = otherInstalled[0]?.name || '';
                // If it's a custom model, also remove it from the custom list
                if (_customModels.includes(modelId)) {
                    await fetch('/api/admin/models/custom/remove', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ model: modelId }),
                    });
                    _customModels = _customModels.filter(id => id !== modelId);
                }
                _renderFamilies();
            } else {
                const err = await r.json().catch(() => ({}));
                alert(`Fehler beim Löschen: ${err.detail || r.status}`);
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
            max_tokens: parseInt(document.getElementById('param-maxtokens')?.value || '2048'),
            repeat_penalty: parseFloat(document.getElementById('param-repeat')?.value || '1.1'),
            response_language: document.getElementById('param-lang')?.value || 'auto',
            keep_alive: document.getElementById('param-keepalive')?.value || '5m',
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

            await _loadRecommendations();
            await _loadInstalled();
            _renderFamilies();

        } catch (e) {
            _showCustomMsg('Fehler: ' + e.message, true);
        }
    }

    async function removeCustom(modelId) {
        const isInstalled = _installed.some(m => m.name === modelId);
        const msg = isInstalled
            ? `"${modelId}" aus der Liste entfernen und aus Ollama löschen?`
            : `"${modelId}" aus der Liste entfernen?`;
        if (!confirm(msg)) return;

        try {
            // Remove from custom list
            const r = await fetch('/api/admin/models/custom/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId }),
            });
            if (!r.ok) return;
            _customModels = _customModels.filter(id => id !== modelId);

            // Also delete from Ollama if installed
            if (isInstalled) {
                await fetch('/api/admin/models/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model: modelId }),
                });
                _installed = _installed.filter(m => m.name !== modelId);
            }

            _renderFamilies();
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

    let _saveTimer = null;

    function _debounceSave() {
        clearTimeout(_saveTimer);
        _saveTimer = setTimeout(_saveParams, 400);
    }

    function init() {
        initTabs();

        // Slider live values + auto-save
        document.getElementById('param-temp')?.addEventListener('input', (e) => {
            document.getElementById('param-temp-val').textContent = parseFloat(e.target.value).toFixed(2);
            _debounceSave();
        });
        document.getElementById('param-topp')?.addEventListener('input', (e) => {
            document.getElementById('param-topp-val').textContent = parseFloat(e.target.value).toFixed(2);
            _debounceSave();
        });
        document.getElementById('param-ctx')?.addEventListener('input', (e) => {
            document.getElementById('param-ctx-val').textContent = e.target.value;
            _debounceSave();
        });
        document.getElementById('param-maxtokens')?.addEventListener('input', (e) => {
            document.getElementById('param-maxtokens-val').textContent = e.target.value;
            _debounceSave();
        });
        document.getElementById('param-repeat')?.addEventListener('input', (e) => {
            document.getElementById('param-repeat-val').textContent = parseFloat(e.target.value).toFixed(2);
            _debounceSave();
        });

        // Select + textarea auto-save
        document.getElementById('param-lang')?.addEventListener('change', _debounceSave);
        document.getElementById('param-keepalive')?.addEventListener('change', _debounceSave);
        document.getElementById('param-prompt')?.addEventListener('input', _debounceSave);

        // Thinking mode toggle
        document.getElementById('thinking-toggle')?.addEventListener('change', _toggleThinking);

        // Reset system prompt to default
        document.getElementById('btn-reset-prompt')?.addEventListener('click', async () => {
            try {
                const r = await fetch('/api/admin/models/default-prompt');
                const data = await r.json();
                const ta = document.getElementById('param-prompt');
                if (ta && data.system_prompt) {
                    ta.value = data.system_prompt;
                    _saveParams();
                }
            } catch (_) {}
        });

        // Custom model input
        document.getElementById('btn-add-custom')?.addEventListener('click', addCustom);
        document.getElementById('custom-model-input')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') addCustom();
        });

        // Pull bar cancel
        document.getElementById('pull-bar-cancel')?.addEventListener('click', cancelPull);
    }

    return { init, pull, activate, remove, removeCustom, cancelPull };

})();

document.addEventListener('DOMContentLoaded', Models.init);
