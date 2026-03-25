"""
Ollama Embedding Client
-----------------------
Async wrapper around Ollama's /api/embeddings endpoint.
Uses nomic-embed-text by default (configurable via env).
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"


async def embed_text(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    """Embed a single text string. Returns a float vector."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{OLLAMA_BASE}/api/embeddings",
            json={"model": model, "prompt": text},
        )
        resp.raise_for_status()
        data = resp.json()
        if "embedding" not in data:
            raise ValueError(f"Ollama returned no embedding: {data}")
        return data["embedding"]


async def embed_batch(
    texts: list[str],
    model: str = EMBEDDING_MODEL,
    log_progress: bool = False,
) -> list[list[float]]:
    """
    Embed a list of texts sequentially.
    Ollama does not support true batch embedding.
    """
    embeddings: list[list[float]] = []
    total = len(texts)
    for i, text in enumerate(texts):
        embeddings.append(await embed_text(text, model))
        if log_progress and (i + 1) % 10 == 0:
            logger.info("Embedded %d/%d chunks", i + 1, total)
    return embeddings


async def check_model_available(model: str = EMBEDDING_MODEL) -> bool:
    """Return True if the model is already pulled in Ollama."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            resp.raise_for_status()
            pulled = [m["name"] for m in resp.json().get("models", [])]
            base = model.split(":")[0]
            return any(m == model or m.startswith(base) for m in pulled)
    except Exception:
        return False


async def pull_model(model: str = EMBEDDING_MODEL) -> dict[str, Any]:
    """
    Ask Ollama to pull a model (blocking until done).
    Suitable for the admin API endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/pull",
                json={"name": model, "stream": False},
            )
            resp.raise_for_status()
            return {"status": "ok", "model": model}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "model": model, "error": str(e)}
    except Exception as e:
        return {"status": "error", "model": model, "error": str(e)}


async def get_embedding_model_status(model: str = EMBEDDING_MODEL) -> dict[str, Any]:
    """Full status check: is Ollama reachable + is the model available."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            resp.raise_for_status()
            pulled = [m["name"] for m in resp.json().get("models", [])]
            base = model.split(":")[0]
            available = any(m == model or m.startswith(base) for m in pulled)
            return {
                "ollama_reachable": True,
                "model": model,
                "available": available,
                "pulled_models": pulled,
                "hint": None if available else f"Run: ollama pull {model}",
            }
    except Exception as e:
        return {
            "ollama_reachable": False,
            "model": model,
            "available": False,
            "error": str(e),
        }
