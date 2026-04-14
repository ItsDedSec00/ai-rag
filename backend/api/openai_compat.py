# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
OpenAI-compatible API layer
----------------------------
Exposes two endpoints that follow the OpenAI Chat Completions spec:

  GET  /v1/models
  POST /v1/chat/completions  (streaming + non-streaming)

Authentication: Bearer token (API key) via require_api_key Depends().

The endpoint reuses the existing RAG pipeline from rag/query.py:
  _retrieve_context  → ChromaDB search
  _build_messages    → system prompt + RAG context + history
  _stream_ollama     → Ollama streaming + SSE events

RAG sources are attached as a non-standard `x_rag_sources` field on
non-streaming responses, and as an SSE comment on streaming responses
(both are silently ignored by standard OpenAI SDK clients).
"""

import json
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import config as cfg
from api.auth import require_api_key
# Reuse internal pipeline functions directly
from rag.query import _retrieve_context, _build_messages, _stream_ollama, HistoryMessage

router = APIRouter(prefix="/v1", tags=["openai-compat"])


# ---------------------------------------------------------------------------
# Request / Response models (OpenAI spec)
# ---------------------------------------------------------------------------

class OAIMessage(BaseModel):
    role: str       # "system" | "user" | "assistant"
    content: str


class OAIChatRequest(BaseModel):
    model: str
    messages: list[OAIMessage]
    stream: bool = False
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = None
    # Non-standard extensions (ignored by standard OpenAI clients)
    collection: str | None = None    # RAG collection override
    top_k: int | None = Field(None, ge=1, le=20)


class OAIChoice(BaseModel):
    index: int
    message: OAIMessage
    finish_reason: str


class OAIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OAIChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[OAIChoice]
    usage: OAIUsage
    x_rag_sources: list[dict] | None = None   # non-standard; ignored by clients


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3."""
    return max(1, int(len(text.split()) * 1.3))


def _map_messages(messages: list[OAIMessage]) -> tuple[str, list[HistoryMessage]]:
    """Convert OpenAI messages list to (query, history).

    - system messages are skipped (server config governs system prompt)
    - the last user message becomes the query
    - all preceding user/assistant messages become history
    """
    history: list[HistoryMessage] = []
    query = ""

    for msg in messages:
        if msg.role == "system":
            continue
        if msg.role in ("user", "assistant"):
            history.append(HistoryMessage(role=msg.role, content=msg.content))

    # Pop the last user message as the current query
    if history and history[-1].role == "user":
        query = history.pop().content

    return query, history


def _oai_chunk(cid: str, created: int, model: str, delta: dict, finish_reason: str | None) -> str:
    """Format one OpenAI streaming SSE chunk."""
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(key: dict = Depends(require_api_key)):
    """Return the active Ollama model as the only available model."""
    model = cfg.ollama_model()
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ollama",
            }
        ],
    }


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------

@router.post("/chat/completions")
async def chat_completions(
    req: OAIChatRequest,
    request: Request,
    key: dict = Depends(require_api_key),
):
    """OpenAI-compatible chat completions endpoint.

    Supports streaming (stream=true) and non-streaming responses.
    Uses the RAG pipeline unless api.rag_enabled is false in config.
    """
    query, history = _map_messages(req.messages)
    if not query:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No user message found in messages")

    model = cfg.ollama_model()   # always use the server's active model
    top_k = req.top_k if req.top_k is not None else cfg.rag_top_k()
    temperature = req.temperature if req.temperature is not None else cfg.ollama_temperature()

    # Retrieve RAG context (unless disabled)
    if cfg.api_rag_enabled():
        try:
            context_chunks, sources = await _retrieve_context(
                query, req.collection, top_k
            )
        except Exception:
            context_chunks, sources = [], []
    else:
        context_chunks, sources = [], []

    messages = _build_messages(query, context_chunks, history)

    if req.stream:
        return await _streaming_response(request, messages, model, temperature, sources)
    else:
        return await _non_streaming_response(request, messages, model, temperature, sources)


async def _non_streaming_response(
    request: Request,
    messages: list[dict],
    model: str,
    temperature: float,
    sources: list[dict],
) -> OAIChatResponse:
    """Consume the internal SSE stream and return a single OAIChatResponse."""
    full_text = ""
    final_sources: list[dict] = []

    async for event_str in _stream_ollama(messages, model, temperature, sources, request):
        if not event_str.startswith("data: "):
            continue
        try:
            evt = json.loads(event_str[6:])
        except json.JSONDecodeError:
            continue

        if evt.get("type") == "token":
            full_text += evt.get("content", "")
        elif evt.get("type") == "sources":
            final_sources = evt.get("sources", [])

    prompt_tokens = _estimate_tokens(json.dumps(messages))
    completion_tokens = _estimate_tokens(full_text)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    return OAIChatResponse(
        id=completion_id,
        created=int(time.time()),
        model=model,
        choices=[
            OAIChoice(
                index=0,
                message=OAIMessage(role="assistant", content=full_text),
                finish_reason="stop",
            )
        ],
        usage=OAIUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        x_rag_sources=final_sources or None,
    )


async def _streaming_response(
    request: Request,
    messages: list[dict],
    model: str,
    temperature: float,
    sources: list[dict],
) -> StreamingResponse:
    """Translate internal SSE events into OpenAI streaming chunks."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    async def event_generator():
        # First chunk: announce the assistant role
        yield _oai_chunk(completion_id, created, model, {"role": "assistant"}, None)

        async for event_str in _stream_ollama(messages, model, temperature, sources, request):
            if not event_str.startswith("data: "):
                continue
            try:
                evt = json.loads(event_str[6:])
            except json.JSONDecodeError:
                continue

            evt_type = evt.get("type")

            if evt_type == "token":
                yield _oai_chunk(
                    completion_id, created, model,
                    {"content": evt.get("content", "")},
                    None,
                )

            elif evt_type == "sources":
                srcs = evt.get("sources", [])
                if srcs:
                    # SSE comment — silently ignored by standard clients
                    yield f": x-rag-sources {json.dumps(srcs, ensure_ascii=False)}\n\n"

            elif evt_type == "done":
                yield _oai_chunk(completion_id, created, model, {}, "stop")
                yield "data: [DONE]\n\n"
                return

            elif evt_type == "error":
                msg = evt.get("message", "Unknown error")
                yield _oai_chunk(
                    completion_id, created, model,
                    {"content": f"\n\n[Error: {msg}]"},
                    "stop",
                )
                yield "data: [DONE]\n\n"
                return

            # thinking_start / thinking / thinking_end are silently dropped
            # (internal DeepSeek-R1 reasoning, not part of OpenAI spec)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
