# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
File manager for the RAG knowledge base (ADM-03).
- List files and folders with indexing status
- Create / rename / delete folders
- Upload files (including ZIP with auto-extract)
- Move / delete files
- Path traversal protection
"""

import logging
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.parser import SUPPORTED_EXTENSIONS
from rag.indexer import indexer

logger = logging.getLogger(__name__)

KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", "/data/knowledge")


# ---------------------------------------------------------------------------
# Path validation (security)
# ---------------------------------------------------------------------------

def _safe_path(relative: str) -> Path:
    """
    Resolve a relative path within KNOWLEDGE_PATH.
    Raises ValueError on traversal attempts.
    """
    base = Path(KNOWLEDGE_PATH).resolve()
    target = (base / relative).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Ungültiger Pfad: Zugriff außerhalb der Wissensbasis")
    return target


def _relative(absolute: Path) -> str:
    """Return relative path string from KNOWLEDGE_PATH."""
    return str(absolute.relative_to(Path(KNOWLEDGE_PATH).resolve()))


# ---------------------------------------------------------------------------
# List files & folders
# ---------------------------------------------------------------------------

def list_files(folder: str = "") -> dict[str, Any]:
    """
    List contents of a folder within the knowledge base.
    Returns folders and files with metadata + indexing status.
    """
    target = _safe_path(folder)

    if not target.exists():
        return {"path": folder, "folders": [], "files": [], "exists": False}

    folders = []
    files = []

    for entry in sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
        if entry.name.startswith("."):
            continue

        if entry.is_dir():
            # Count files in subdirectory
            file_count = sum(
                1 for f in entry.rglob("*")
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            )
            folders.append({
                "name": entry.name,
                "path": _relative(entry),
                "file_count": file_count,
            })

        elif entry.is_file():
            ext = entry.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            stat = entry.stat()
            abs_path = str(entry.resolve())

            # Get indexing status from indexer state
            idx_record = indexer._state.get(abs_path)
            idx_status = "unknown"
            idx_chunks = 0
            idx_error = None
            if idx_record:
                idx_status = idx_record.status
                idx_chunks = idx_record.chunks
                idx_error = idx_record.error

            files.append({
                "name": entry.name,
                "path": _relative(entry),
                "size_bytes": stat.st_size,
                "size_display": _format_size(stat.st_size),
                "extension": ext.lstrip("."),
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "index_status": idx_status,
                "chunks": idx_chunks,
                "error": idx_error,
            })

    return {
        "path": folder or "",
        "folders": folders,
        "files": files,
        "exists": True,
    }


# ---------------------------------------------------------------------------
# Folder operations
# ---------------------------------------------------------------------------

def create_folder(folder_path: str) -> dict[str, Any]:
    """Create a new folder."""
    target = _safe_path(folder_path)

    if target.exists():
        return {"status": "error", "detail": "Ordner existiert bereits"}

    target.mkdir(parents=True, exist_ok=True)
    logger.info("Created folder: %s", folder_path)
    return {"status": "ok", "path": folder_path}


def rename_folder(old_path: str, new_name: str) -> dict[str, Any]:
    """Rename a folder (new_name is just the folder name, not a path)."""
    source = _safe_path(old_path)
    if not source.exists() or not source.is_dir():
        return {"status": "error", "detail": "Ordner nicht gefunden"}

    # Validate new name
    new_name = new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        return {"status": "error", "detail": "Ungültiger Ordnername"}

    target = source.parent / new_name
    if target.exists():
        return {"status": "error", "detail": "Zielname existiert bereits"}

    source.rename(target)
    logger.info("Renamed folder: %s → %s", old_path, new_name)
    return {"status": "ok", "old_path": old_path, "new_path": _relative(target)}


def delete_folder(folder_path: str) -> dict[str, Any]:
    """Delete a folder and all its contents."""
    target = _safe_path(folder_path)

    if not target.exists() or not target.is_dir():
        return {"status": "error", "detail": "Ordner nicht gefunden"}

    # Don't allow deleting the root knowledge path
    if target.resolve() == Path(KNOWLEDGE_PATH).resolve():
        return {"status": "error", "detail": "Stammverzeichnis kann nicht gelöscht werden"}

    # Count files to be deleted
    file_count = sum(1 for f in target.rglob("*") if f.is_file())

    shutil.rmtree(target)
    logger.info("Deleted folder: %s (%d files)", folder_path, file_count)
    return {"status": "ok", "path": folder_path, "files_deleted": file_count}


# ---------------------------------------------------------------------------
# File upload (with ZIP support)
# ---------------------------------------------------------------------------

def check_duplicates(folder: str, filenames: list[str]) -> dict[str, Any]:
    """
    Check which filenames already exist in the target folder.
    Returns list of conflicts for the frontend to resolve.
    """
    target_dir = _safe_path(folder) if folder else Path(KNOWLEDGE_PATH).resolve()
    conflicts = []
    for name in filenames:
        candidate = target_dir / name
        if candidate.exists() and candidate.is_file():
            stat = candidate.stat()
            conflicts.append({
                "name": name,
                "existing_size": stat.st_size,
                "existing_size_display": _format_size(stat.st_size),
            })
    return {"conflicts": conflicts}


def save_upload(
    folder: str,
    filename: str,
    content: bytes,
    on_conflict: str = "rename",
) -> dict[str, Any]:
    """
    Save an uploaded file. If it's a ZIP, extract supported files.
    on_conflict: "rename" (default), "overwrite", "skip"
    Returns info about saved/extracted files.
    """
    target_dir = _safe_path(folder) if folder else Path(KNOWLEDGE_PATH).resolve()

    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower()

    if ext == ".zip":
        return _extract_zip(target_dir, filename, content, on_conflict)

    # Single file upload
    if ext not in SUPPORTED_EXTENSIONS:
        return {
            "status": "error",
            "detail": f"Dateityp '{ext}' wird nicht unterstützt. "
                      f"Erlaubt: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        }

    file_path = target_dir / filename

    # Handle duplicates
    if file_path.exists():
        if on_conflict == "skip":
            return {
                "status": "ok",
                "files": [],
                "total": 0,
                "skipped_duplicates": 1,
            }
        elif on_conflict == "overwrite":
            pass  # just write over it
        else:  # rename
            file_path = _unique_path(file_path)

    file_path.write_bytes(content)
    logger.info("Uploaded file: %s (%s)", _relative(file_path), _format_size(len(content)))

    return {
        "status": "ok",
        "files": [{
            "name": file_path.name,
            "path": _relative(file_path),
            "size_bytes": len(content),
        }],
        "total": 1,
    }


def _extract_zip(
    target_dir: Path,
    zip_name: str,
    content: bytes,
    on_conflict: str = "rename",
) -> dict[str, Any]:
    """Extract a ZIP archive, keeping only supported file types."""
    import io

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return {"status": "error", "detail": "Ungültige ZIP-Datei"}

    extracted = []
    skipped = 0
    skipped_duplicates = 0

    for info in zf.infolist():
        # Skip directories and hidden files
        if info.is_dir():
            continue
        if any(part.startswith(".") or part.startswith("__") for part in Path(info.filename).parts):
            skipped += 1
            continue

        ext = Path(info.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            skipped += 1
            continue

        # Security: validate no path traversal
        clean_name = Path(info.filename).name
        if not clean_name:
            skipped += 1
            continue

        # Preserve subfolder structure from ZIP
        zip_path = Path(info.filename)
        if len(zip_path.parts) > 1:
            sub_dir = target_dir / Path(*zip_path.parts[:-1])
            sub_dir.mkdir(parents=True, exist_ok=True)
            out_path = sub_dir / clean_name
        else:
            out_path = target_dir / clean_name

        # Handle duplicates
        if out_path.exists():
            if on_conflict == "skip":
                skipped_duplicates += 1
                continue
            elif on_conflict == "overwrite":
                pass  # just write over it
            else:  # rename
                out_path = _unique_path(out_path)

        data = zf.read(info)
        out_path.write_bytes(data)

        extracted.append({
            "name": out_path.name,
            "path": _relative(out_path),
            "size_bytes": len(data),
        })

    logger.info("Extracted ZIP '%s': %d files, %d skipped, %d duplicate-skipped",
                zip_name, len(extracted), skipped, skipped_duplicates)

    return {
        "status": "ok",
        "files": extracted,
        "total": len(extracted),
        "skipped": skipped,
        "skipped_duplicates": skipped_duplicates,
        "zip_name": zip_name,
    }


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

def rename_file(file_path: str, new_name: str) -> dict[str, Any]:
    """Rename a file (new_name is just the filename, not a path)."""
    source = _safe_path(file_path)
    if not source.exists() or not source.is_file():
        return {"status": "error", "detail": "Datei nicht gefunden"}

    # Validate new name
    new_name = new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        return {"status": "error", "detail": "Ungültiger Dateiname"}

    # Keep original extension if user omitted it
    old_ext = source.suffix.lower()
    new_ext = Path(new_name).suffix.lower()
    if not new_ext and old_ext:
        new_name = new_name + source.suffix

    # Check supported extension
    final_ext = Path(new_name).suffix.lower()
    if final_ext not in SUPPORTED_EXTENSIONS:
        return {
            "status": "error",
            "detail": f"Dateityp '{final_ext}' wird nicht unterstützt. "
                      f"Erlaubt: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        }

    target = source.parent / new_name
    if target.exists():
        return {"status": "error", "detail": "Eine Datei mit diesem Namen existiert bereits"}

    source.rename(target)
    logger.info("Renamed file: %s → %s", file_path, new_name)
    return {
        "status": "ok",
        "old_path": file_path,
        "new_path": _relative(target),
        "new_name": target.name,
    }


def delete_file(file_path: str) -> dict[str, Any]:
    """Delete a single file."""
    target = _safe_path(file_path)

    if not target.exists() or not target.is_file():
        return {"status": "error", "detail": "Datei nicht gefunden"}

    target.unlink()
    logger.info("Deleted file: %s", file_path)
    return {"status": "ok", "path": file_path}


def move_file(file_path: str, target_folder: str) -> dict[str, Any]:
    """Move a file to a different folder."""
    source = _safe_path(file_path)
    if not source.exists() or not source.is_file():
        return {"status": "error", "detail": "Datei nicht gefunden"}

    dest_dir = _safe_path(target_folder)
    if not dest_dir.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)

    dest_file = _unique_path(dest_dir / source.name)
    shutil.move(str(source), str(dest_file))
    logger.info("Moved file: %s → %s", file_path, _relative(dest_file))

    return {
        "status": "ok",
        "old_path": file_path,
        "new_path": _relative(dest_file),
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict[str, Any]:
    """Overall knowledge base statistics."""
    base = Path(KNOWLEDGE_PATH)
    if not base.exists():
        return {
            "total_files": 0,
            "total_folders": 0,
            "total_size_bytes": 0,
            "total_size_display": "0 B",
            "by_extension": {},
            "indexed": 0,
            "pending": 0,
            "errors": 0,
        }

    total_files = 0
    total_size = 0
    by_ext: dict[str, int] = {}
    indexed = 0
    pending = 0
    errors = 0
    folder_set: set[str] = set()

    for f in base.rglob("*"):
        if f.is_dir():
            folder_set.add(str(f))
            continue
        if f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        total_files += 1
        total_size += f.stat().st_size
        by_ext[ext] = by_ext.get(ext, 0) + 1

        # Indexing status
        rec = indexer._state.get(str(f.resolve()))
        if rec:
            if rec.status == "indexed":
                indexed += 1
            elif rec.status == "error":
                errors += 1
            else:
                pending += 1
        else:
            pending += 1

    return {
        "total_files": total_files,
        "total_folders": len(folder_set),
        "total_size_bytes": total_size,
        "total_size_display": _format_size(total_size),
        "by_extension": by_ext,
        "indexed": indexed,
        "pending": pending,
        "errors": errors,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024**2):.1f} MB"
    else:
        return f"{size_bytes / (1024**3):.1f} GB"


def _unique_path(path: Path) -> Path:
    """If path exists, append (1), (2), etc."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1
