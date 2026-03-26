# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
System metrics: CPU, RAM, disk, uptime, request counters.
"""

import os
import sqlite3
import time
import platform
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import psutil
import config as cfg

from utils.gpu import get_gpu_info

_PERF_DB = Path("/data/logs/performance.db")


# ---------------------------------------------------------------------------
# Request counter (thread-safe, seeded from persistent SQLite on startup)
# ---------------------------------------------------------------------------

class RequestCounter:
    """In-memory counter seeded from performance.db so counts survive restarts."""

    def __init__(self):
        self._lock = Lock()
        self._total = 0
        self._hourly: dict[str, int] = {}   # "YYYY-MM-DD-HH" → count
        self._daily: dict[str, int] = {}    # "YYYY-MM-DD" → count
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._load_from_db()

    def _load_from_db(self) -> None:
        """Seed counters from persisted performance.db (best-effort)."""
        try:
            if not _PERF_DB.exists():
                return
            with sqlite3.connect(str(_PERF_DB)) as c:
                self._total = c.execute("SELECT COUNT(*) FROM requests").fetchone()[0] or 0
                rows = c.execute(
                    """SELECT strftime('%Y-%m-%d-%H', timestamp) AS h, COUNT(*) AS n
                       FROM requests GROUP BY h"""
                ).fetchall()
                for h, n in rows:
                    self._hourly[h] = n
                    day = h[:10]  # "YYYY-MM-DD"
                    self._daily[day] = self._daily.get(day, 0) + n
        except Exception:
            pass  # non-fatal — start from 0 if DB not readable

    def increment(self):
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%d-%H")
        day_key = now.strftime("%Y-%m-%d")

        with self._lock:
            self._total += 1
            self._hourly[hour_key] = self._hourly.get(hour_key, 0) + 1
            self._daily[day_key] = self._daily.get(day_key, 0) + 1

            # Trim old entries (keep last 48 hours, last 60 days)
            if len(self._hourly) > 48:
                oldest = sorted(self._hourly.keys())[:-48]
                for k in oldest:
                    del self._hourly[k]
            if len(self._daily) > 60:
                oldest = sorted(self._daily.keys())[:-60]
                for k in oldest:
                    del self._daily[k]

    def stats(self) -> dict:
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%d-%H")
        day_key = now.strftime("%Y-%m-%d")

        with self._lock:
            return {
                "total": self._total,
                "today": self._daily.get(day_key, 0),
                "this_hour": self._hourly.get(hour_key, 0),
                "since": self._started_at,
            }


# Global singleton
request_counter = RequestCounter()


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------

_process_start = time.time()        # Container/process start time
_boot_time = psutil.boot_time()     # Host system boot time


def get_system_info() -> dict:
    """Collect system metrics for the admin dashboard."""

    now = time.time()

    # CPU
    cpu_pct = psutil.cpu_percent(interval=0.3)
    cpu_count = psutil.cpu_count(logical=True)
    cpu_freq = psutil.cpu_freq()

    # RAM
    mem = psutil.virtual_memory()

    # Disk (/data if available, else /)
    disk_path = "/data" if os.path.exists("/data") else "/"
    disk = psutil.disk_usage(disk_path)

    # GPU (cached call)
    gpu = get_gpu_info()

    # Ollama model from config
    chat_model = cfg.ollama_model()
    embedding_model = cfg.rag_embedding_model()

    return {
        "hostname": platform.node(),
        "platform": f"{platform.system()} {platform.release()}",
        "container_uptime_seconds": int(now - _process_start),
        "system_uptime_seconds": int(now - _boot_time),
        "cpu": {
            "cores": cpu_count,
            "frequency_mhz": int(cpu_freq.current) if cpu_freq else None,
            "usage_pct": cpu_pct,
        },
        "ram": {
            "total_gb": round(mem.total / (1024**3), 1),
            "used_gb": round(mem.used / (1024**3), 1),
            "available_gb": round(mem.available / (1024**3), 1),
            "usage_pct": mem.percent,
        },
        "disk": {
            "path": disk_path,
            "total_gb": round(disk.total / (1024**3), 1),
            "used_gb": round(disk.used / (1024**3), 1),
            "free_gb": round(disk.free / (1024**3), 1),
            "usage_pct": round(disk.percent, 1),
        },
        "gpu": gpu,
        "models": {
            "chat": chat_model,
            "embedding": embedding_model,
        },
        "requests": request_counter.stats(),
    }
