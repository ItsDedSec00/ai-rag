"""
RAG Query Engine + SSE Streaming
---------------------------------
POST /api/chat flow:
1. Embed the user query via Ollama
2. Search ChromaDB for top-k similar chunks
3. Build prompt: system_prompt + context chunks + user query
4. Stream Ollama /api/generate response as SSE events
5. Send source attribution as final SSE event

SSE event format:
  data: {"type": "token",   "content": "..."}
  data: {"type": "sources", "sources": [...]}
  data: {"type": "done"}
  data: {"type": "error",   "message": "..."}
"""

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag.embeddings import embed_text
from rag.chroma_client import similarity_search, list_collections
from rag.upload import session_search

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2:1b")
TOP_K = int(os.getenv("RAG_TOP_K", "5"))
CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", "4096"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
TOP_P = float(os.getenv("TOP_P", "0.9"))

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", (
    "Du bist ein hilfreicher Assistent. Beantworte die Frage des Nutzers "
    "basierend auf dem folgenden Kontext. Wenn der Kontext keine Antwort "
    "enthält, sage ehrlich, dass du es nicht weißt. "
    "Antworte auf Deutsch, es sei denn der Nutzer fragt in einer anderen Sprache."
))


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    collection: str | None = Field(None, description="Specific collection to search, or None for all")
    session_id: str | None = Field(None, description="Upload session ID for temporary context")
    top_k: int = Field(default=TOP_K, ge=1, le=20)
    temperature: float = Field(default=TEMPERATURE, ge=0.0, le=2.0)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(
    query: str,
    context_chunks: list[dict[str, Any]],
) -> str:
    """Build the final prompt with system instruction + RAG context + query."""
    if not context_chunks:
        context_block = "(Kein relevanter Kontext verfügbar.)"
    else:
        parts = []
        for i, chunk in enumerate(context_chunks, 1):
            source = chunk.get("source", "Unbekannt")
            text = chunk.get("text", "")
            parts.append(f"[Quelle {i}: {source}]\n{text}")
        context_block = "\n\n---\n\n".join(parts)

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"=== KONTEXT ===\n{context_block}\n\n"
        f"=== FRAGE ===\n{query}"
    )


# ---------------------------------------------------------------------------
# ChromaDB search → context chunks
# ---------------------------------------------------------------------------

async def _retrieve_context(
    query: str,
    collection: str | None,
    top_k: int,
    session_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Embed query → search ChromaDB (+ optional upload session) → return results.
    context_chunks: [{"text": "...", "source": "..."}]
    sources: [{"file": "...", "score": float, "preview": "..."}]
    """
    query_embedding = await embed_text(query)

    all_results: list[dict[str, Any]] = []

    # --- Session-based upload chunks (in-memory similarity search) ---
    if session_id:
        session_results = session_search(session_id, query_embedding, top_k=top_k)
        all_results.extend(session_results)

    # --- ChromaDB knowledge base search ---
    if collection:
        folders = [collection]
    else:
        cols = await asyncio.to_thread(list_collections)
        folders = [
            (c.get("metadata") or {}).get("folder", c.get("name", "default"))
            for c in cols
        ]
        if not folders:
            folders = ["default"]

    for folder in folders:
        try:
            result = await asyncio.to_thread(
                similarity_search, folder, query_embedding, top_k
            )
            docs = result.get("documents", [[]])[0]
            metas = result.get("metadatas", [[]])[0]
            dists = result.get("distances", [[]])[0]

            for doc, meta, dist in zip(docs, metas, dists):
                score = max(0.0, 1.0 - (dist / 2.0))
                all_results.append({
                    "text": doc,
                    "source": (meta or {}).get("relative_path", "unknown"),
                    "score": round(score, 4),
                    "folder": (meta or {}).get("folder", "default"),
                })
        except Exception as e:
            logger.warning("Search in folder '%s' failed: %s", folder, e)

    # Sort by score descending, take top_k
    all_results.sort(key=lambda x: x["score"], reverse=True)
    top = all_results[:top_k]

    context_chunks = [{"text": r["text"], "source": r["source"]} for r in top]
    sources = [
        {
            "file": r["source"],
            "score": r["score"],
            "folder": r["folder"],
            "preview": r["text"][:150] + "..." if len(r["text"]) > 150 else r["text"],
        }
        for r in top
    ]

    return context_chunks, sources


# ---------------------------------------------------------------------------
# SSE streaming from Ollama
# ---------------------------------------------------------------------------

def _sse(event_type: str, data: dict) -> str:
    """Format a single SSE event line."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_ollama(
    prompt: str,
    model: str,
    temperature: float,
    sources: list[dict[str, Any]],
    request: Request,
) -> AsyncGenerator[str, None]:
    """
    Stream Ollama /api/generate response as SSE events.
    Yields: token events, then sources, then done.
    """
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                        "top_p": TOP_P,
                        "num_ctx": CONTEXT_WINDOW,
                    },
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    # Check if client disconnected
                    if await request.is_disconnected():
                        logger.info("Client disconnected, aborting stream")
                        return

                    if not line.strip():
                        continue

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("response", "")
                    if token:
                        yield _sse("token", {"content": token})

                    if chunk.get("done", False):
                        # Include generation stats
                        stats = {}
                        if "total_duration" in chunk:
                            stats["total_duration_ms"] = chunk["total_duration"] // 1_000_000
                        if "eval_count" in chunk and "eval_duration" in chunk:
                            eval_dur_s = chunk["eval_duration"] / 1e9
                            if eval_dur_s > 0:
                                stats["tokens_per_second"] = round(
                                    chunk["eval_count"] / eval_dur_s, 1
                                )
                        yield _sse("sources", {"sources": sources, "stats": stats})
                        yield _sse("done", {})
                        return

    except httpx.HTTPStatusError as e:
        error_msg = f"Ollama error: {e.response.status_code}"
        try:
            detail = e.response.json().get("error", str(e))
            error_msg = f"Ollama: {detail}"
        except Exception:
            pass
        yield _sse("error", {"message": error_msg})

    except httpx.ConnectError:
        yield _sse("error", {"message": "Ollama ist nicht erreichbar. Ist der Container gestartet?"})

    except Exception as e:
        logger.error("Stream error: %s", e)
        yield _sse("error", {"message": f"Interner Fehler: {str(e)}"})


# ---------------------------------------------------------------------------
# POST /api/chat endpoint
# ---------------------------------------------------------------------------

@router.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """
    RAG chat endpoint with SSE streaming.
    Returns: text/event-stream with token/sources/done/error events.
    """
    logger.info("Chat request: %.100s...", req.message)

    # 1. Retrieve context from ChromaDB
    try:
        context_chunks, sources = await _retrieve_context(
            req.message, req.collection, req.top_k, req.session_id
        )
    except Exception as e:
        logger.error("Context retrieval failed: %s", e)
        context_chunks, sources = [], []

    # 2. Build prompt
    prompt = _build_prompt(req.message, context_chunks)
    logger.debug("Prompt length: %d chars, %d context chunks", len(prompt), len(context_chunks))

    # 3. Stream response
    return StreamingResponse(
        _stream_ollama(prompt, CHAT_MODEL, req.temperature, sources, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )
