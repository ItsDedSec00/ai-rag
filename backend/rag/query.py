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
  data: {"type": "thinking", "content": "..."}   ← DeepSeek-R1 reasoning
  data: {"type": "token",    "content": "..."}
  data: {"type": "sources",  "sources": [...]}
  data: {"type": "done"}
  data: {"type": "error",    "message": "..."}
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

import config as cfg
from rag.embeddings import embed_text
from rag.chroma_client import similarity_search, list_collection_names
from rag.upload import session_search

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Infrastructure (not user-changeable)
# ---------------------------------------------------------------------------

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    collection: str | None = Field(None, description="Specific collection to search, or None for all")
    session_id: str | None = Field(None, description="Upload session ID for temporary context")
    top_k: int | None = Field(None, ge=1, le=20)
    temperature: float | None = Field(None, ge=0.0, le=2.0)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(
    query: str,
    context_chunks: list[dict[str, Any]],
) -> str:
    """Build the final prompt with system instruction + RAG context + query."""
    system_prompt = cfg.ollama_system_prompt()

    # Append language instruction if set
    lang = cfg.ollama_response_language()
    if lang and lang != "auto":
        system_prompt += f"\n\nAntworte immer auf {lang}."

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
        f"{system_prompt}\n\n"
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
    # Use collection names directly (not metadata) to avoid v2 compat issues
    if collection:
        col_names = [collection]
    else:
        col_names = await asyncio.to_thread(list_collection_names)

    logger.debug("Searching %d collection(s): %s", len(col_names), col_names)

    for col_name in col_names:
        try:
            result = await asyncio.to_thread(
                similarity_search, col_name, query_embedding, top_k
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
            logger.warning("Search in collection '%s' failed: %s", col_name, e)

    # Sort by score descending, take top_k
    all_results.sort(key=lambda x: x["score"], reverse=True)
    top = all_results[:top_k]

    # Filter by minimum similarity score
    min_score = cfg.rag_min_score()
    top = [r for r in top if r["score"] >= min_score]

    context_chunks = [{"text": r["text"], "source": r["source"]} for r in top]

    # Limit displayed sources (may differ from retrieval top_k)
    display_limit = cfg.rag_display_sources()
    sources = [
        {
            "file": r["source"],
            "score": r["score"],
            "folder": r["folder"],
            "preview": r["text"][:150] + "..." if len(r["text"]) > 150 else r["text"],
        }
        for r in top[:display_limit]
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
    # State machine for <think>...</think> reasoning blocks
    # States: "detect" → "thinking" → "answering"
    in_thinking = False
    thinking_detected = False
    token_buffer = ""

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
                        "top_p": cfg.ollama_top_p(),
                        "num_ctx": cfg.ollama_context_window(),
                        "num_predict": cfg.ollama_max_tokens(),
                        "repeat_penalty": cfg.ollama_repeat_penalty(),
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
                        # Buffer tokens to detect <think> / </think> tags
                        token_buffer += token

                        # Detect opening <think>
                        if not thinking_detected and "<think>" in token_buffer:
                            thinking_detected = True
                            in_thinking = True
                            # Send "thinking_start" event
                            yield _sse("thinking_start", {})
                            # Strip the <think> tag and send remaining as thinking
                            after = token_buffer.split("<think>", 1)[1]
                            token_buffer = ""
                            if after:
                                yield _sse("thinking", {"content": after})
                            continue

                        # Inside thinking block
                        if in_thinking:
                            if "</think>" in token_buffer:
                                # End of thinking
                                before_end = token_buffer.split("</think>", 1)[0]
                                after_end = token_buffer.split("</think>", 1)[1]
                                if before_end:
                                    yield _sse("thinking", {"content": before_end})
                                yield _sse("thinking_end", {})
                                in_thinking = False
                                token_buffer = ""
                                # Send remaining text after </think> as normal token
                                after_end = after_end.lstrip("\n")
                                if after_end:
                                    yield _sse("token", {"content": after_end})
                            else:
                                # Still thinking — flush buffer but keep last
                                # 10 chars in case </think> spans chunks
                                if len(token_buffer) > 10:
                                    flush = token_buffer[:-10]
                                    token_buffer = token_buffer[-10:]
                                    yield _sse("thinking", {"content": flush})
                            continue

                        # Normal token (no thinking)
                        # Flush buffer if it's long enough that <think> won't appear
                        if len(token_buffer) > 10 or thinking_detected:
                            yield _sse("token", {"content": token_buffer})
                            token_buffer = ""
                        elif len(token_buffer) > 10:
                            flush = token_buffer[:-7]
                            token_buffer = token_buffer[-7:]
                            yield _sse("token", {"content": flush})

                    if chunk.get("done", False):
                        # Flush remaining buffer
                        if token_buffer:
                            evt = "thinking" if in_thinking else "token"
                            yield _sse(evt, {"content": token_buffer})
                            token_buffer = ""
                        if in_thinking:
                            yield _sse("thinking_end", {})

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

    # Resolve per-request values from config (with optional request overrides)
    top_k = req.top_k if req.top_k is not None else cfg.rag_top_k()
    temperature = req.temperature if req.temperature is not None else cfg.ollama_temperature()
    model = cfg.ollama_model()

    # 1. Retrieve context from ChromaDB
    try:
        context_chunks, sources = await _retrieve_context(
            req.message, req.collection, top_k, req.session_id
        )
    except Exception as e:
        logger.error("Context retrieval failed: %s", e)
        context_chunks, sources = [], []

    # 2. Build prompt
    prompt = _build_prompt(req.message, context_chunks)
    logger.debug("Prompt length: %d chars, %d context chunks", len(prompt), len(context_chunks))

    # 3. Stream response
    return StreamingResponse(
        _stream_ollama(prompt, model, temperature, sources, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )
