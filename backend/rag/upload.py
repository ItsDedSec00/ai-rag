"""
Temporary User Upload — Session-based context
----------------------------------------------
Uploaded files are parsed + chunked + embedded in-memory.
NOT stored in ChromaDB. Auto-cleanup after TTL expires.

Usage:
  POST /api/upload  →  returns { session_id, filename, chunks }
  POST /api/chat    →  include session_id to extend context
"""

import asyncio
import logging
import math
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile, File, HTTPException

from rag.parser import parse_file, SUPPORTED_EXTENSIONS
from rag.indexer import chunk_text
from rag.embeddings import embed_batch

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
SESSION_TTL = int(os.getenv("SESSION_TIMEOUT_MIN", "30")) * 60  # seconds


# ---------------------------------------------------------------------------
# Session store (in-memory)
# ---------------------------------------------------------------------------

@dataclass
class UploadSession:
    session_id: str
    filename: str
    chunks: list[str]
    embeddings: list[list[float]]
    created_at: float = field(default_factory=time.monotonic)


_sessions: dict[str, UploadSession] = {}


def get_session(session_id: str) -> UploadSession | None:
    session = _sessions.get(session_id)
    if session and (time.monotonic() - session.created_at) > SESSION_TTL:
        _sessions.pop(session_id, None)
        return None
    return session


def session_search(
    session_id: str,
    query_embedding: list[float],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Cosine similarity search against session chunks.
    Returns list of { text, source, score } dicts, sorted by score desc.
    """
    session = get_session(session_id)
    if not session or not session.embeddings:
        return []

    scored: list[tuple[float, int]] = []
    for i, emb in enumerate(session.embeddings):
        score = _cosine_sim(query_embedding, emb)
        scored.append((score, i))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, idx in scored[:top_k]:
        results.append({
            "text": session.chunks[idx],
            "source": f"[Upload] {session.filename}",
            "score": round(score, 4),
            "folder": "_upload",
        })
    return results


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Cleanup background task
# ---------------------------------------------------------------------------

async def cleanup_loop() -> None:
    """Remove expired sessions every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        expired = [
            sid for sid, s in _sessions.items()
            if (now - s.created_at) > SESSION_TTL
        ]
        for sid in expired:
            _sessions.pop(sid, None)
            logger.info("Session %s expired and removed", sid[:8])


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a document for temporary session context.
    Returns session_id to use with /api/chat.
    """
    # Validate extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Nicht unterstuetzter Dateityp: {ext}. "
                   f"Erlaubt: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Validate size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu gross: {size_mb:.1f} MB (max {MAX_UPLOAD_MB} MB)",
        )

    # Write to temp file for parser
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, dir="/tmp"
        )
        tmp.write(content)
        tmp.close()

        # Parse
        text = await asyncio.to_thread(parse_file, tmp.name)
        if not text.strip():
            raise HTTPException(status_code=400, detail="Datei ist leer oder nicht lesbar")

        # Chunk
        chunks = chunk_text(text)
        if not chunks:
            raise HTTPException(status_code=400, detail="Keine verwertbaren Textabschnitte gefunden")

        # Embed
        embeddings = await embed_batch(chunks, log_progress=len(chunks) > 20)

        # Store session
        session_id = str(uuid.uuid4())
        _sessions[session_id] = UploadSession(
            session_id=session_id,
            filename=file.filename or "upload",
            chunks=chunks,
            embeddings=embeddings,
        )

        logger.info(
            "Upload session %s: '%s' → %d chunks",
            session_id[:8], file.filename, len(chunks),
        )

        return {
            "session_id": session_id,
            "filename": file.filename,
            "chunks": len(chunks),
            "size_mb": round(size_mb, 2),
            "ttl_minutes": SESSION_TTL // 60,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload failed for '%s': %s", file.filename, e)
        raise HTTPException(status_code=500, detail=f"Upload-Fehler: {str(e)}")
    finally:
        if tmp and os.path.exists(tmp.name):
            os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# Session info endpoint
# ---------------------------------------------------------------------------

@router.get("/api/upload/{session_id}")
async def session_info(session_id: str):
    """Check if a session is still active."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session nicht gefunden oder abgelaufen")
    remaining = max(0, SESSION_TTL - (time.monotonic() - session.created_at))
    return {
        "session_id": session.session_id,
        "filename": session.filename,
        "chunks": len(session.chunks),
        "ttl_remaining_seconds": int(remaining),
    }
