// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Upload module: file upload with progress bar, drag & drop, session management
 */

const Upload = (() => {

    let _sessionId = null;
    let _filename = null;

    function getSessionId() { return _sessionId; }

    // --- Progress bar helpers ---

    function _showProgress(show) {
        const el = document.getElementById('upload-progress');
        if (el) el.classList.toggle('hidden', !show);
    }

    function _setProgress(pct) {
        const fill = document.getElementById('upload-progress-fill');
        if (!fill) return;
        fill.classList.remove('processing');
        fill.style.width = pct + '%';
    }

    function _setProcessing() {
        const fill = document.getElementById('upload-progress-fill');
        if (!fill) return;
        fill.classList.add('processing');
        fill.style.width = '100%';
    }

    // --- Upload a file to the backend ---

    function uploadFile(file) {
        const bar = document.getElementById('upload-bar');
        const barInfo = document.getElementById('upload-bar-info');

        // Validate extension
        const ext = file.name.split('.').pop().toLowerCase();
        const allowed = ['pdf', 'docx', 'txt', 'md', 'csv'];
        if (!allowed.includes(ext)) {
            alert(`Dateityp .${ext} wird nicht unterstützt.\nErlaubt: ${allowed.join(', ')}`);
            return;
        }

        // Validate size (10 MB)
        if (file.size > 10 * 1024 * 1024) {
            alert('Datei ist zu groß (max. 10 MB).');
            return;
        }

        // Show upload bar + progress
        bar.classList.remove('hidden');
        barInfo.textContent = `📎 ${file.name} — Upload…`;
        _showProgress(true);
        _setProgress(0);

        const formData = new FormData();
        formData.append('file', file);

        const xhr = new XMLHttpRequest();

        // --- Upload progress (file → server) ---
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                _setProgress(pct);
                barInfo.textContent = `📎 ${file.name} — Upload ${pct}%`;
            }
        });

        // Upload done → server is now processing (parsing + embedding)
        xhr.upload.addEventListener('load', () => {
            barInfo.textContent = `📎 ${file.name} — Verarbeitung…`;
            _setProcessing();
        });

        // --- Server response ---
        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const data = JSON.parse(xhr.responseText);
                    _sessionId = data.session_id;
                    _filename = data.filename;
                    barInfo.textContent = `📎 ${data.filename} (${data.chunks} Chunks, ${data.ttl_minutes} Min)`;
                    _showProgress(false);
                } catch (e) {
                    _onUploadError('Unerwartete Antwort');
                }
            } else {
                let msg = `Upload fehlgeschlagen (${xhr.status})`;
                try {
                    const err = JSON.parse(xhr.responseText);
                    if (err.detail) msg = err.detail;
                } catch (_) {}
                _onUploadError(msg);
            }
        });

        xhr.addEventListener('error', () => _onUploadError('Netzwerkfehler'));
        xhr.addEventListener('abort', () => _onUploadError('Abgebrochen'));

        xhr.open('POST', '/api/upload');
        xhr.send(formData);
    }

    function _onUploadError(msg) {
        const barInfo = document.getElementById('upload-bar-info');
        if (barInfo) barInfo.textContent = `❌ ${msg}`;
        _showProgress(false);
        setTimeout(() => clearSession(), 3000);
    }

    function clearSession() {
        _sessionId = null;
        _filename = null;
        const bar = document.getElementById('upload-bar');
        if (bar) bar.classList.add('hidden');
        _showProgress(false);
    }

    // --- Drag & Drop ---

    function initDragDrop() {
        const overlay = document.getElementById('drop-overlay');
        let dragCounter = 0;

        document.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragCounter++;
            if (overlay) overlay.classList.remove('hidden');
        });

        document.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dragCounter--;
            if (dragCounter <= 0) {
                dragCounter = 0;
                if (overlay) overlay.classList.add('hidden');
            }
        });

        document.addEventListener('dragover', (e) => e.preventDefault());

        document.addEventListener('drop', (e) => {
            e.preventDefault();
            dragCounter = 0;
            if (overlay) overlay.classList.add('hidden');

            const file = e.dataTransfer?.files?.[0];
            if (file) uploadFile(file);
        });
    }

    // --- Init ---

    function init() {
        initDragDrop();

        const fileInput = document.getElementById('file-input');
        fileInput?.addEventListener('change', () => {
            if (fileInput.files[0]) {
                uploadFile(fileInput.files[0]);
                fileInput.value = '';
            }
        });

        document.getElementById('upload-bar-remove')?.addEventListener('click', clearSession);
    }

    return { init, uploadFile, getSessionId, clearSession };

})();

document.addEventListener('DOMContentLoaded', Upload.init);
