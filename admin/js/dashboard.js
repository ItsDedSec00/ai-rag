// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Admin Dashboard — polls /api/admin/system every 5 s,
 * updates meters, KPIs, service status, collections, indexer log.
 */

const Dashboard = (() => {

    const POLL_MS = 5000;
    let _timer = null;

    // =================================================================
    // Theme
    // =================================================================

    function _initTheme() {
        const saved = localStorage.getItem('rag-admin-theme');
        if (saved) {
            document.documentElement.setAttribute('data-theme', saved);
        }
        // Standard: Light-Mode
        _syncThemeIcon();
    }

    function _toggleTheme() {
        const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('rag-admin-theme', next);
        _syncThemeIcon();
    }

    function _syncThemeIcon() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        document.getElementById('icon-theme-moon')?.classList.toggle('hidden', isDark);
        document.getElementById('icon-theme-sun')?.classList.toggle('hidden', !isDark);
    }

    // =================================================================
    // Sidebar (mobile)
    // =================================================================

    function _toggleSidebar() {
        const sidebar = document.getElementById('admin-sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        const isOpen = sidebar?.classList.toggle('open');
        overlay?.classList.toggle('active', isOpen);
    }

    function _closeSidebar() {
        document.getElementById('admin-sidebar')?.classList.remove('open');
        document.getElementById('sidebar-overlay')?.classList.remove('active');
    }

    // =================================================================
    // Helpers
    // =================================================================

    function _formatUptime(s) {
        const d = Math.floor(s / 86400);
        const h = Math.floor((s % 86400) / 3600);
        const m = Math.floor((s % 3600) / 60);
        if (d > 0) return `${d}d ${h}h`;
        if (h > 0) return `${h}h ${m}m`;
        return `${m} Min`;
    }

    function _esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    function _setMeter(id, pct) {
        const fill = document.getElementById(id);
        if (!fill) return;
        fill.style.width = Math.min(pct, 100) + '%';
        fill.classList.remove('warn', 'critical');
        if (pct >= 90) fill.classList.add('critical');
        else if (pct >= 70) fill.classList.add('warn');
    }

    function _dot(id, ok) {
        const el = document.getElementById(id);
        if (el) el.className = 'svc-status ' + (ok ? 'ok' : 'err');
    }

    // =================================================================
    // Poll: /api/admin/system
    // =================================================================

    async function _pollSystem() {
        try {
            const r = await fetch('/api/admin/system');
            if (!r.ok) throw new Error(r.status);
            const d = await r.json();

            // Connection
            const badge = document.getElementById('connection-status');
            badge.textContent = 'Online';
            badge.className = 'badge online';

            // Last update
            document.getElementById('last-update').textContent =
                'Aktualisiert: ' + new Date().toLocaleTimeString('de-DE');

            // KPIs
            document.getElementById('val-uptime').textContent = _formatUptime(d.container_uptime_seconds);
            document.getElementById('val-requests-total').textContent = d.requests.total.toLocaleString('de-DE');
            document.getElementById('val-requests-today').textContent = d.requests.today.toLocaleString('de-DE');
            document.getElementById('val-requests-hour').textContent = d.requests.this_hour.toLocaleString('de-DE');

            // Meters
            _setMeter('meter-cpu-fill', d.cpu.usage_pct);
            document.getElementById('meter-cpu-pct').textContent = Math.round(d.cpu.usage_pct) + '%';
            document.getElementById('meter-cpu-sub').textContent =
                d.cpu.cores + ' Kerne' + (d.cpu.frequency_mhz ? ' · ' + d.cpu.frequency_mhz + ' MHz' : '');

            _setMeter('meter-ram-fill', d.ram.usage_pct);
            document.getElementById('meter-ram-pct').textContent = Math.round(d.ram.usage_pct) + '%';
            document.getElementById('meter-ram-sub').textContent =
                d.ram.used_gb + ' / ' + d.ram.total_gb + ' GB';

            _setMeter('meter-disk-fill', d.disk.usage_pct);
            document.getElementById('meter-disk-pct').textContent = Math.round(d.disk.usage_pct) + '%';
            document.getElementById('meter-disk-sub').textContent =
                d.disk.used_gb + ' / ' + d.disk.total_gb + ' GB';

            // GPU meter
            const gpuContainer = document.getElementById('meter-gpu-container');
            if (d.gpu && d.gpu.mode !== 'cpu' && d.gpu.gpus && d.gpu.gpus.length > 0) {
                gpuContainer.classList.remove('hidden');
                const gpu = d.gpu.gpus[0];
                const pct = gpu.utilization_pct || 0;
                _setMeter('meter-gpu-fill', pct);
                document.getElementById('meter-gpu-pct').textContent = pct + '%';
                const used = gpu.vram_used_mb ? (gpu.vram_used_mb / 1024).toFixed(1) : '?';
                const total = gpu.vram_total_mb ? (gpu.vram_total_mb / 1024).toFixed(1) : '?';
                document.getElementById('meter-gpu-sub').textContent = used + ' / ' + total + ' GB VRAM';
            } else {
                // CPU mode
                _setMeter('meter-gpu-fill', 0);
                document.getElementById('meter-gpu-pct').textContent = '—';
                document.getElementById('meter-gpu-sub').textContent = 'CPU-Modus (kein GPU)';
            }

            // System table
            document.getElementById('sys-chat-model').textContent = d.models.chat;
            document.getElementById('sys-embedding-model').textContent = d.models.embedding;
            document.getElementById('sys-hostname').textContent = d.hostname || '—';
            document.getElementById('sys-platform').textContent = d.platform || '—';
            document.getElementById('sys-cpu').textContent =
                d.cpu.cores + ' Kerne' + (d.cpu.frequency_mhz ? ' @ ' + d.cpu.frequency_mhz + ' MHz' : '');

            if (d.gpu && d.gpu.gpus && d.gpu.gpus.length > 0) {
                document.getElementById('sys-gpu').textContent = d.gpu.gpus[0].name;
            } else {
                document.getElementById('sys-gpu').textContent = 'CPU-Modus (' + d.ram.total_gb + ' GB RAM)';
            }

            // System uptime (Host)
            document.getElementById('sys-uptime').textContent = _formatUptime(d.system_uptime_seconds);

        } catch (_) {
            const badge = document.getElementById('connection-status');
            badge.textContent = 'Offline';
            badge.className = 'badge offline';
        }
    }

    // =================================================================
    // Poll: /api/health (service dots)
    // =================================================================

    let _gpuBannerShown = false;

    async function _pollHealth() {
        try {
            const r = await fetch('/api/health');
            if (!r.ok) return;
            const d = await r.json();
            _dot('svc-ollama', d.services?.ollama === 'ok');
            _dot('svc-chromadb', d.services?.chromadb === 'ok');
            document.getElementById('svc-ollama-text').textContent =
                d.services?.ollama === 'ok' ? 'Verbunden' : 'Nicht erreichbar';
            document.getElementById('svc-chromadb-text').textContent =
                d.services?.chromadb === 'ok' ? 'Verbunden' : 'Nicht erreichbar';

            // GPU banner (show once, only if there's a problem)
            if (!_gpuBannerShown && d.gpu_banner) {
                _gpuBannerShown = true;
                _showGpuBanner(d.gpu_banner);
            }
        } catch (_) {
            _dot('svc-ollama', false);
            _dot('svc-chromadb', false);
        }
    }

    function _showGpuBanner(bannerData) {
        const banner = document.getElementById('gpu-banner');
        if (!banner) return;

        const isWarning = bannerData.type === 'warning';
        const icon = isWarning ? '⚠️' : 'ℹ️';
        const cls = isWarning ? 'gpu-banner warn' : 'gpu-banner cpu';
        let text = bannerData.message;
        if (bannerData.action) text += ' ' + bannerData.action;

        banner.className = cls;
        banner.innerHTML = `<span class="gpu-banner-icon">${icon}</span><span class="gpu-banner-text">${_esc(text)}</span><button class="gpu-banner-close" title="Schließen">✕</button>`;
        banner.querySelector('.gpu-banner-close').addEventListener('click', () => banner.classList.add('hidden'));
    }

    // =================================================================
    // Poll: collections
    // =================================================================

    async function _pollCollections() {
        try {
            const r = await fetch('/api/admin/collections');
            if (!r.ok) return;
            const d = await r.json();
            const list = document.getElementById('collections-list');
            const total = document.getElementById('total-chunks');

            total.textContent = (d.total_chunks || 0) + ' Chunks';

            if (!d.collections || d.collections.length === 0) {
                list.innerHTML = '<div class="muted">Keine Collections vorhanden</div>';
                return;
            }

            list.innerHTML = d.collections.map(c =>
                `<div class="collection-row">
                    <span class="collection-name">${_esc(c.name)}</span>
                    <span class="collection-chunks">${c.chunk_count}</span>
                </div>`
            ).join('');
        } catch (_) {}
    }

    // =================================================================
    // Poll: indexer
    // =================================================================

    async function _pollIndexer() {
        try {
            const r = await fetch('/api/admin/indexer/status');
            if (!r.ok) return;
            const d = await r.json();
            const badge = document.getElementById('indexer-badge');
            const detail = document.getElementById('indexer-detail');

            if (d.initial_indexing) {
                badge.textContent = (d.progress_pct || 0) + '%';
                badge.className = 'indexer-status indexing';
                detail.textContent = d.done_files + ' / ' + d.total_files + ' Dateien verarbeitet';
            } else if (d.running) {
                badge.textContent = 'Aktiv';
                badge.className = 'indexer-status active';
                detail.textContent = d.done_files + ' Dateien indexiert';
            } else {
                badge.textContent = 'Inaktiv';
                badge.className = 'indexer-status idle';
                detail.textContent = '';
            }
        } catch (_) {}
    }

    async function _pollLogs() {
        try {
            const r = await fetch('/api/admin/indexer/logs?n=30');
            if (!r.ok) return;
            const d = await r.json();
            const container = document.getElementById('indexer-log');
            const counter = document.getElementById('log-count');

            if (!d.logs || d.logs.length === 0) {
                container.innerHTML = '<div class="muted">Keine Einträge</div>';
                counter.textContent = '';
                return;
            }

            counter.textContent = d.logs.length + ' Einträge';
            container.innerHTML = d.logs.slice().reverse().map(log => {
                const time = log.timestamp ? new Date(log.timestamp).toLocaleTimeString('de-DE') : '';
                const evt = log.event || '?';
                const file = log.file ? log.file.split('/').pop() : '';
                const msg = file || log.error || '';
                return `<div class="log-entry">
                    <span class="log-time">${time}</span>
                    <span class="log-event ${evt}">${_esc(evt)}</span>
                    <span class="log-msg" title="${_esc(log.file || log.error || '')}">${_esc(msg)}</span>
                </div>`;
            }).join('');
        } catch (_) {}
    }

    // =================================================================
    // Reindex
    // =================================================================

    async function _reindex() {
        const btn = document.getElementById('btn-reindex');
        if (btn) btn.disabled = true;
        try {
            await fetch('/api/admin/indexer/reindex', { method: 'POST' });
            setTimeout(_pollIndexer, 500);
        } catch (_) {}
        finally {
            if (btn) setTimeout(() => btn.disabled = false, 3000);
        }
    }

    // =================================================================
    // Poll cycle
    // =================================================================

    async function _poll() {
        await Promise.allSettled([
            _pollSystem(),
            _pollHealth(),
            _pollCollections(),
            _pollIndexer(),
            _pollLogs(),
        ]);
    }

    // =================================================================
    // Init
    // =================================================================

    function init() {
        _initTheme();

        document.getElementById('theme-toggle')?.addEventListener('click', _toggleTheme);
        document.getElementById('sidebar-toggle')?.addEventListener('click', _toggleSidebar);
        document.getElementById('sidebar-overlay')?.addEventListener('click', _closeSidebar);
        document.getElementById('btn-reindex')?.addEventListener('click', _reindex);

        _poll();
        _timer = setInterval(_poll, POLL_MS);
    }

    return { init };

})();

document.addEventListener('DOMContentLoaded', Dashboard.init);
