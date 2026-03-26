# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
Update management: version check, GitHub release comparison,
update log reading, and update/rollback trigger via flag file.
"""

import os
import json
import time
from pathlib import Path
from typing import Any

import httpx

GITHUB_REPO = os.getenv("GITHUB_REPO", "")
APP_VERSION = os.getenv("APP_VERSION", "dev")
LOG_FILE = Path("/data/logs/update.log")
UPDATE_FLAG = Path("/data/.update-flag")

# In-memory cache for GitHub API response (1 hour TTL)
_github_cache: dict = {}
_github_cache_time: float = 0
_CACHE_TTL = 3600


# ---------------------------------------------------------------------------
# Version info
# ---------------------------------------------------------------------------

def get_local_version() -> str:
    """Return the currently running app version."""
    return APP_VERSION


async def check_github_release() -> dict[str, Any]:
    """
    Fetch the latest GitHub release. Cached for 1 hour.
    Returns: {status, latest, changelog, published_at, url}
    """
    global _github_cache, _github_cache_time

    now = time.monotonic()
    if _github_cache and (now - _github_cache_time) < _CACHE_TTL:
        return _github_cache

    if not GITHUB_REPO:
        return {"status": "no_repo", "latest": None, "changelog": "", "url": ""}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if r.status_code == 200:
                data = r.json()
                result = {
                    "status": "ok",
                    "latest": data.get("tag_name", ""),
                    "changelog": data.get("body", ""),
                    "published_at": data.get("published_at", ""),
                    "url": data.get("html_url", ""),
                }
                _github_cache = result
                _github_cache_time = now
                return result
            if r.status_code == 404:
                return {"status": "no_releases", "latest": None, "changelog": "", "url": ""}
            return {"status": "error", "latest": None, "changelog": "",
                    "url": "", "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "latest": None, "changelog": "", "url": "", "error": str(e)}


async def get_update_status() -> dict[str, Any]:
    """Return version info + GitHub update availability."""
    local = get_local_version()
    github = await check_github_release()

    update_available = False
    if github.get("status") == "ok" and github.get("latest"):
        update_available = github["latest"] != local

    return {
        "local_version": local,
        "github_repo": GITHUB_REPO,
        "github": github,
        "update_available": update_available,
    }


# ---------------------------------------------------------------------------
# Update log
# ---------------------------------------------------------------------------

def get_update_log(n: int = 20) -> list[dict]:
    """Return last N entries from update.log (newest first)."""
    if not LOG_FILE.exists():
        return []
    entries = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return list(reversed(entries[-n:]))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Update / Rollback trigger (flag file read by host-side watcher)
# ---------------------------------------------------------------------------

def request_update() -> dict[str, Any]:
    """
    Write 'update' to the flag file. The host-side update-watcher.sh
    picks this up and runs update.sh.
    """
    try:
        UPDATE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_FLAG.write_text("update\n")
        return {"status": "ok", "message": "Update angefordert — wird im Hintergrund ausgeführt"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def request_rollback() -> dict[str, Any]:
    """
    Write 'rollback' to the flag file. The host-side update-watcher.sh
    picks this up and runs update.sh --rollback.
    """
    try:
        UPDATE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_FLAG.write_text("rollback\n")
        return {"status": "ok", "message": "Rollback angefordert — wird im Hintergrund ausgeführt"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def get_flag_status() -> dict[str, Any]:
    """Check if an update/rollback is currently pending."""
    if UPDATE_FLAG.exists():
        flag = UPDATE_FLAG.read_text().strip()
        return {"pending": True, "action": flag}
    return {"pending": False, "action": None}
