# RAG-Chat — © 2026 David Dülle
# https://duelle.org

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import httpx

from admin.routes import router as admin_router
from admin.system import request_counter
from rag.query import router as chat_router
from rag.upload import router as upload_router, cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    import config as cfg
    cfg.load()

    # GPU detection on every start
    from utils.gpu import get_gpu_info
    gpu = get_gpu_info()
    app.state.gpu_info = gpu
    mode = gpu.get("mode", "cpu")
    if mode == "nvidia":
        gpus = gpu.get("gpus", [])
        names = ", ".join(g.get("name", "?") for g in gpus)
        total_vram = gpu.get("total_vram_mb", 0)
        print(f"[RAG-Chat] GPU erkannt: {names} ({total_vram} MB VRAM) — GPU-Modus")
    elif mode == "amd":
        print(f"[RAG-Chat] AMD GPU erkannt — {gpu.get('note', 'CPU-Modus')}")
    else:
        print("[RAG-Chat] Keine GPU erkannt — CPU-Modus (langsamer)")

    from rag.indexer import indexer
    import asyncio
    asyncio.create_task(
        indexer.start(os.getenv("KNOWLEDGE_PATH", "/data/knowledge"))
    )
    asyncio.create_task(cleanup_loop())
    yield
    # --- shutdown ---
    await indexer.stop()


app = FastAPI(title="RAG-Chat Backend", version="0.1.0", lifespan=lifespan)

app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(upload_router)


# ---------------------------------------------------------------------------
# Middleware: request counter (counts /api/chat requests)
# ---------------------------------------------------------------------------

class RequestCounterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/api/chat" and request.method == "POST":
            request_counter.increment()
        return await call_next(request)


app.add_middleware(RequestCounterMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")


@app.get("/api/health")
async def health(request: Request):
    status: dict = {"status": "ok", "services": {}}

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags")
            status["services"]["ollama"] = "ok" if r.status_code == 200 else "error"
    except Exception:
        status["services"]["ollama"] = "unavailable"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            for path in ("/api/v2/heartbeat", "/api/v1/heartbeat"):
                try:
                    r = await client.get(f"http://{CHROMA_HOST}:{CHROMA_PORT}{path}")
                    if r.status_code == 200:
                        status["services"]["chromadb"] = "ok"
                        break
                except Exception:
                    continue
            else:
                status["services"]["chromadb"] = "error"
    except Exception:
        status["services"]["chromadb"] = "unavailable"

    # GPU status from startup detection
    gpu = getattr(request.app.state, "gpu_info", None)
    if gpu:
        mode = gpu.get("mode", "cpu")
        gpu_status: dict = {"mode": mode}
        if mode == "nvidia":
            gpus = gpu.get("gpus", [])
            gpu_status["gpu_name"] = ", ".join(g.get("name", "?") for g in gpus)
            gpu_status["vram_total_mb"] = gpu.get("total_vram_mb", 0)
            gpu_status["gpu_count"] = gpu.get("gpu_count", 1)
        elif mode == "amd":
            gpu_status["note"] = gpu.get("note", "")
        else:
            gpu_status["note"] = gpu.get("note", "Keine GPU erkannt. CPU-Modus (langsamer).")
        status["gpu"] = gpu_status

    return status


@app.get("/api/branding")
async def branding():
    """Public endpoint: app name, logo, color, chat settings."""
    import config as cfg
    return {
        "app_name": cfg.branding_app_name(),
        "logo_url": cfg.branding_logo_url(),
        "primary_color": cfg.branding_primary_color(),
        "welcome_message": cfg.chat_welcome(),
        "placeholder": cfg.chat_placeholder(),
        "history_limit": cfg.chat_history_limit(),
        "markdown_enabled": cfg.chat_markdown_enabled(),
    }
