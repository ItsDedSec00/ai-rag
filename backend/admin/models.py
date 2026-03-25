# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
Model management: list, pull (with SSE progress), delete, switch active,
and hardware-aware recommendations for non-technical users.
"""

import os
import json
import asyncio
from typing import Any

import httpx

from utils.gpu import get_gpu_info

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

CONFIG_PATH = os.getenv("CONFIG_PATH", "/data/config")
CONFIG_FILE = os.path.join(CONFIG_PATH, "rag-config.json")


# ---------------------------------------------------------------------------
# Layperson-friendly model catalog
# ---------------------------------------------------------------------------

MODEL_CATALOG = [
    # ------------------------------------------------------------------
    # Einsteiger — für schwache Hardware
    # ------------------------------------------------------------------
    {
        "id": "llama3.2:1b",
        "name": "Llama 3.2 — 1B",
        "family": "Meta Llama",
        "params": "1B",
        "size_gb": 0.7,
        "speed": "sehr schnell",
        "quality": "einfach",
        "stars": 1,
        "min_ram_gb": 4,
        "min_vram_mb": 0,
        "description": "Das kleinste Modell — ideal zum Testen oder für sehr schwache Hardware. "
                       "Versteht einfache Fragen, aber Antworten können ungenau sein.",
        "best_for": "Testen, sehr schwache PCs",
        "tier": "einsteiger",
    },
    # ------------------------------------------------------------------
    # Standard — guter Alltag
    # ------------------------------------------------------------------
    {
        "id": "qwen3:8b",
        "name": "Qwen 3 — 8B",
        "family": "Alibaba Qwen",
        "params": "8B",
        "size_gb": 5.2,
        "speed": "schnell",
        "quality": "sehr gut",
        "stars": 3,
        "min_ram_gb": 8,
        "min_vram_mb": 4_000,
        "description": "Bestes Modell unter 10B für RAG-Anwendungen. "
                       "Versteht Deutsch sehr gut, liefert präzise Antworten "
                       "aus Dokumenten und bleibt nah am Quelltext.",
        "best_for": "RAG-Alltag, Dokumenten-Fragen, 8+ GB RAM",
        "tier": "standard",
    },
    # ------------------------------------------------------------------
    # Fortgeschritten — starke Qualität
    # ------------------------------------------------------------------
    {
        "id": "deepseek-r1:14b",
        "name": "DeepSeek-R1 — 14B",
        "family": "DeepSeek",
        "params": "14B",
        "size_gb": 9.0,
        "speed": "mittel",
        "quality": "sehr gut",
        "stars": 4,
        "min_ram_gb": 16,
        "min_vram_mb": 6_000,
        "description": "Reasoning-Modell: denkt Schritt für Schritt nach, bevor es antwortet. "
                       "Besonders gut bei komplexen Fragen, Fachtexten und "
                       "wenn die Antwort aus mehreren Quellen zusammengesetzt werden muss. "
                       "Etwas langsamer, dafür gründlicher.",
        "best_for": "Komplexe Fragen, Fachtexte, 16 GB RAM",
        "tier": "fortgeschritten",
    },
    {
        "id": "gpt-oss:20b",
        "name": "GPT-OSS — 20B",
        "family": "OpenAI",
        "params": "21B (3.6B aktiv)",
        "size_gb": 14.0,
        "speed": "schnell",
        "quality": "sehr gut",
        "stars": 4,
        "min_ram_gb": 16,
        "min_vram_mb": 8_000,
        "description": "OpenAIs erstes Open-Source-Modell. Nutzt Mixture-of-Experts — "
                       "nur 3.6B Parameter sind gleichzeitig aktiv, dadurch schnell "
                       "trotz 21B Gesamtgröße. Sehr gute Antwortqualität, "
                       "128K Kontextfenster, Apache-2.0-Lizenz.",
        "best_for": "Schnelle, präzise Antworten, 16+ GB RAM",
        "tier": "fortgeschritten",
    },
    # ------------------------------------------------------------------
    # Profi — beste Qualität
    # ------------------------------------------------------------------
    {
        "id": "qwen3:32b",
        "name": "Qwen 3 — 32B",
        "family": "Alibaba Qwen",
        "params": "32B",
        "size_gb": 20.0,
        "speed": "mittel",
        "quality": "exzellent",
        "stars": 5,
        "min_ram_gb": 32,
        "min_vram_mb": 16_000,
        "description": "Exzellentes RAG-Modell mit hervorragendem Deutsch. "
                       "Versteht komplexe Zusammenhänge über lange Dokumente, "
                       "zitiert Quellen präzise und liefert ausgewogene Antworten.",
        "best_for": "Beste RAG-Qualität, Server mit 32 GB RAM oder 16 GB VRAM",
        "tier": "profi",
    },
    {
        "id": "deepseek-r1:32b",
        "name": "DeepSeek-R1 — 32B",
        "family": "DeepSeek",
        "params": "32B",
        "size_gb": 20.0,
        "speed": "langsam",
        "quality": "exzellent",
        "stars": 5,
        "min_ram_gb": 32,
        "min_vram_mb": 20_000,
        "description": "Tiefes Reasoning auf GPT-4-Niveau. Denkt gründlich nach, "
                       "erkennt Widersprüche in Dokumenten und liefert gut begründete "
                       "Antworten. Ideal wenn Korrektheit wichtiger als Geschwindigkeit ist.",
        "best_for": "Maximale Korrektheit, 24+ GB VRAM",
        "tier": "profi",
    },
    {
        "id": "gpt-oss:120b",
        "name": "GPT-OSS — 120B",
        "family": "OpenAI",
        "params": "117B (5.1B aktiv)",
        "size_gb": 65.0,
        "speed": "mittel",
        "quality": "exzellent",
        "stars": 5,
        "min_ram_gb": 80,
        "min_vram_mb": 80_000,
        "description": "OpenAIs stärkstes Open-Source-Modell. Nahe an o4-mini-Niveau. "
                       "Mixture-of-Experts mit nur 5.1B aktiven Parametern, "
                       "läuft auf einer einzelnen 80-GB-GPU (H100/MI300X). "
                       "128K Kontext, exzellentes Reasoning.",
        "best_for": "Maximale Qualität, High-End GPU (80 GB VRAM)",
        "tier": "profi",
    },
]


# ---------------------------------------------------------------------------
# Hardware-aware recommendation
# ---------------------------------------------------------------------------

def get_recommendations() -> dict[str, Any]:
    """
    Return model catalog with per-model compatibility status
    and a top recommendation — explained for non-technical users.
    """
    hw = get_gpu_info()
    mode = hw.get("mode", "cpu")
    cpu = hw.get("cpu", {})
    ram_gb: float = cpu.get("ram_total_gb") or 0.0

    # VRAM: use total across all GPUs (Ollama splits models across GPUs)
    vram_mb: int | None = None
    gpu_count = hw.get("gpu_count", 0)
    if mode != "cpu" and hw.get("gpus"):
        vram_mb = hw.get("total_vram_mb") or sum(
            g.get("vram_total_mb", 0) for g in hw["gpus"]
        )
        gpu_count = len(hw["gpus"])

    # Score each model
    models = []
    best = None
    best_score = -1

    for m in MODEL_CATALOG:
        entry = {**m}

        # Compatibility check
        if vram_mb is not None and vram_mb > 0:
            fits = vram_mb >= m["min_vram_mb"]
            resource = f"{vram_mb // 1024} GB VRAM"
        else:
            fits = ram_gb >= m["min_ram_gb"]
            resource = f"{ram_gb:.0f} GB RAM"

        entry["compatible"] = fits

        if not fits:
            entry["reason"] = (
                f"Benötigt mindestens {m['min_ram_gb']} GB RAM"
                if vram_mb is None
                else f"Benötigt mindestens {m['min_vram_mb'] // 1024} GB VRAM"
            )
        else:
            entry["reason"] = f"Passt zu deiner Hardware ({resource})"

        # Score: prefer best quality that still fits
        if fits:
            score = m["stars"] * 10 + m["size_gb"]
            if score > best_score:
                best_score = score
                best = entry

        models.append(entry)

    # Hardware summary for the UI
    if mode == "cpu":
        hw_summary = f"CPU-Modus · {cpu.get('name', 'Unbekannt')} · {ram_gb:.0f} GB RAM"
        hw_hint = ("Dein System hat keine dedizierte Grafikkarte. "
                   "Die KI läuft über den Prozessor — das funktioniert, "
                   "ist aber langsamer als mit einer GPU.")
    else:
        gpu_name = hw["gpus"][0].get("name", "GPU") if hw.get("gpus") else "GPU"
        if gpu_count > 1:
            hw_summary = (f"{gpu_count}× {gpu_name} · {vram_mb // 1024} GB VRAM gesamt "
                          f"· {ram_gb:.0f} GB RAM")
            hw_hint = (f"Dein System hat {gpu_count} Grafikkarten — die KI verteilt "
                       f"das Modell automatisch über alle GPUs für maximale Leistung.")
        else:
            hw_summary = f"{gpu_name} · {vram_mb // 1024} GB VRAM · {ram_gb:.0f} GB RAM"
            hw_hint = ("Dein System hat eine Grafikkarte — die KI kann diese "
                       "für schnellere Antworten nutzen.")

    # Append custom (user-added) models
    custom_models = get_custom_models()
    for cm in custom_models:
        models.append({
            "id": cm["id"],
            "name": cm["id"],
            "family": "Benutzerdefiniert",
            "params": "—",
            "size_gb": 0,
            "speed": "—",
            "quality": "—",
            "stars": 0,
            "min_ram_gb": 0,
            "min_vram_mb": 0,
            "description": "Manuell hinzugefügtes Modell",
            "best_for": "—",
            "tier": "custom",
            "compatible": True,
            "reason": "Manuell hinzugefügt",
            "custom": True,
        })

    return {
        "hardware": {
            "mode": mode,
            "gpu_count": gpu_count,
            "summary": hw_summary,
            "hint": hw_hint,
            "ram_gb": ram_gb,
            "vram_mb": vram_mb,
        },
        "recommendation": best,
        "models": models,
    }


# ---------------------------------------------------------------------------
# Ollama API helpers
# ---------------------------------------------------------------------------

async def list_installed_models() -> list[dict]:
    """Fetch installed models from Ollama /api/tags."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            if r.status_code == 200:
                data = r.json()
                models = []
                for m in data.get("models", []):
                    models.append({
                        "name": m.get("name", ""),
                        "size_bytes": m.get("size", 0),
                        "size_gb": round(m.get("size", 0) / (1024**3), 1),
                        "modified_at": m.get("modified_at", ""),
                        "family": m.get("details", {}).get("family", ""),
                        "parameter_size": m.get("details", {}).get("parameter_size", ""),
                        "quantization": m.get("details", {}).get("quantization_level", ""),
                    })
                return models
    except Exception:
        pass
    return []


async def pull_model_stream(model: str):
    """
    Yield SSE events while pulling a model from Ollama.
    Each event: {"status": "...", "completed": int, "total": int}
    """
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE}/api/pull",
            json={"name": model},
            timeout=None,
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    yield data
                except json.JSONDecodeError:
                    continue


async def show_model_info(model: str) -> dict:
    """
    Get detailed info for a locally installed model via Ollama /api/show.
    Returns parameters, architecture, context length, quantization, etc.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{OLLAMA_BASE}/api/show",
                json={"name": model},
            )
            if r.status_code == 200:
                data = r.json()
                info = data.get("model_info", {})
                details = data.get("details", {})

                # Extract useful fields
                result = {
                    "status": "ok",
                    "model": model,
                    "family": details.get("family", ""),
                    "parameter_size": details.get("parameter_size", ""),
                    "quantization": details.get("quantization_level", ""),
                    "format": details.get("format", ""),
                }

                # Context length from model_info keys
                for key, val in info.items():
                    if "context_length" in key:
                        result["context_length"] = val
                    elif "embedding_length" in key:
                        result["embedding_length"] = val
                    elif "block_count" in key:
                        result["layers"] = val

                return result
            return {"status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def delete_model(model: str) -> dict:
    """Delete a model from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(
                f"{OLLAMA_BASE}/api/delete",
                json={"name": model},
            )
            if r.status_code == 200:
                return {"status": "ok", "model": model}
            return {"status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ---------------------------------------------------------------------------
# Active model config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load rag-config.json or return defaults."""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(cfg: dict):
    """Save rag-config.json atomically."""
    os.makedirs(CONFIG_PATH, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_FILE)


def get_active_model() -> dict:
    """Return the current active chat model + generation params."""
    cfg = _load_config()
    ollama = cfg.get("ollama", {})
    return {
        "model": os.getenv("CHAT_MODEL", ollama.get("model", "llama3.2:1b")),
        "temperature": float(os.getenv("TEMPERATURE", ollama.get("temperature", 0.7))),
        "top_p": ollama.get("top_p", 0.9),
        "context_window": int(os.getenv("CONTEXT_WINDOW", ollama.get("context_window", 4096))),
        "system_prompt": ollama.get("system_prompt", ""),
    }


def set_active_model(model: str) -> dict:
    """Update the active chat model in config."""
    cfg = _load_config()
    if "ollama" not in cfg:
        cfg["ollama"] = {}
    cfg["ollama"]["model"] = model
    _save_config(cfg)
    # Also update env for current process
    os.environ["CHAT_MODEL"] = model
    return {"status": "ok", "model": model}


def update_generation_params(
    temperature: float | None = None,
    top_p: float | None = None,
    context_window: int | None = None,
    system_prompt: str | None = None,
) -> dict:
    """Update generation parameters in config."""
    cfg = _load_config()
    if "ollama" not in cfg:
        cfg["ollama"] = {}

    if temperature is not None:
        cfg["ollama"]["temperature"] = round(min(max(temperature, 0.0), 2.0), 2)
        os.environ["TEMPERATURE"] = str(cfg["ollama"]["temperature"])
    if top_p is not None:
        cfg["ollama"]["top_p"] = round(min(max(top_p, 0.0), 1.0), 2)
    if context_window is not None:
        cfg["ollama"]["context_window"] = min(max(context_window, 512), 131072)
        os.environ["CONTEXT_WINDOW"] = str(cfg["ollama"]["context_window"])
    if system_prompt is not None:
        cfg["ollama"]["system_prompt"] = system_prompt

    _save_config(cfg)
    return {"status": "ok", **cfg["ollama"]}


# ---------------------------------------------------------------------------
# Custom (manual) models
# ---------------------------------------------------------------------------

def get_custom_models() -> list[dict]:
    """Return the list of user-added custom model IDs."""
    cfg = _load_config()
    return cfg.get("custom_models", [])


def add_custom_model(model_id: str) -> dict:
    """Add a custom Ollama model ID to the config."""
    model_id = model_id.strip()
    if not model_id:
        return {"status": "error", "detail": "Modell-ID darf nicht leer sein"}

    # Check if it's already in the built-in catalog
    for m in MODEL_CATALOG:
        if m["id"] == model_id:
            return {"status": "error", "detail": f"'{model_id}' ist bereits im Katalog vorhanden"}

    cfg = _load_config()
    custom = cfg.get("custom_models", [])

    # Check duplicates
    if any(c["id"] == model_id for c in custom):
        return {"status": "error", "detail": f"'{model_id}' wurde bereits hinzugefügt"}

    custom.append({
        "id": model_id,
        "added_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    })
    cfg["custom_models"] = custom
    _save_config(cfg)

    return {"status": "ok", "model": model_id}


def remove_custom_model(model_id: str) -> dict:
    """Remove a custom model from the config (does NOT delete from Ollama)."""
    cfg = _load_config()
    custom = cfg.get("custom_models", [])
    before = len(custom)
    custom = [c for c in custom if c["id"] != model_id]

    if len(custom) == before:
        return {"status": "error", "detail": "Modell nicht in der Custom-Liste gefunden"}

    cfg["custom_models"] = custom
    _save_config(cfg)
    return {"status": "ok", "model": model_id}
