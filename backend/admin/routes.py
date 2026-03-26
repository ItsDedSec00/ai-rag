# RAG-Chat — © 2026 David Dülle
# https://duelle.org

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import config as cfg
from utils.gpu import get_gpu_info
from rag.embeddings import get_embedding_model_status, pull_model
from rag.chroma_client import collections_stats
from rag.indexer import indexer
from admin.system import get_system_info
from admin.models import (
    get_recommendations, list_installed_models, pull_model_stream,
    delete_model, get_active_model, set_active_model,
    update_generation_params, add_custom_model, remove_custom_model,
    show_model_info,
)
from admin.files import (
    list_files, create_folder, rename_folder, delete_folder,
    save_upload, rename_file, delete_file, move_file, get_stats,
    check_duplicates,
)
from admin.updates import (
    get_update_status, get_update_log, request_update, request_rollback,
    get_flag_status,
)

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
# Model Management (ADM-02)
# ---------------------------------------------------------------------------

@router.get("/models/recommendations")
def model_recommendations():
    """Hardware-aware model catalog with compatibility info."""
    return get_recommendations()


@router.get("/models/installed")
async def models_installed():
    """List all models currently downloaded in Ollama."""
    return {"models": await list_installed_models()}


@router.get("/models/active")
def models_active():
    """Current active chat model + generation params."""
    return get_active_model()


class SetActiveRequest(BaseModel):
    model: str

@router.post("/models/active")
def models_set_active(req: SetActiveRequest):
    """Switch the active chat model."""
    return set_active_model(req.model)


class ModelPullRequest(BaseModel):
    model: str

@router.post("/models/pull")
async def models_pull(req: ModelPullRequest):
    """Pull a model from Ollama with SSE progress stream."""
    import json

    async def event_stream():
        try:
            async for chunk in pull_model_stream(req.model):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield f"data: {json.dumps({'status': 'success'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ModelDeleteRequest(BaseModel):
    model: str

@router.post("/models/delete")
async def models_delete(req: ModelDeleteRequest):
    """Delete a model from Ollama."""
    result = await delete_model(req.model)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result.get("detail"))
    return result


class GenerationParamsRequest(BaseModel):
    temperature: float | None = None
    top_p: float | None = None
    context_window: int | None = None
    system_prompt: str | None = None
    max_tokens: int | None = None
    repeat_penalty: float | None = None
    response_language: str | None = None
    thinking_mode: bool | None = None

@router.post("/models/params")
def models_update_params(req: GenerationParamsRequest):
    """Update generation parameters."""
    return update_generation_params(
        temperature=req.temperature,
        top_p=req.top_p,
        context_window=req.context_window,
        system_prompt=req.system_prompt,
        max_tokens=req.max_tokens,
        repeat_penalty=req.repeat_penalty,
        response_language=req.response_language,
        thinking_mode=req.thinking_mode,
    )


class CustomModelRequest(BaseModel):
    model: str

@router.get("/models/show")
async def models_show(model: str):
    """Get detailed info for an installed model via Ollama /api/show."""
    result = await show_model_info(model)
    if result["status"] != "ok":
        raise HTTPException(status_code=404, detail=result.get("detail"))
    return result


@router.post("/models/custom")
def models_add_custom(req: CustomModelRequest):
    """Add a custom Ollama model ID."""
    result = add_custom_model(req.model)
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    return result

@router.post("/models/custom/remove")
def models_remove_custom(req: CustomModelRequest):
    """Remove a custom model from the list."""
    result = remove_custom_model(req.model)
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result.get("detail"))
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


# ---------------------------------------------------------------------------
# File Manager (ADM-03)
# ---------------------------------------------------------------------------

@router.get("/files")
def files_list(path: str = ""):
    """List files and folders in the knowledge base."""
    try:
        return list_files(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/files/stats")
def files_stats():
    """Knowledge base file statistics."""
    return get_stats()


class CreateFolderRequest(BaseModel):
    path: str

@router.post("/files/folder")
def files_create_folder(req: CreateFolderRequest):
    """Create a new folder in the knowledge base."""
    try:
        result = create_folder(req.path)
        if result["status"] != "ok":
            raise HTTPException(status_code=400, detail=result.get("detail"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class RenameFolderRequest(BaseModel):
    path: str
    new_name: str

@router.post("/files/rename-folder")
def files_rename_folder(req: RenameFolderRequest):
    """Rename a folder."""
    try:
        result = rename_folder(req.path, req.new_name)
        if result["status"] != "ok":
            raise HTTPException(status_code=400, detail=result.get("detail"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DeleteFolderRequest(BaseModel):
    path: str

@router.post("/files/delete-folder")
def files_delete_folder(req: DeleteFolderRequest):
    """Delete a folder and all its contents."""
    try:
        result = delete_folder(req.path)
        if result["status"] != "ok":
            raise HTTPException(status_code=400, detail=result.get("detail"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CheckDuplicatesRequest(BaseModel):
    folder: str = ""
    filenames: list[str]

@router.post("/files/check-duplicates")
def files_check_duplicates(req: CheckDuplicatesRequest):
    """Check which filenames already exist in the target folder."""
    try:
        return check_duplicates(req.folder, req.filenames)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/files/upload")
async def files_upload(
    file: UploadFile = File(...),
    folder: str = Form(""),
    on_conflict: str = Form("rename"),
):
    """Upload a file (or ZIP archive) to the knowledge base."""
    if on_conflict not in ("rename", "overwrite", "skip"):
        on_conflict = "rename"
    try:
        content = await file.read()
        result = save_upload(folder, file.filename or "upload", content, on_conflict)
        if result["status"] != "ok":
            raise HTTPException(status_code=400, detail=result.get("detail"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class RenameFileRequest(BaseModel):
    path: str
    new_name: str

@router.post("/files/rename")
def files_rename(req: RenameFileRequest):
    """Rename a file in the knowledge base."""
    try:
        result = rename_file(req.path, req.new_name)
        if result["status"] != "ok":
            raise HTTPException(status_code=400, detail=result.get("detail"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DeleteFileRequest(BaseModel):
    path: str

@router.post("/files/delete")
def files_delete(req: DeleteFileRequest):
    """Delete a single file from the knowledge base."""
    try:
        result = delete_file(req.path)
        if result["status"] != "ok":
            raise HTTPException(status_code=400, detail=result.get("detail"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class MoveFileRequest(BaseModel):
    path: str
    target_folder: str

@router.post("/files/move")
def files_move(req: MoveFileRequest):
    """Move a file to a different folder."""
    try:
        result = move_file(req.path, req.target_folder)
        if result["status"] != "ok":
            raise HTTPException(status_code=400, detail=result.get("detail"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Config Manager (ADM-06)
# ---------------------------------------------------------------------------

@router.get("/config")
def config_get():
    """Return the full current configuration."""
    return cfg.get()


class ConfigUpdateRequest(BaseModel):
    config: dict

@router.post("/config")
def config_update(req: ConfigUpdateRequest):
    """Update (merge) configuration values."""
    try:
        cfg.replace_all(req.config)
        return {"status": "ok", "config": cfg.get()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config/export")
def config_export():
    """Download the current config as a JSON file."""
    import json
    content = json.dumps(cfg.get(), indent=2, ensure_ascii=False)
    return JSONResponse(
        content=cfg.get(),
        headers={
            "Content-Disposition": "attachment; filename=rag-config.json",
        },
    )


@router.post("/config/import")
async def config_import(file: UploadFile = File(...)):
    """Import a config from an uploaded JSON file."""
    import json
    try:
        raw = await file.read()
        new_cfg = json.loads(raw.decode("utf-8"))
        # Auto-snapshot before import
        cfg.create_snapshot(label="pre_import")
        cfg.replace_all(new_cfg)
        return {"status": "ok", "config": cfg.get()}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Ungültige JSON-Datei")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SnapshotRequest(BaseModel):
    label: str = ""

@router.post("/config/snapshot")
def config_snapshot(req: SnapshotRequest):
    """Create a named snapshot of the current config."""
    result = cfg.create_snapshot(req.label)
    return {"status": "ok", **result}


@router.get("/config/snapshots")
def config_snapshots():
    """List all available config snapshots."""
    return {"snapshots": cfg.list_snapshots()}


class RestoreRequest(BaseModel):
    id: str

@router.post("/config/restore")
def config_restore(req: RestoreRequest):
    """Restore a config snapshot."""
    try:
        result = cfg.restore_snapshot(req.id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


class DeleteSnapshotRequest(BaseModel):
    id: str

@router.post("/config/snapshot/delete")
def config_snapshot_delete(req: DeleteSnapshotRequest):
    """Delete a config snapshot."""
    try:
        return cfg.delete_snapshot(req.id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Update Manager (ADM-04 / INF-04)
# ---------------------------------------------------------------------------

@router.get("/updates/status")
async def updates_status():
    """Current version + GitHub update availability."""
    return await get_update_status()


@router.get("/updates/log")
def updates_log(n: int = 20):
    """Last N update log entries."""
    return {"log": get_update_log(n)}


@router.get("/updates/flag")
def updates_flag():
    """Check if an update/rollback is currently pending."""
    return get_flag_status()


@router.post("/updates/trigger")
def updates_trigger():
    """Request an update via flag file (host-side watcher picks this up)."""
    result = request_update()
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result.get("detail"))
    return result


@router.post("/updates/rollback")
def updates_rollback():
    """Request a rollback via flag file."""
    result = request_rollback()
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result.get("detail"))
    return result
