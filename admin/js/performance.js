// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Performance Monitor (ADM-05)
 * Primary KPIs + charts + GPU live + recent requests table.
 */

const Performance = (() => {

    let _loaded = false;
    let _chartReq = null;
    let _chartTps = null;
    let _gpuTimer = null;

    // =========================================================
    // Init
    // =========================================================

    function init() {
        document.querySelectorAll('.nav-item[data-tab]').forEach(link => {
            link.addEventListener('click', () => {
                if (link.dataset.tab === 'performance') {
                    if (!_loaded) {
                        _loaded = true;
                        _initCharts();
                    }
                    _load();
                    _startGpuPoll();
                } else {
                    _stopGpuPoll();
                }
            });
        });

        document.getElementById('btn-perf-refresh')?.addEventListener('click', _load);
    }

    // =========================================================
    // Load all data
    // =========================================================

    async function _load() {
        await Promise.all([_loadSummary(), _loadHistory(), _loadRecent()]);
    }

    // =========================================================
    // Primary KPIs
    // =========================================================

    async function _loadSummary() {
        try {
            const r = await fetch('/api/admin/performance/summary');
            if (!r.ok) return;
            const d = await r.json();

            _set('perf-today',       d.total_today ?? '—');
            _set('perf-last-hour',   d.last_hour   ?? '—');
            _set('perf-first-token', d.avg_first_token_ms != null ? d.avg_first_token_ms + ' ms' : '—');
            _set('perf-tps',         d.avg_tps != null ? d.avg_tps : '—');
        } catch (_) {}
    }

    // =========================================================
    // Charts (hourly history)
    // =========================================================

    function _initCharts() {
        const isDark = () => document.documentElement.getAttribute('data-theme') === 'dark';

        const gridColor  = () => isDark() ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)';
        const labelColor = () => isDark() ? '#a0a0b0' : '#6b7280';
        const accent     = getComputedStyle(document.documentElement)
                               .getPropertyValue('--accent').trim() || '#6366f1';

        const baseOpts = (yLabel) => ({
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    grid: { color: gridColor() },
                    ticks: { color: labelColor(), maxTicksLimit: 8,
                             maxRotation: 0, font: { size: 11 } },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: gridColor() },
                    ticks: { color: labelColor(), font: { size: 11 } },
                    title: { display: true, text: yLabel,
                             color: labelColor(), font: { size: 11 } },
                },
            },
        });

        const ctxReq = document.getElementById('chart-requests')?.getContext('2d');
        if (ctxReq) {
            _chartReq = new Chart(ctxReq, {
                type: 'bar',
                data: { labels: [], datasets: [{ label: 'Anfragen', data: [],
                    backgroundColor: accent + 'aa', borderColor: accent,
                    borderWidth: 1, borderRadius: 3 }] },
                options: baseOpts('Anfragen'),
            });
        }

        const ctxTps = document.getElementById('chart-tps')?.getContext('2d');
        if (ctxTps) {
            _chartTps = new Chart(ctxTps, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'Token/s', data: [],
                    borderColor: accent, backgroundColor: accent + '22',
                    borderWidth: 2, pointRadius: 3, fill: true, tension: 0.3 }] },
                options: baseOpts('Token / s'),
            });
        }
    }

    async function _loadHistory() {
        try {
            const r = await fetch('/api/admin/performance/history?hours=24');
            if (!r.ok) return;
            const { history } = await r.json();

            const labels = history.map(h => {
                const d = new Date(h.hour);
                return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
            });

            if (_chartReq) {
                _chartReq.data.labels = labels;
                _chartReq.data.datasets[0].data = history.map(h => h.requests);
                _chartReq.update();
            }
            if (_chartTps) {
                _chartTps.data.labels = labels;
                _chartTps.data.datasets[0].data = history.map(h => h.avg_tps ?? 0);
                _chartTps.update();
            }
        } catch (_) {}
    }

    // =========================================================
    // Recent requests table
    // =========================================================

    async function _loadRecent() {
        const tbody = document.getElementById('perf-recent-tbody');
        if (!tbody) return;
        try {
            const r = await fetch('/api/admin/performance/recent?n=20');
            if (!r.ok) return;
            const { requests } = await r.json();

            if (!requests.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="muted" style="padding:16px;text-align:center">Noch keine Anfragen aufgezeichnet</td></tr>';
                return;
            }

            tbody.innerHTML = requests.map(req => {
                const ts = req.timestamp
                    ? new Date(req.timestamp).toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    : '—';
                const model = _esc(req.model || '—');
                const ftms  = req.first_token_ms  != null ? req.first_token_ms  + ' ms' : '—';
                const tps   = req.tokens_per_second != null ? req.tokens_per_second : '—';
                const dur   = req.duration_ms != null ? Math.round(req.duration_ms / 1000) + ' s' : '—';
                const src   = req.source_count ?? 0;

                return `<tr>
                    <td class="perf-td-mono">${ts}</td>
                    <td><span class="perf-model-chip">${model}</span></td>
                    <td class="perf-td-num">${ftms}</td>
                    <td class="perf-td-num">${tps}</td>
                    <td class="perf-td-num">${dur}</td>
                    <td class="perf-td-num">${src}</td>
                </tr>`;
            }).join('');
        } catch (_) {}
    }

    // =========================================================
    // GPU live poll
    // =========================================================

    function _startGpuPoll() {
        _pollGpu();
        if (!_gpuTimer) _gpuTimer = setInterval(_pollGpu, 10000);
    }

    function _stopGpuPoll() {
        if (_gpuTimer) { clearInterval(_gpuTimer); _gpuTimer = null; }
    }

    async function _pollGpu() {
        try {
            const r = await fetch('/api/admin/gpu');
            if (!r.ok) return;
            const gpu = await r.json();

            const panel = document.getElementById('perf-gpu-panel');
            if (!gpu.gpus || !gpu.gpus.length) {
                if (panel) panel.classList.add('hidden');
                return;
            }
            if (panel) panel.classList.remove('hidden');

            const g = gpu.gpus[0];
            _set('perf-gpu-name',  g.name  || '—');
            _set('perf-gpu-temp',  g.temperature_c != null ? g.temperature_c + ' °C' : '—');
            _set('perf-gpu-util',  g.utilization_pct != null ? g.utilization_pct + ' %' : '—');

            if (g.vram_used_mb != null && g.vram_total_mb != null) {
                _set('perf-gpu-vram', `${g.vram_used_mb} / ${g.vram_total_mb} MB`);
            } else {
                _set('perf-gpu-vram', '—');
            }
        } catch (_) {}
    }

    // =========================================================
    // Helpers
    // =========================================================

    function _set(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function _esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    return { init };

})();

document.addEventListener('DOMContentLoaded', Performance.init);
