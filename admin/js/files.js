// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * File Manager (ADM-03): browse, upload (drag & drop + ZIP),
 * create/rename/delete folders, move/delete files.
 * Real-time index status polling, duplicate conflict resolution.
 */

const Files = (() => {

    let _currentPath = '';
    let _loaded = false;
    let _moveTarget = null;
    let _pollTimer = null;      // real-time stats/file-list polling
    let _pollCount = 0;         // counts down after upload

    // Extension → icon/color mapping
    const EXT_ICONS = {
        pdf: { icon: 'PDF', color: 'var(--red)' },
        docx: { icon: 'DOC', color: 'var(--accent)' },
        txt: { icon: 'TXT', color: 'var(--text-muted)' },
        md: { icon: 'MD', color: 'var(--green)' },
        csv: { icon: 'CSV', color: 'var(--amber)' },
    };

    const STATUS_LABELS = {
        indexed: { text: 'Indexiert', cls: 'status-ok' },
        error: { text: 'Fehler', cls: 'status-err' },
        pending: { text: 'Ausstehend', cls: 'status-pending' },
        unknown: { text: 'Ausstehend', cls: 'status-pending' },
    };

    // =================================================================
    // Load
    // =================================================================

    function load() {
        if (!_loaded) {
            _initEvents();
            _loaded = true;
        }
        _loadStats();
        _navigate(_currentPath);
    }

    // =================================================================
    // Events
    // =================================================================

    function _initEvents() {
        // Upload button
        document.getElementById('btn-upload-file')?.addEventListener('click', () => {
            document.getElementById('file-upload-input')?.click();
        });

        // File input change
        document.getElementById('file-upload-input')?.addEventListener('change', (e) => {
            if (e.target.files.length) {
                _startUpload(Array.from(e.target.files));
                e.target.value = '';
            }
        });

        // New folder button
        document.getElementById('btn-new-folder')?.addEventListener('click', _showFolderDialog);
        document.getElementById('btn-folder-cancel')?.addEventListener('click', _hideFolderDialog);
        document.getElementById('btn-folder-create')?.addEventListener('click', _createFolder);
        document.getElementById('folder-name-input')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') _createFolder();
            if (e.key === 'Escape') _hideFolderDialog();
        });

        // Rename dialog
        document.getElementById('btn-rename-cancel')?.addEventListener('click', _hideRenameDialog);
        document.getElementById('btn-rename-confirm')?.addEventListener('click', _confirmRename);
        document.getElementById('rename-input')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') _confirmRename();
            if (e.key === 'Escape') _hideRenameDialog();
        });

        // Move dialog
        document.getElementById('btn-move-cancel')?.addEventListener('click', _hideMoveDialog);
        document.getElementById('btn-move-confirm')?.addEventListener('click', _confirmMove);

        // Conflict dialog
        document.getElementById('btn-conflict-skip')?.addEventListener('click', () => _resolveConflict('skip'));
        document.getElementById('btn-conflict-rename')?.addEventListener('click', () => _resolveConflict('rename'));
        document.getElementById('btn-conflict-overwrite')?.addEventListener('click', () => _resolveConflict('overwrite'));

        // Drag & drop
        const dropzone = document.getElementById('files-dropzone');
        const filesPanel = dropzone?.closest('.panel');

        if (filesPanel) {
            filesPanel.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('dragover');
            });

            filesPanel.addEventListener('dragleave', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (!filesPanel.contains(e.relatedTarget)) {
                    dropzone.classList.remove('dragover');
                }
            });

            filesPanel.addEventListener('drop', (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');

                const files = [];
                if (e.dataTransfer.items) {
                    for (const item of e.dataTransfer.items) {
                        if (item.kind === 'file') {
                            const file = item.getAsFile();
                            if (file) files.push(file);
                        }
                    }
                } else if (e.dataTransfer.files) {
                    files.push(...e.dataTransfer.files);
                }

                if (files.length) _startUpload(files);
            });
        }
    }

    // =================================================================
    // Navigation
    // =================================================================

    async function _navigate(path) {
        _currentPath = path;
        _renderBreadcrumb();

        const list = document.getElementById('files-list');
        list.innerHTML = '<div class="muted">Lädt…</div>';

        try {
            const r = await fetch('/api/admin/files?path=' + encodeURIComponent(path));
            if (!r.ok) throw new Error('Fehler beim Laden');
            const data = await r.json();
            _renderFileList(data);
        } catch (e) {
            list.innerHTML = `<div class="muted">Fehler: ${_esc(e.message)}</div>`;
        }
    }

    function _renderBreadcrumb() {
        const bc = document.getElementById('files-breadcrumb');
        const parts = _currentPath ? _currentPath.split('/').filter(Boolean) : [];

        let html = '<a href="#" class="breadcrumb-item" data-path="">Wissensbasis</a>';
        let cumulative = '';

        for (const part of parts) {
            cumulative += (cumulative ? '/' : '') + part;
            html += `<span class="breadcrumb-sep">/</span>`;
            html += `<a href="#" class="breadcrumb-item" data-path="${_esc(cumulative)}">${_esc(part)}</a>`;
        }

        bc.innerHTML = html;

        bc.querySelectorAll('.breadcrumb-item').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                _navigate(link.dataset.path);
            });
        });
    }

    // =================================================================
    // Render file list
    // =================================================================

    function _renderFileList(data) {
        const list = document.getElementById('files-list');

        if (data.folders.length === 0 && data.files.length === 0) {
            list.innerHTML = `
                <div class="files-empty">
                    <div class="files-empty-icon">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <p>Keine Dateien vorhanden</p>
                    <p class="files-empty-hint">Lade Dateien hoch oder erstelle einen Ordner</p>
                </div>`;
            return;
        }

        let html = '';

        // Parent folder link
        if (_currentPath) {
            const parentParts = _currentPath.split('/').filter(Boolean);
            parentParts.pop();
            const parentPath = parentParts.join('/');
            html += `
                <div class="file-row file-row-parent" data-navigate="${_esc(parentPath)}">
                    <div class="file-icon folder-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
                    </div>
                    <div class="file-info">
                        <span class="file-name">..</span>
                    </div>
                </div>`;
        }

        // Folders
        for (const f of data.folders) {
            html += `
                <div class="file-row file-row-folder" data-navigate="${_esc(f.path)}">
                    <div class="file-icon folder-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <div class="file-info">
                        <span class="file-name">${_esc(f.name)}</span>
                        <span class="file-meta">${f.file_count} Datei${f.file_count !== 1 ? 'en' : ''}</span>
                    </div>
                    <div class="file-actions">
                        <button class="btn-sm btn-red btn-icon" onclick="event.stopPropagation(); Files.deleteFolder('${_esc(f.path)}')" title="Ordner löschen">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                    </div>
                </div>`;
        }

        // Files
        for (const f of data.files) {
            const extInfo = EXT_ICONS[f.extension] || { icon: f.extension.toUpperCase(), color: 'var(--text-muted)' };
            const status = STATUS_LABELS[f.index_status] || STATUS_LABELS.unknown;

            html += `
                <div class="file-row">
                    <div class="file-icon file-ext-icon" style="background: ${extInfo.color}15; color: ${extInfo.color}">
                        ${extInfo.icon}
                    </div>
                    <div class="file-info">
                        <span class="file-name">${_esc(f.name)}</span>
                        <span class="file-meta">
                            ${_esc(f.size_display)}
                            ${f.chunks ? ' · ' + f.chunks + ' Chunks' : ''}
                        </span>
                    </div>
                    <div class="file-status ${status.cls}" title="${f.error ? _esc(f.error) : ''}">${status.text}</div>
                    <div class="file-actions">
                        <button class="btn-sm btn-icon" onclick="Files.showRename('${_esc(f.path)}', '${_esc(f.name)}')" title="Umbenennen">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                        </button>
                        <button class="btn-sm btn-icon" onclick="Files.showMove('${_esc(f.path)}')" title="Verschieben">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>
                        </button>
                        <button class="btn-sm btn-red btn-icon" onclick="Files.deleteFile('${_esc(f.path)}')" title="Löschen">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                    </div>
                </div>`;
        }

        list.innerHTML = html;

        // Folder navigation clicks
        list.querySelectorAll('[data-navigate]').forEach(row => {
            row.addEventListener('click', () => _navigate(row.dataset.navigate));
        });
    }

    // =================================================================
    // Upload with duplicate detection
    // =================================================================

    // Conflict resolution state
    let _conflictResolve = null;   // Promise resolve callback
    let _conflictRemember = false; // "remember" checkbox state

    async function _startUpload(files) {
        // Check for duplicates first (only non-ZIP files)
        const nonZipFiles = files.filter(f => !f.name.toLowerCase().endsWith('.zip'));
        const nonZipNames = nonZipFiles.map(f => f.name);
        let defaultAction = null; // remembered action for this transfer

        let conflicts = [];
        if (nonZipNames.length > 0) {
            try {
                const r = await fetch('/api/admin/files/check-duplicates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folder: _currentPath, filenames: nonZipNames }),
                });
                if (r.ok) {
                    const data = await r.json();
                    conflicts = data.conflicts || [];
                }
            } catch (_) {}
        }

        // If there are conflicts and no remembered action, ask once
        let onConflict = 'rename';
        if (conflicts.length > 0) {
            const result = await _showConflictDialog(conflicts);
            if (result === null) return; // cancelled
            onConflict = result;
        }

        _doUpload(files, onConflict);
    }

    async function _doUpload(files, onConflict) {
        const overlay = document.getElementById('upload-overlay');
        const fill = document.getElementById('upload-fill');
        const status = document.getElementById('upload-status');
        const title = document.getElementById('upload-title');

        title.textContent = files.length === 1
            ? `"${files[0].name}" wird hochgeladen…`
            : `${files.length} Dateien werden hochgeladen…`;
        fill.style.width = '0%';
        status.textContent = 'Starte Upload…';
        overlay.classList.remove('hidden');

        let done = 0;
        let totalUploaded = 0;
        let skippedDupes = 0;
        let errors = [];

        for (const file of files) {
            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('folder', _currentPath);
                formData.append('on_conflict', onConflict);

                status.textContent = `${file.name} (${done + 1}/${files.length})`;

                const r = await fetch('/api/admin/files/upload', {
                    method: 'POST',
                    body: formData,
                });

                const result = await r.json();
                if (r.ok && result.status === 'ok') {
                    totalUploaded += result.total || 0;
                    skippedDupes += result.skipped_duplicates || 0;
                } else {
                    errors.push(`${file.name}: ${result.detail || 'Fehler'}`);
                }
            } catch (e) {
                errors.push(`${file.name}: ${e.message}`);
            }

            done++;
            fill.style.width = Math.round((done / files.length) * 100) + '%';
        }

        // Summary
        let summary = '';
        if (totalUploaded > 0) {
            summary = totalUploaded === 1
                ? '1 Datei hochgeladen'
                : `${totalUploaded} Dateien hochgeladen`;
        }
        if (skippedDupes > 0) {
            summary += (summary ? ', ' : '') + `${skippedDupes} Duplikat${skippedDupes > 1 ? 'e' : ''} übersprungen`;
        }
        if (errors.length) {
            summary += (summary ? ', ' : '') + `${errors.length} Fehler`;
            status.title = errors.join('\n');
        }
        status.textContent = summary || 'Fertig';
        fill.style.width = '100%';

        // Start real-time polling for index status updates
        _startPoll();

        setTimeout(() => {
            overlay.classList.add('hidden');
            _navigate(_currentPath);
            _loadStats();
        }, 1200);
    }

    // =================================================================
    // Conflict dialog
    // =================================================================

    function _showConflictDialog(conflicts) {
        return new Promise((resolve) => {
            _conflictResolve = resolve;

            const dialog = document.getElementById('conflict-dialog');
            const list = document.getElementById('conflict-file-list');
            const remember = document.getElementById('conflict-remember');
            if (remember) remember.checked = false;

            let html = '';
            for (const c of conflicts) {
                html += `<div class="conflict-file">
                    <span class="conflict-file-name">${_esc(c.name)}</span>
                    <span class="conflict-file-size">${_esc(c.existing_size_display)}</span>
                </div>`;
            }
            list.innerHTML = html;

            const countEl = document.getElementById('conflict-count');
            if (countEl) {
                countEl.textContent = conflicts.length === 1
                    ? '1 Datei existiert bereits:'
                    : `${conflicts.length} Dateien existieren bereits:`;
            }

            dialog.classList.remove('hidden');
        });
    }

    function _resolveConflict(action) {
        document.getElementById('conflict-dialog').classList.add('hidden');
        if (_conflictResolve) {
            _conflictResolve(action);
            _conflictResolve = null;
        }
    }

    function _cancelConflict() {
        document.getElementById('conflict-dialog').classList.add('hidden');
        if (_conflictResolve) {
            _conflictResolve(null);
            _conflictResolve = null;
        }
    }

    // =================================================================
    // Real-time polling after upload
    // =================================================================

    function _startPoll() {
        _stopPoll();
        _pollCount = 20; // poll for ~40 seconds (20 × 2s)
        _pollTimer = setInterval(async () => {
            _pollCount--;
            if (_pollCount <= 0) {
                _stopPoll();
                return;
            }

            // Refresh stats + file list in background
            await Promise.allSettled([
                _loadStats(),
                _refreshFileList(),
            ]);
        }, 2000);
    }

    function _stopPoll() {
        if (_pollTimer) {
            clearInterval(_pollTimer);
            _pollTimer = null;
        }
    }

    async function _refreshFileList() {
        try {
            const r = await fetch('/api/admin/files?path=' + encodeURIComponent(_currentPath));
            if (!r.ok) return;
            const data = await r.json();
            _renderFileList(data);

            // Stop early if all files are indexed
            const hasPending = data.files.some(f =>
                f.index_status === 'pending' || f.index_status === 'unknown'
            );
            if (!hasPending && _pollCount < 15) {
                _stopPoll();
            }
        } catch (_) {}
    }

    // =================================================================
    // Folder dialog
    // =================================================================

    function _showFolderDialog() {
        const dialog = document.getElementById('folder-dialog');
        const input = document.getElementById('folder-name-input');
        dialog.classList.remove('hidden');
        input.value = '';
        input.focus();
    }

    function _hideFolderDialog() {
        document.getElementById('folder-dialog').classList.add('hidden');
    }

    async function _createFolder() {
        const input = document.getElementById('folder-name-input');
        const name = input.value.trim();
        if (!name) return;

        const path = _currentPath ? _currentPath + '/' + name : name;

        try {
            const r = await fetch('/api/admin/files/folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path }),
            });
            if (!r.ok) {
                const err = await r.json().catch(() => ({}));
                alert(err.detail || 'Fehler beim Erstellen');
                return;
            }
            _hideFolderDialog();
            _navigate(_currentPath);
        } catch (e) {
            alert('Fehler: ' + e.message);
        }
    }

    // =================================================================
    // Delete operations
    // =================================================================

    async function deleteFile(path) {
        const name = path.split('/').pop();
        if (!confirm(`Datei "${name}" wirklich löschen?`)) return;

        try {
            const r = await fetch('/api/admin/files/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path }),
            });
            if (r.ok) {
                _navigate(_currentPath);
                _loadStats();
            } else {
                const err = await r.json().catch(() => ({}));
                alert(err.detail || 'Fehler beim Löschen');
            }
        } catch (e) {
            alert('Fehler: ' + e.message);
        }
    }

    async function deleteFolder(path) {
        const name = path.split('/').pop();
        if (!confirm(`Ordner "${name}" und alle Inhalte wirklich löschen?`)) return;

        try {
            const r = await fetch('/api/admin/files/delete-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path }),
            });
            if (r.ok) {
                _navigate(_currentPath);
                _loadStats();
            } else {
                const err = await r.json().catch(() => ({}));
                alert(err.detail || 'Fehler beim Löschen');
            }
        } catch (e) {
            alert('Fehler: ' + e.message);
        }
    }

    // =================================================================
    // Move dialog
    // =================================================================

    async function showMove(filePath) {
        _moveTarget = filePath;

        const dialog = document.getElementById('move-dialog');
        const list = document.getElementById('move-folder-list');

        dialog.classList.remove('hidden');
        list.innerHTML = '<div class="muted">Lädt Ordner…</div>';

        try {
            const r = await fetch('/api/admin/files?path=');
            if (!r.ok) throw new Error('Fehler');
            const data = await r.json();

            let html = `
                <div class="move-folder-item ${_currentPath === '' ? 'active' : ''}" data-move-path="">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    Wissensbasis (Stammverzeichnis)
                </div>`;

            for (const f of data.folders) {
                const isCurrentFolder = f.path === _currentPath;
                html += `
                    <div class="move-folder-item ${isCurrentFolder ? 'active' : ''}" data-move-path="${_esc(f.path)}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                        ${_esc(f.name)}
                    </div>`;
            }

            list.innerHTML = html;

            list.querySelectorAll('.move-folder-item').forEach(item => {
                item.addEventListener('click', () => {
                    list.querySelectorAll('.move-folder-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                });
            });

        } catch (e) {
            list.innerHTML = `<div class="muted">Fehler: ${_esc(e.message)}</div>`;
        }
    }

    function _hideMoveDialog() {
        document.getElementById('move-dialog').classList.add('hidden');
        _moveTarget = null;
    }

    async function _confirmMove() {
        if (!_moveTarget) return;

        const selected = document.querySelector('#move-folder-list .move-folder-item.selected');
        if (!selected) {
            alert('Bitte wähle einen Zielordner aus');
            return;
        }

        const targetFolder = selected.dataset.movePath;

        try {
            const r = await fetch('/api/admin/files/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: _moveTarget, target_folder: targetFolder }),
            });
            if (r.ok) {
                _hideMoveDialog();
                _navigate(_currentPath);
                _loadStats();
            } else {
                const err = await r.json().catch(() => ({}));
                alert(err.detail || 'Fehler beim Verschieben');
            }
        } catch (e) {
            alert('Fehler: ' + e.message);
        }
    }

    // =================================================================
    // Rename dialog
    // =================================================================

    let _renameTarget = null;

    function showRename(filePath, currentName) {
        _renameTarget = filePath;

        const dialog = document.getElementById('rename-dialog');
        const input = document.getElementById('rename-input');
        const hint = document.getElementById('rename-hint');

        // Pre-fill with name (without extension)
        const ext = currentName.includes('.') ? currentName.substring(currentName.lastIndexOf('.')) : '';
        const stem = ext ? currentName.substring(0, currentName.lastIndexOf('.')) : currentName;

        input.value = stem;
        hint.textContent = ext ? `Dateiendung "${ext}" wird automatisch beibehalten.` : '';

        dialog.classList.remove('hidden');
        input.focus();
        input.select();
    }

    function _hideRenameDialog() {
        document.getElementById('rename-dialog').classList.add('hidden');
        _renameTarget = null;
    }

    async function _confirmRename() {
        if (!_renameTarget) return;

        const input = document.getElementById('rename-input');
        const newName = input.value.trim();
        if (!newName) return;

        try {
            const r = await fetch('/api/admin/files/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: _renameTarget, new_name: newName }),
            });
            if (r.ok) {
                _hideRenameDialog();
                _navigate(_currentPath);
            } else {
                const err = await r.json().catch(() => ({}));
                alert(err.detail || 'Fehler beim Umbenennen');
            }
        } catch (e) {
            alert('Fehler: ' + e.message);
        }
    }

    // =================================================================
    // Stats
    // =================================================================

    async function _loadStats() {
        try {
            const r = await fetch('/api/admin/files/stats');
            if (!r.ok) return;
            const data = await r.json();

            document.getElementById('files-total').textContent = data.total_files;
            document.getElementById('files-indexed').textContent = data.indexed;
            document.getElementById('files-pending').textContent = data.pending + data.errors;
            document.getElementById('files-size').textContent = data.total_size_display;
        } catch (_) {}
    }

    // =================================================================
    // Helpers
    // =================================================================

    function _esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    return { load, deleteFile, deleteFolder, showMove, showRename, cancelConflict: _cancelConflict };

})();
