"""
GPU detection utility.
Priority: NVIDIA (nvidia-smi) → AMD (rocm-smi / sysfs) → CPU fallback.
Returns a unified dict consumed by the admin API endpoint.
"""

import subprocess
import shutil
import os
import re
from typing import Any


# ---------------------------------------------------------------------------
# Model recommendation table
# ---------------------------------------------------------------------------

def _recommend(vram_mb: int | None, ram_gb: float) -> dict[str, str]:
    """Return the best Ollama model + reason given available VRAM (or RAM)."""
    if vram_mb is not None:
        if vram_mb >= 48_000:
            return {
                "model": "llama3.1:70b-instruct-q5_K_M",
                "reason": f"{vram_mb // 1024} GB VRAM — 70B model (q5)",
            }
        if vram_mb >= 24_000:
            return {
                "model": "mixtral:8x7b-instruct-v0.1-q5_K_M",
                "reason": f"{vram_mb // 1024} GB VRAM — Mixtral 8x7B (q5)",
            }
        if vram_mb >= 12_000:
            return {
                "model": "llama3.1:8b-instruct-q8_0",
                "reason": f"{vram_mb // 1024} GB VRAM — 8B model (q8, full quality)",
            }
        if vram_mb >= 6_000:
            return {
                "model": "llama3.1:8b-instruct-q5_K_M",
                "reason": f"{vram_mb // 1024} GB VRAM — 8B model (q5)",
            }
        if vram_mb >= 4_000:
            return {
                "model": "llama3.1:8b-instruct-q4_K_M",
                "reason": f"{vram_mb // 1024} GB VRAM — 8B model (q4)",
            }
        return {
            "model": "llama3.2:1b",
            "reason": f"{vram_mb // 1024} GB VRAM — very limited, smallest model",
        }

    # CPU path — use available RAM as proxy
    if ram_gb >= 16:
        return {
            "model": "llama3.1:8b-instruct-q4_K_M",
            "reason": f"{ram_gb:.1f} GB RAM (CPU) — 8B model (q4, slow)",
        }
    if ram_gb >= 8:
        return {
            "model": "llama3.2:3b",
            "reason": f"{ram_gb:.1f} GB RAM (CPU) — 3B model",
        }
    return {
        "model": "llama3.2:1b",
        "reason": f"{ram_gb:.1f} GB RAM (CPU) — limited RAM, smallest model",
    }


# ---------------------------------------------------------------------------
# NVIDIA detection
# ---------------------------------------------------------------------------

def _detect_nvidia() -> list[dict[str, Any]] | None:
    """Return list of NVIDIA GPU dicts, or None if nvidia-smi unavailable."""
    if not shutil.which("nvidia-smi"):
        return None

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,"
                "driver_version,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        gpus: list[dict[str, Any]] = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:
                continue
            gpus.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "vram_total_mb": int(parts[2]),
                    "vram_used_mb": int(parts[3]),
                    "vram_free_mb": int(parts[4]),
                    "driver_version": parts[5],
                    "temperature_c": int(parts[6]) if parts[6] != "[N/A]" else None,
                    "utilization_pct": int(parts[7]) if parts[7] != "[N/A]" else None,
                }
            )
        return gpus if gpus else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AMD detection (ROCm or sysfs fallback)
# ---------------------------------------------------------------------------

def _detect_amd() -> list[dict[str, Any]] | None:
    """Return AMD GPU info via rocm-smi or /sys/class/drm, or None."""
    gpus: list[dict[str, Any]] = []

    if shutil.which("rocm-smi"):
        try:
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                for key, val in data.items():
                    if not key.startswith("card"):
                        continue
                    total = int(val.get("VRAM Total Memory (B)", 0)) // (1024 * 1024)
                    used = int(val.get("VRAM Total Used Memory (B)", 0)) // (1024 * 1024)
                    gpus.append(
                        {
                            "index": int(re.sub(r"\D", "", key)),
                            "name": val.get("Card Series", "AMD GPU"),
                            "vram_total_mb": total,
                            "vram_used_mb": used,
                            "vram_free_mb": total - used,
                        }
                    )
                if gpus:
                    return gpus
        except Exception:
            pass

    # sysfs fallback — just detect names, no VRAM info
    drm_path = "/sys/class/drm"
    if os.path.isdir(drm_path):
        seen: set[str] = set()
        idx = 0
        for entry in sorted(os.listdir(drm_path)):
            vendor_path = os.path.join(drm_path, entry, "device", "vendor")
            if not os.path.isfile(vendor_path):
                continue
            try:
                vendor = open(vendor_path).read().strip()
            except OSError:
                continue
            if vendor != "0x1002":  # AMD PCI vendor ID
                continue
            name_path = os.path.join(drm_path, entry, "device", "product_name")
            name = "AMD GPU"
            if os.path.isfile(name_path):
                try:
                    name = open(name_path).read().strip() or name
                except OSError:
                    pass
            key = f"{entry}"
            if key in seen:
                continue
            seen.add(key)
            gpus.append({"index": idx, "name": name, "vram_total_mb": None,
                         "vram_used_mb": None, "vram_free_mb": None})
            idx += 1
        if gpus:
            return gpus

    return None


# ---------------------------------------------------------------------------
# CPU / system info
# ---------------------------------------------------------------------------

def _cpu_info() -> dict[str, Any]:
    try:
        import psutil
        vm = psutil.virtual_memory()
        cpu_name = _cpu_name()
        return {
            "name": cpu_name,
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "ram_total_gb": round(vm.total / 1024**3, 1),
            "ram_available_gb": round(vm.available / 1024**3, 1),
        }
    except ImportError:
        return {"name": _cpu_name(), "ram_total_gb": None, "ram_available_gb": None}


def _cpu_name() -> str:
    # Linux
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    # fallback
    return os.getenv("PROCESSOR_IDENTIFIER", "Unknown CPU")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_gpu_info() -> dict[str, Any]:
    """
    Detect GPU and return unified info dict:
      {
        "mode": "nvidia" | "amd" | "cpu",
        "gpus": [...],          # empty for cpu mode
        "cpu": {...},
        "recommendation": {"model": "...", "reason": "..."},
        "cuda_visible_devices": "..."
      }
    """
    cpu = _cpu_info()
    ram_gb: float = cpu.get("ram_total_gb") or 0.0

    nvidia = _detect_nvidia()
    if nvidia:
        total_vram = sum(g["vram_total_mb"] for g in nvidia)
        # Use GPU with most VRAM for recommendation
        max_vram = max(g["vram_total_mb"] for g in nvidia)
        return {
            "mode": "nvidia",
            "gpus": nvidia,
            "cpu": cpu,
            "recommendation": _recommend(max_vram, ram_gb),
            "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES", "all"),
            "total_vram_mb": total_vram,
        }

    amd = _detect_amd()
    if amd:
        max_vram = max(
            (g["vram_total_mb"] for g in amd if g["vram_total_mb"]),
            default=None,
        )
        return {
            "mode": "amd",
            "gpus": amd,
            "cpu": cpu,
            "recommendation": _recommend(max_vram, ram_gb),
            "note": "AMD GPU detected. Ollama uses CPU unless ROCm is installed.",
        }

    return {
        "mode": "cpu",
        "gpus": [],
        "cpu": cpu,
        "recommendation": _recommend(None, ram_gb),
        "note": "No GPU detected. Running in CPU-only mode.",
    }
