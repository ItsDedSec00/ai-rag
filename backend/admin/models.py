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

import config as cfg
from utils.gpu import get_gpu_info

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"


# ---------------------------------------------------------------------------
# Layperson-friendly model catalog
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Model families — each family has a description + ordered list of sizes
# ---------------------------------------------------------------------------

MODEL_FAMILIES = [
    {
        "key": "llama3.2",
        "name": "Llama 3.2",
        "vendor": "Meta",
        "description": "Bewährtes Allround-Modell von Meta. Solide Qualität, "
                       "schnelle Antworten, gutes Deutsch.",
        "supports_thinking": False,
        "sizes": [
            {"id": "llama3.2:1b", "label": "1B", "size_gb": 0.7,
             "min_ram_gb": 4, "min_vram_mb": 0},
            {"id": "llama3.2:3b", "label": "3B", "size_gb": 2.0,
             "min_ram_gb": 6, "min_vram_mb": 2_000},
        ],
    },
    {
        "key": "qwen3.5",
        "name": "Qwen 3.5",
        "vendor": "Alibaba",
        "description": "Aktuelles Top-Modell mit hervorragendem Deutsch und Reasoning. "
                       "Unterstützt Thinking-Modus für komplexe Fragen.",
        "supports_thinking": True,
        "sizes": [
            {"id": "qwen3.5:0.8b", "label": "0.8B", "size_gb": 0.5,
             "min_ram_gb": 4, "min_vram_mb": 0},
            {"id": "qwen3.5:2b", "label": "2B", "size_gb": 1.5,
             "min_ram_gb": 4, "min_vram_mb": 1_500},
            {"id": "qwen3.5:4b", "label": "4B", "size_gb": 2.7,
             "min_ram_gb": 6, "min_vram_mb": 3_000},
            {"id": "qwen3.5:9b", "label": "9B", "size_gb": 5.5,
             "min_ram_gb": 10, "min_vram_mb": 6_000},
            {"id": "qwen3.5:27b", "label": "27B", "size_gb": 16.0,
             "min_ram_gb": 24, "min_vram_mb": 16_000},
            {"id": "qwen3.5:35b", "label": "35B", "size_gb": 21.0,
             "min_ram_gb": 32, "min_vram_mb": 22_000},
            {"id": "qwen3.5:122b", "label": "122B", "size_gb": 72.0,
             "min_ram_gb": 96, "min_vram_mb": 80_000},
        ],
    },
    {
        "key": "deepseek-r1",
        "name": "DeepSeek-R1",
        "vendor": "DeepSeek",
        "description": "Reasoning-Modell: denkt Schritt für Schritt nach. "
                       "Besonders gut bei Fachtexten und komplexen Zusammenhängen.",
        "supports_thinking": True,
        "sizes": [
            {"id": "deepseek-r1:1.5b", "label": "1.5B", "size_gb": 1.0,
             "min_ram_gb": 4, "min_vram_mb": 0},
            {"id": "deepseek-r1:7b", "label": "7B", "size_gb": 4.7,
             "min_ram_gb": 8, "min_vram_mb": 4_000},
            {"id": "deepseek-r1:8b", "label": "8B", "size_gb": 5.0,
             "min_ram_gb": 10, "min_vram_mb": 5_000},
            {"id": "deepseek-r1:14b", "label": "14B", "size_gb": 9.0,
             "min_ram_gb": 16, "min_vram_mb": 8_000},
            {"id": "deepseek-r1:32b", "label": "32B", "size_gb": 20.0,
             "min_ram_gb": 32, "min_vram_mb": 20_000},
            {"id": "deepseek-r1:70b", "label": "70B", "size_gb": 43.0,
             "min_ram_gb": 64, "min_vram_mb": 48_000},
        ],
    },
    {
        "key": "gpt-oss",
        "name": "GPT-OSS",
        "vendor": "OpenAI",
        "description": "OpenAIs Open-Source-Modell. Mixture-of-Experts — "
                       "schnell trotz großer Gesamtgröße.",
        "supports_thinking": False,
        "sizes": [
            {"id": "gpt-oss:20b", "label": "20B", "size_gb": 14.0,
             "min_ram_gb": 16, "min_vram_mb": 8_000},
            {"id": "gpt-oss:120b", "label": "120B", "size_gb": 65.0,
             "min_ram_gb": 80, "min_vram_mb": 80_000},
        ],
    },
]

# Flat catalog for backwards-compat (used by custom model check)
MODEL_CATALOG = []
for _fam in MODEL_FAMILIES:
    for _sz in _fam["sizes"]:
        MODEL_CATALOG.append({"id": _sz["id"], "family": _fam["key"]})


# ---------------------------------------------------------------------------
# Hardware-aware recommendation
# ---------------------------------------------------------------------------

def _fits_hardware(size: dict, vram_mb: int | None, ram_gb: float) -> bool:
    """Check if a model size fits the available hardware."""
    if vram_mb is not None and vram_mb > 0:
        return vram_mb >= size["min_vram_mb"]
    return ram_gb >= size["min_ram_gb"]


def get_recommendations() -> dict[str, Any]:
    """
    Return model families with per-size compatibility and
    a recommended size per family based on available hardware.
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

    resource_str = (f"{vram_mb // 1024} GB VRAM" if vram_mb and vram_mb > 0
                    else f"{ram_gb:.0f} GB RAM")

    # Build family data with compatibility per size
    families = []
    for fam in MODEL_FAMILIES:
        sizes = []
        recommended_idx = -1
        for i, sz in enumerate(fam["sizes"]):
            fits = _fits_hardware(sz, vram_mb, ram_gb)
            sizes.append({**sz, "compatible": fits})
            if fits:
                recommended_idx = i  # last fitting = largest that fits

        families.append({
            "key": fam["key"],
            "name": fam["name"],
            "vendor": fam["vendor"],
            "description": fam["description"],
            "supports_thinking": fam["supports_thinking"],
            "sizes": sizes,
            "recommended_idx": recommended_idx,  # -1 = none fit
        })

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

    # Custom models
    custom_models = get_custom_models()

    return {
        "hardware": {
            "mode": mode,
            "gpu_count": gpu_count,
            "summary": hw_summary,
            "hint": hw_hint,
            "ram_gb": ram_gb,
            "vram_mb": vram_mb,
            "resource": resource_str,
        },
        "families": families,
        "custom_models": [cm["id"] for cm in custom_models],
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
# Active model config (delegates to central config module)
# ---------------------------------------------------------------------------

def get_active_model() -> dict:
    """Return the current active chat model + generation params."""
    return {
        "model": cfg.ollama_model(),
        "temperature": cfg.ollama_temperature(),
        "top_p": cfg.ollama_top_p(),
        "context_window": cfg.ollama_context_window(),
        "system_prompt": cfg.ollama_system_prompt(),
        "max_tokens": cfg.ollama_max_tokens(),
        "repeat_penalty": cfg.ollama_repeat_penalty(),
        "response_language": cfg.ollama_response_language(),
        "thinking_mode": cfg.ollama_thinking_mode(),
    }


def set_active_model(model: str) -> dict:
    """Update the active chat model in config."""
    cfg.set_value("ollama", "model", model)
    return {"status": "ok", "model": model}


def update_generation_params(
    temperature: float | None = None,
    top_p: float | None = None,
    context_window: int | None = None,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
    repeat_penalty: float | None = None,
    response_language: str | None = None,
    thinking_mode: bool | None = None,
) -> dict:
    """Update generation parameters in config."""
    updates = {}
    if temperature is not None:
        updates["temperature"] = round(min(max(temperature, 0.0), 2.0), 2)
    if top_p is not None:
        updates["top_p"] = round(min(max(top_p, 0.0), 1.0), 2)
    if context_window is not None:
        updates["context_window"] = min(max(context_window, 512), 131072)
    if system_prompt is not None:
        updates["system_prompt"] = system_prompt
    if max_tokens is not None:
        updates["max_tokens"] = min(max(max_tokens, 64), 32768)
    if repeat_penalty is not None:
        updates["repeat_penalty"] = round(min(max(repeat_penalty, 1.0), 2.0), 2)
    if response_language is not None:
        updates["response_language"] = response_language
    if thinking_mode is not None:
        updates["thinking_mode"] = bool(thinking_mode)

    if updates:
        cfg.update_section("ollama", updates)

    return {"status": "ok", **cfg.get().get("ollama", {})}


# ---------------------------------------------------------------------------
# Custom (manual) models
# ---------------------------------------------------------------------------

def get_custom_models() -> list[dict]:
    """Return the list of user-added custom model IDs."""
    return cfg.get().get("custom_models", [])


def add_custom_model(model_id: str) -> dict:
    """Add a custom Ollama model ID to the config."""
    from datetime import datetime, timezone

    model_id = model_id.strip()
    if not model_id:
        return {"status": "error", "detail": "Modell-ID darf nicht leer sein"}

    # Check if it's already in the built-in catalog
    for m in MODEL_CATALOG:
        if m["id"] == model_id:
            return {"status": "error", "detail": f"'{model_id}' ist bereits im Katalog vorhanden"}

    full = cfg.get()
    custom = full.get("custom_models", [])

    # Check duplicates
    if any(c["id"] == model_id for c in custom):
        return {"status": "error", "detail": f"'{model_id}' wurde bereits hinzugefügt"}

    custom.append({
        "id": model_id,
        "added_at": datetime.now(timezone.utc).isoformat(),
    })
    full["custom_models"] = custom
    cfg.replace_all(full)

    return {"status": "ok", "model": model_id}


def remove_custom_model(model_id: str) -> dict:
    """Remove a custom model from the config (does NOT delete from Ollama)."""
    full = cfg.get()
    custom = full.get("custom_models", [])
    before = len(custom)
    custom = [c for c in custom if c["id"] != model_id]

    if len(custom) == before:
        return {"status": "error", "detail": "Modell nicht in der Custom-Liste gefunden"}

    full["custom_models"] = custom
    cfg.replace_all(full)
    return {"status": "ok", "model": model_id}
