"""
RAG Indexer Service
-------------------
- Monitors /data/knowledge via watchdog (recursive)
- On startup: initial scan + inkrementelle Indexierung (hash-basiert)
- On file create/modify: parse → chunk → embed → upsert to ChromaDB
- On file delete: remove chunks from ChromaDB
- Persistent state in /data/config/indexer_state.json
- Append-only JSON-lines log in /data/logs/indexer.log
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from rag.parser import parse_file, SUPPORTED_EXTENSIONS
from rag.embeddings import embed_batch
from rag.chroma_client import add_chunks, delete_by_source, folder_to_collection, list_collection_names

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", "/data/knowledge")
CONFIG_PATH = os.getenv("CONFIG_PATH", "/data/config")
LOGS_PATH = "/data/logs"
STATE_FILE = os.path.join(CONFIG_PATH, "indexer_state.json")
LOG_FILE = os.path.join(LOGS_PATH, "indexer.log")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))


# ---------------------------------------------------------------------------
# Text Chunker
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks.
    Breaks at paragraph → newline → space boundaries when possible.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            # Find best break point in the second half of the chunk
            mid = start + chunk_size // 2
            for sep in ["\n\n", "\n", " "]:
                pos = text.rfind(sep, mid, end)
                if pos != -1:
                    end = pos + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        # Next chunk starts with overlap
        start = end - overlap
        if start <= 0:
            start = end  # safety: avoid infinite loop

    return [c for c in chunks if len(c.strip()) > 20]


# ---------------------------------------------------------------------------
# File Hashing
# ---------------------------------------------------------------------------

def file_hash(path: str) -> str:
    """MD5 hash of file contents."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_folder(file_path: str, knowledge_path: str) -> str:
    """Map a file path to its top-level knowledge folder (for collection naming)."""
    try:
        rel = Path(file_path).relative_to(knowledge_path)
        return rel.parts[0] if len(rel.parts) > 1 else "default"
    except ValueError:
        return "default"


# ---------------------------------------------------------------------------
# Persistent State
# ---------------------------------------------------------------------------

@dataclass
class FileRecord:
    path: str
    hash: str
    status: str          # "indexed" | "error" | "pending"
    indexed_at: str
    chunks: int
    collection: str
    error: str | None = None


class IndexerState:
    def __init__(self, state_file: str = STATE_FILE):
        self._file = state_file
        self.files: dict[str, FileRecord] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._file):
            return
        try:
            with open(self._file, encoding="utf-8") as f:
                data = json.load(f)
            for path, rec in data.get("files", {}).items():
                self.files[path] = FileRecord(**rec)
        except Exception as e:
            logger.warning("Could not load indexer state: %s", e)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._file), exist_ok=True)
        tmp = self._file + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"version": 1, "files": {p: asdict(r) for p, r in self.files.items()}},
                    f, indent=2,
                )
            os.replace(tmp, self._file)
        except Exception as e:
            logger.error("Could not save indexer state: %s", e)

    def get(self, path: str) -> FileRecord | None:
        return self.files.get(path)

    def set(self, record: FileRecord) -> None:
        self.files[record.path] = record
        self.save()

    def remove(self, path: str) -> None:
        self.files.pop(path, None)
        self.save()

    def needs_indexing(self, path: str) -> bool:
        """True if file is new or has changed since last indexing."""
        rec = self.files.get(path)
        if rec is None or rec.status != "indexed":
            return True
        try:
            return rec.hash != file_hash(path)
        except OSError:
            return True


# ---------------------------------------------------------------------------
# JSON-Lines Log
# ---------------------------------------------------------------------------

class IndexerLog:
    def __init__(self, log_file: str = LOG_FILE):
        self._file = log_file
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    def write(self, event: str, **kwargs: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **kwargs,
        }
        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Could not write indexer log: %s", e)

    def tail(self, n: int = 50) -> list[dict]:
        if not os.path.exists(self._file):
            return []
        lines = []
        try:
            with open(self._file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
        return lines[-n:]


# ---------------------------------------------------------------------------
# Watchdog → asyncio bridge
# ---------------------------------------------------------------------------

class _FileEventHandler(FileSystemEventHandler):
    """Forwards watchdog events to an asyncio Queue."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._q = queue
        self._loop = loop

    def _put(self, event_type: str, path: str) -> None:
        asyncio.run_coroutine_threadsafe(self._q.put((event_type, path)), self._loop)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._put("created", event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._put("modified", event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._put("deleted", event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._put("deleted", event.src_path)
            self._put("created", event.dest_path)


# ---------------------------------------------------------------------------
# Indexer Service
# ---------------------------------------------------------------------------

class IndexerService:
    def __init__(self) -> None:
        self._state = IndexerState()
        self._log = IndexerLog()
        self._observer: Observer | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._knowledge_path = KNOWLEDGE_PATH

        # Live status (read by admin API)
        self._status: dict[str, Any] = {
            "running": False,
            "initial_indexing": False,
            "total_files": 0,
            "done_files": 0,
            "error_files": 0,
            "current_file": None,
            "progress_pct": 0,
            "eta_seconds": None,
            "started_at": None,
            "last_activity": None,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, knowledge_path: str = KNOWLEDGE_PATH) -> None:
        self._knowledge_path = knowledge_path
        self._running = True
        self._status["running"] = True
        self._status["started_at"] = datetime.now(timezone.utc).isoformat()

        os.makedirs(knowledge_path, exist_ok=True)

        # Start watchdog observer
        loop = asyncio.get_event_loop()
        handler = _FileEventHandler(self._queue, loop)
        self._observer = Observer()
        self._observer.schedule(handler, knowledge_path, recursive=True)
        self._observer.start()
        logger.info("Watching %s for changes", knowledge_path)

        # Initial indexing + event loop in background
        asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
        logger.info("Indexer stopped")

    def status(self) -> dict[str, Any]:
        return dict(self._status)

    def log_tail(self, n: int = 50) -> list[dict]:
        return self._log.tail(n)

    async def reindex_all(self) -> None:
        """Clear state and re-index everything."""
        self._state.files.clear()
        self._state.save()
        await self._initial_index()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        await self._verify_chromadb()
        await self._initial_index()
        await self._watch_loop()

    async def _verify_chromadb(self) -> None:
        """Check that indexed files still have their collections in ChromaDB.
        If a collection is missing (e.g. after ChromaDB data loss), mark
        those files as needing re-indexing."""
        try:
            existing = set(await asyncio.to_thread(list_collection_names))
        except Exception as e:
            logger.warning("Could not verify ChromaDB collections: %s", e)
            return

        invalidated = 0
        for path, rec in list(self._state.files.items()):
            if rec.status != "indexed":
                continue
            if rec.collection not in existing:
                logger.info("Collection '%s' missing in ChromaDB, will re-index: %s",
                            rec.collection, os.path.basename(path))
                rec.status = "pending"
                rec.hash = ""  # force re-index
                self._state.files[path] = rec
                invalidated += 1

        if invalidated:
            self._state.save()
            logger.warning("Invalidated %d files due to missing ChromaDB collections", invalidated)
        else:
            logger.info("ChromaDB verification OK — all collections present")

    async def _initial_index(self) -> None:
        """Scan knowledge_path and index all new or changed files."""
        path = Path(self._knowledge_path)
        all_files = [
            str(p) for p in path.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        pending = [f for f in all_files if self._state.needs_indexing(f)]
        total = len(pending)

        if total == 0:
            logger.info("Initial scan: all %d files already indexed", len(all_files))
            self._status["total_files"] = len(all_files)
            self._status["done_files"] = len(all_files)
            self._status["progress_pct"] = 100
            return

        logger.info("Initial indexing: %d files to index", total)
        self._status["initial_indexing"] = True
        self._status["total_files"] = total
        self._status["done_files"] = 0
        self._status["error_files"] = 0

        t_start = time.monotonic()

        for i, file_path in enumerate(pending):
            self._status["current_file"] = file_path
            await self._index_file(file_path)

            done = i + 1
            self._status["done_files"] = done
            self._status["progress_pct"] = int(done / total * 100)

            elapsed = time.monotonic() - t_start
            rate = done / elapsed if elapsed > 0 else 0
            remaining = total - done
            self._status["eta_seconds"] = int(remaining / rate) if rate > 0 else None

            # Yield to event loop so other tasks can run
            await asyncio.sleep(0)

        self._status["initial_indexing"] = False
        self._status["current_file"] = None
        self._status["eta_seconds"] = None
        self._status["last_activity"] = datetime.now(timezone.utc).isoformat()
        logger.info("Initial indexing complete: %d indexed, %d errors",
                    self._status["done_files"], self._status["error_files"])

    async def _watch_loop(self) -> None:
        """Process file system events from the watchdog queue."""
        while self._running:
            try:
                event_type, file_path = await asyncio.wait_for(
                    self._queue.get(), timeout=2.0
                )
            except asyncio.TimeoutError:
                continue

            if Path(file_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            if event_type in ("created", "modified"):
                logger.info("File %s: %s", event_type, file_path)
                await self._index_file(file_path)
            elif event_type == "deleted":
                logger.info("File deleted: %s", file_path)
                await self._delete_file(file_path)

    async def _index_file(self, file_path: str) -> None:
        """Parse → chunk → embed → upsert one file into ChromaDB."""
        t0 = time.monotonic()
        folder = get_folder(file_path, self._knowledge_path)
        self._status["current_file"] = file_path
        self._status["last_activity"] = datetime.now(timezone.utc).isoformat()

        try:
            fhash = file_hash(file_path)

            # Skip if unchanged
            rec = self._state.get(file_path)
            if rec and rec.hash == fhash and rec.status == "indexed":
                return

            # Remove old chunks if file was previously indexed
            if rec:
                delete_by_source(folder, file_path)

            # Parse
            text = await asyncio.to_thread(parse_file, file_path)
            if not text.strip():
                raise ValueError("File is empty or contains no extractable text")

            # Chunk
            chunks = chunk_text(text)
            if not chunks:
                raise ValueError("No valid chunks produced")

            # Embed (batch)
            embeddings = await embed_batch(chunks, log_progress=len(chunks) > 20)

            # Build metadata for each chunk
            rel_path = str(Path(file_path).relative_to(self._knowledge_path))
            metadatas = [
                {
                    "source": file_path,
                    "relative_path": rel_path,
                    "chunk_index": i,
                    "folder": folder,
                }
                for i in range(len(chunks))
            ]

            # Generate stable chunk IDs: hash + chunk index
            ids = [f"{fhash}_{i}" for i in range(len(chunks))]

            # Upsert to ChromaDB
            await asyncio.to_thread(add_chunks, folder, ids, embeddings, chunks, metadatas)

            duration_ms = int((time.monotonic() - t0) * 1000)

            self._state.set(FileRecord(
                path=file_path,
                hash=fhash,
                status="indexed",
                indexed_at=datetime.now(timezone.utc).isoformat(),
                chunks=len(chunks),
                collection=folder_to_collection(folder),
            ))

            self._log.write("indexed", file=rel_path, chunks=len(chunks), duration_ms=duration_ms)
            logger.info("Indexed '%s': %d chunks in %dms", rel_path, len(chunks), duration_ms)

        except Exception as e:
            self._status["error_files"] = self._status.get("error_files", 0) + 1
            rel_path = str(Path(file_path).relative_to(self._knowledge_path)) if self._knowledge_path in file_path else file_path
            self._log.write("error", file=rel_path, error=str(e))
            logger.error("Failed to index '%s': %s", file_path, e)

            self._state.set(FileRecord(
                path=file_path,
                hash="",
                status="error",
                indexed_at=datetime.now(timezone.utc).isoformat(),
                chunks=0,
                collection=folder_to_collection(folder),
                error=str(e),
            ))

    async def _delete_file(self, file_path: str) -> None:
        """Remove all chunks for a deleted file from ChromaDB."""
        folder = get_folder(file_path, self._knowledge_path)
        try:
            removed = await asyncio.to_thread(delete_by_source, folder, file_path)
            rel_path = str(Path(file_path).relative_to(self._knowledge_path)) if self._knowledge_path in file_path else file_path
            self._log.write("deleted", file=rel_path, chunks_removed=removed)
            self._state.remove(file_path)
            logger.info("Removed %d chunks for '%s'", removed, rel_path)
        except Exception as e:
            logger.error("Failed to delete chunks for '%s': %s", file_path, e)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

indexer = IndexerService()
