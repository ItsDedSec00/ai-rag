# RAG-Chat — © 2026 David Dülle
# https://duelle.org

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.gpu import get_gpu_info
from rag.embeddings import get_embedding_model_status, pull_model
from rag.chroma_client import collections_stats
from rag.indexer import indexer
from admin.system import get_system_info

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# System Dashboard
# ---------------------------------------------------------------------------

@router.get("/system")
def system_info():
    """Full system metrics for the admin dashboard."""
    return get_system_info()


# ---------------------------------------------------------------------------
# GPU / System
# ---------------------------------------------------------------------------

@router.get("/gpu")
def gpu_info():
    """GPU detection info + model recommendation."""
    return get_gpu_info()


# ---------------------------------------------------------------------------
# ChromaDB Collections
# ---------------------------------------------------------------------------

@router.get("/collections")
def list_collections():
    """All ChromaDB collections with chunk counts."""
    try:
        return collections_stats()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ChromaDB unavailable: {e}")


# ---------------------------------------------------------------------------
# Embedding Model
# ---------------------------------------------------------------------------

@router.get("/embedding-model")
async def embedding_model_status():
    """Check if the Ollama embedding model is pulled and ready."""
    return await get_embedding_model_status()


class PullRequest(BaseModel):
    model: str = "nomic-embed-text"


@router.post("/embedding-model/pull")
async def pull_embedding_model(req: PullRequest):
    """Trigger Ollama to download the embedding model."""
    result = await pull_model(req.model)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

@router.get("/indexer/status")
def indexer_status():
    """Current indexer progress and stats."""
    return indexer.status()


@router.get("/indexer/logs")
def indexer_logs(n: int = 50):
    """Last N indexer log entries."""
    return {"logs": indexer.log_tail(n)}


@router.post("/indexer/reindex")
async def trigger_reindex():
    """Clear indexer state and re-index all files from scratch."""
    await indexer.reindex_all()
    return {"status": "reindex_started"}
