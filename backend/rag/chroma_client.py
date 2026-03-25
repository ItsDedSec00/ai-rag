"""
ChromaDB HTTP Client (httpx-based, no chromadb Python package)
--------------------------------------------------------------
Uses the ChromaDB REST API directly.
Auto-detects v2 (>= 0.6) or v1 (< 0.6) API.

v2 base: /api/v2/tenants/default_tenant/databases/default_database/
v1 base: /api/v1/
"""

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")
_BASE = f"http://{CHROMA_HOST}:{CHROMA_PORT}"

_TENANT = "default_tenant"
_DB     = "default_database"

# Detected at first call, cached for the process lifetime
_api: str | None = None

# name → id cache to avoid repeated GET /collections/{name}
_col_id_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# API version detection
# ---------------------------------------------------------------------------

def _api_version() -> str:
    global _api
    if _api:
        return _api
    try:
        r = httpx.get(f"{_BASE}/api/v2/heartbeat", timeout=5)
        if r.status_code == 200:
            _api = "v2"
            logger.debug("ChromaDB API: v2")
            return "v2"
    except Exception:
        pass
    _api = "v1"
    logger.debug("ChromaDB API: v1 (fallback)")
    return "v1"


def _col_base() -> str:
    if _api_version() == "v2":
        return f"{_BASE}/api/v2/tenants/{_TENANT}/databases/{_DB}/collections"
    return f"{_BASE}/api/v1/collections"


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, **params: Any) -> Any:
    r = httpx.get(url, params=params or None, timeout=10)
    r.raise_for_status()
    return r.json()


def _post(url: str, body: dict, timeout: int = 30) -> Any:
    r = httpx.post(url, json=body, timeout=timeout)
    r.raise_for_status()
    # Some endpoints return empty body (204)
    if r.status_code == 204 or not r.content:
        return None
    return r.json()


def _delete(url: str) -> None:
    r = httpx.delete(url, timeout=10)
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Collection name helpers
# ---------------------------------------------------------------------------

def sanitize_collection_name(raw: str) -> str:
    """ChromaDB names: 3–63 chars, a-z/0-9/-/_, no leading/trailing specials."""
    name = raw.strip().lower()
    name = re.sub(r"[^a-z0-9_-]", "_", name)
    name = re.sub(r"[_-]{2,}", "_", name)
    name = name.strip("_-")
    name = name[:63]
    if len(name) < 3:
        name = (name + "kno")[:3]
    return name


def folder_to_collection(folder: str) -> str:
    if not folder or folder.strip("/") in ("", "."):
        return "default"
    leaf = folder.rstrip("/").split("/")[-1]
    return sanitize_collection_name(leaf)


# ---------------------------------------------------------------------------
# Collection CRUD
# ---------------------------------------------------------------------------

def _get_collection_id(name: str) -> str:
    """Return the UUID for a collection name (cached)."""
    if name in _col_id_cache:
        return _col_id_cache[name]
    data = _get(f"{_col_base()}/{name}")
    col_id = data["id"]
    _col_id_cache[name] = col_id
    return col_id


def get_or_create_collection(folder: str) -> str:
    """
    Get or create a ChromaDB collection for a folder.
    Returns the collection name.
    """
    name = folder_to_collection(folder)
    body: dict[str, Any] = {
        "name": name,
        "metadata": {
            "hnsw:space": "cosine",
            "folder": folder or "root",
        },
    }
    if _api_version() == "v2":
        body["get_or_create"] = True
        data = _post(_col_base(), body)
    else:
        # v1: POST returns existing or raises 409
        try:
            data = _post(_col_base(), body)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                data = _get(f"{_col_base()}/{name}")
            else:
                raise

    _col_id_cache[name] = data["id"]
    logger.debug("Collection '%s' ready (id=%s)", name, data["id"])
    return name


def list_collections() -> list[dict[str, Any]]:
    """Return raw collection dicts from ChromaDB."""
    data = _get(_col_base())
    # v2 may return {"collections": [...]} or just [...]
    if isinstance(data, dict):
        return data.get("collections", [])
    return data


def delete_collection(folder: str) -> bool:
    name = folder_to_collection(folder)
    try:
        _delete(f"{_col_base()}/{name}")
        _col_id_cache.pop(name, None)
        logger.info("Deleted collection '%s'", name)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Chunk operations
# ---------------------------------------------------------------------------

def add_chunks(
    folder: str,
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    """Upsert chunks (idempotent)."""
    name = get_or_create_collection(folder)
    col_id = _get_collection_id(name)
    _post(
        f"{_col_base()}/{col_id}/upsert",
        {
            "ids": ids,
            "embeddings": embeddings,
            "documents": documents,
            "metadatas": metadatas,
        },
    )
    logger.info("Upserted %d chunks → '%s'", len(ids), name)


def delete_by_source(folder: str, source_path: str) -> int:
    """Delete all chunks from a source file. Returns count removed."""
    name = get_or_create_collection(folder)
    col_id = _get_collection_id(name)

    # First fetch the IDs to delete
    result = _post(
        f"{_col_base()}/{col_id}/get",
        {"where": {"source": source_path}, "include": []},
    )
    ids: list[str] = result.get("ids", []) if result else []
    if not ids:
        return 0

    _post(f"{_col_base()}/{col_id}/delete", {"ids": ids})
    logger.info("Removed %d chunks for '%s'", len(ids), source_path)
    return len(ids)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def similarity_search(
    folder: str,
    query_embedding: list[float],
    n_results: int = 5,
    where: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return top-k similar chunks."""
    name = get_or_create_collection(folder)
    col_id = _get_collection_id(name)

    # Get count first to avoid querying empty collections
    count = _get(f"{_col_base()}/{col_id}/count")
    if count == 0:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    body: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": min(n_results, count),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        body["where"] = where
    return _post(f"{_col_base()}/{col_id}/query", body)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def collections_stats() -> dict[str, Any]:
    """Return stats for all collections (admin panel)."""
    cols = list_collections()
    stats = []
    total = 0

    for col in cols:
        col_id = col.get("id", "")
        name   = col.get("name", "")
        meta   = col.get("metadata") or {}

        try:
            count = _get(f"{_col_base()}/{col_id}/count")
        except Exception:
            count = -1

        total += max(count, 0)
        stats.append({
            "name": name,
            "chunk_count": count,
            "folder": meta.get("folder", name),
            "metadata": meta,
        })

    return {"collections": stats, "total_chunks": total}
