# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
Central configuration — single source of truth.
-------------------------------------------------
Priority: rag-config.json > environment variables > hardcoded defaults.

On startup the saved config file is loaded.  Admin API changes are
written to the file *and* update the in-memory state so they take
effect immediately and survive container restarts.

Snapshots are timestamped copies stored alongside the main file.
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_PATH = os.getenv("CONFIG_PATH", "/data/config")

DEFAULT_SYSTEM_PROMPT = (
    "Du bist ein hilfreicher KI-Assistent. "
    "Du kannst allgemeine Fragen frei beantworten und hast zusätzlich "
    "Zugriff auf eine Wissensdatenbank mit Dokumenten.\n\n"
    "Halte dich an folgende Regeln:\n"
    "- Wenn im Kontext relevante Dokumente bereitgestellt werden UND die Frage "
    "sich auf diese Dokumente bezieht, nutze sie für deine Antwort.\n"
    "- Wenn der Kontext nicht zur Frage passt, ignoriere ihn und antworte "
    "frei aus deinem eigenen Wissen.\n"
    "- Bei allgemeinen Fragen, Smalltalk oder Begrüßungen antworte natürlich "
    "und freundlich — ohne die Dokumente zu erwähnen.\n"
    "- Antworte in der Sprache, in der du gefragt wirst.\n"
    "- Formuliere Antworten klar und verständlich – auch für Personen ohne Fachkenntnisse.\n"
    "- Erfinde keine Fakten. Wenn du etwas nicht weißt, sage es ehrlich."
)
CONFIG_FILE = os.path.join(CONFIG_PATH, "rag-config.json")
SNAPSHOT_DIR = os.path.join(CONFIG_PATH, "snapshots")

# ──────────────────────────────────────────────────────────────────────
# Default values (used when neither file nor env var provides a value)
# ──────────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "ollama": {
        "model": "llama3.2:1b",
        "temperature": 0.7,
        "top_p": 0.9,
        "context_window": 4096,
        "max_tokens": 2048,
        "repeat_penalty": 1.1,
        "response_language": "auto",
        "thinking_mode": False,
        "keep_alive": "5m",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
    },
    "rag": {
        "embedding_model": "nomic-embed-text",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "top_k": 5,
        "min_score": 0.3,
        "display_sources": 5,
        "supported_formats": ["pdf", "docx", "txt", "md", "csv"],
        "reindex_on_change": True,
    },
    "server": {
        "max_upload_mb": 10,
        "session_timeout_min": 30,
        "log_level": "INFO",
        "indexer_interval_sec": 5,
    },
    "chat": {
        "welcome_message": "Willkommen bei {app_name}! Stelle eine Frage zu deinen Dokumenten.",
        "placeholder": "Nachricht eingeben…",
        "history_limit": 50,
        "markdown_enabled": True,
    },
    "branding": {
        "app_name": "RAG-Chat",
        "logo_url": "",
        "primary_color": "#3b82f6",
    },
    "custom_models": [],
    "api": {
        "enabled": True,
        "rag_enabled": True,   # if False, bypasses ChromaDB and goes directly to Ollama
        "keys": [],            # list of {id, name, hash, created_at, last_used}
    },
}

# Map env-var names → config paths for initial seeding
_ENV_MAP: dict[str, tuple[str, str, type]] = {
    "CHAT_MODEL":          ("ollama", "model", str),
    "TEMPERATURE":         ("ollama", "temperature", float),
    "TOP_P":               ("ollama", "top_p", float),
    "CONTEXT_WINDOW":      ("ollama", "context_window", int),
    "SYSTEM_PROMPT":       ("ollama", "system_prompt", str),
    "EMBEDDING_MODEL":     ("rag", "embedding_model", str),
    "CHUNK_SIZE":          ("rag", "chunk_size", int),
    "CHUNK_OVERLAP":       ("rag", "chunk_overlap", int),
    "RAG_TOP_K":           ("rag", "top_k", int),
    "MAX_UPLOAD_MB":       ("server", "max_upload_mb", int),
    "SESSION_TIMEOUT_MIN": ("server", "session_timeout_min", int),
}


# ──────────────────────────────────────────────────────────────────────
# In-memory state (loaded once, updated by setters)
# ──────────────────────────────────────────────────────────────────────

_cfg: dict[str, Any] = {}
_loaded = False


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (in-place)."""
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load() -> dict[str, Any]:
    """Load config: saved file (if exists), else defaults + env vars.

    Priority on first install:  defaults ← env vars → saved to file.
    Priority on restart:        defaults ← saved file (env vars ignored).

    This ensures the saved config is always the single source of truth
    after initial setup.  Env vars only seed the very first config file.
    """
    global _cfg, _loaded

    import copy
    _cfg = copy.deepcopy(_DEFAULTS)

    if os.path.exists(CONFIG_FILE):
        # ── Existing install: saved file is the sole authority ──
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            _deep_merge(_cfg, saved)
            logger.info("Config loaded from %s", CONFIG_FILE)
        except Exception as e:
            logger.warning("Could not load config file: %s", e)
    else:
        # ── First install: seed from env vars, then persist ──
        for env_key, (section, key, typ) in _ENV_MAP.items():
            val = os.environ.get(env_key)
            if val is not None:
                try:
                    _cfg.setdefault(section, {})[key] = typ(val)
                except (ValueError, TypeError):
                    pass
        logger.info("No config file found — creating from defaults + env vars")
        save()

    _loaded = True
    return _cfg


def save() -> None:
    """Persist current config to disk (atomic write)."""
    os.makedirs(CONFIG_PATH, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_FILE)
        logger.debug("Config saved to %s", CONFIG_FILE)
    except Exception as e:
        logger.error("Failed to save config: %s", e)


def get() -> dict[str, Any]:
    """Return the full config dict (read-only copy)."""
    if not _loaded:
        load()
    import copy
    return copy.deepcopy(_cfg)


# ──────────────────────────────────────────────────────────────────────
# Typed getters for hot-path reads (no copy overhead)
# ──────────────────────────────────────────────────────────────────────

def ollama_model() -> str:
    if not _loaded: load()
    return _cfg.get("ollama", {}).get("model", "llama3.2:1b")

def ollama_temperature() -> float:
    if not _loaded: load()
    return float(_cfg.get("ollama", {}).get("temperature", 0.7))

def ollama_top_p() -> float:
    if not _loaded: load()
    return float(_cfg.get("ollama", {}).get("top_p", 0.9))

def ollama_context_window() -> int:
    if not _loaded: load()
    return int(_cfg.get("ollama", {}).get("context_window", 4096))

def ollama_system_prompt() -> str:
    if not _loaded: load()
    return _cfg.get("ollama", {}).get("system_prompt", "")

def rag_top_k() -> int:
    if not _loaded: load()
    return int(_cfg.get("rag", {}).get("top_k", 5))

def rag_embedding_model() -> str:
    if not _loaded: load()
    return _cfg.get("rag", {}).get("embedding_model", "nomic-embed-text")

def rag_chunk_size() -> int:
    if not _loaded: load()
    return int(_cfg.get("rag", {}).get("chunk_size", 1000))

def rag_chunk_overlap() -> int:
    if not _loaded: load()
    return int(_cfg.get("rag", {}).get("chunk_overlap", 200))

def ollama_max_tokens() -> int:
    if not _loaded: load()
    return int(_cfg.get("ollama", {}).get("max_tokens", 2048))

def ollama_repeat_penalty() -> float:
    if not _loaded: load()
    return float(_cfg.get("ollama", {}).get("repeat_penalty", 1.1))

def ollama_response_language() -> str:
    if not _loaded: load()
    return _cfg.get("ollama", {}).get("response_language", "auto")

def ollama_thinking_mode() -> bool:
    if not _loaded: load()
    return _cfg.get("ollama", {}).get("thinking_mode", False)

def ollama_keep_alive() -> str:
    if not _loaded: load()
    return str(_cfg.get("ollama", {}).get("keep_alive", "5m"))

def rag_min_score() -> float:
    if not _loaded: load()
    return float(_cfg.get("rag", {}).get("min_score", 0.3))

def rag_display_sources() -> int:
    if not _loaded: load()
    return int(_cfg.get("rag", {}).get("display_sources", 5))

def rag_supported_formats() -> list[str]:
    if not _loaded: load()
    return _cfg.get("rag", {}).get("supported_formats", ["pdf", "docx", "txt", "md", "csv"])

def rag_reindex_on_change() -> bool:
    if not _loaded: load()
    return bool(_cfg.get("rag", {}).get("reindex_on_change", True))

def server_max_upload_mb() -> int:
    if not _loaded: load()
    return int(_cfg.get("server", {}).get("max_upload_mb", 10))

def server_session_timeout_min() -> int:
    if not _loaded: load()
    return int(_cfg.get("server", {}).get("session_timeout_min", 30))

def server_log_level() -> str:
    if not _loaded: load()
    return _cfg.get("server", {}).get("log_level", "INFO")

def server_indexer_interval() -> int:
    if not _loaded: load()
    return int(_cfg.get("server", {}).get("indexer_interval_sec", 5))

def chat_welcome() -> str:
    if not _loaded: load()
    msg = _cfg.get("chat", {}).get("welcome_message", "")
    name = _cfg.get("branding", {}).get("app_name", "RAG-Chat")
    return msg.replace("{app_name}", name)

def chat_placeholder() -> str:
    if not _loaded: load()
    return _cfg.get("chat", {}).get("placeholder", "Nachricht eingeben…")

def chat_history_limit() -> int:
    if not _loaded: load()
    return int(_cfg.get("chat", {}).get("history_limit", 50))

def chat_markdown_enabled() -> bool:
    if not _loaded: load()
    return bool(_cfg.get("chat", {}).get("markdown_enabled", True))

def branding_app_name() -> str:
    if not _loaded: load()
    return _cfg.get("branding", {}).get("app_name", "RAG-Chat")

def branding_logo_url() -> str:
    if not _loaded: load()
    return _cfg.get("branding", {}).get("logo_url", "")

def branding_primary_color() -> str:
    if not _loaded: load()
    return _cfg.get("branding", {}).get("primary_color", "#3b82f6")


# ──────────────────────────────────────────────────────────────────────
# Setters (update in-memory + persist)
# ──────────────────────────────────────────────────────────────────────

def set_value(section: str, key: str, value: Any) -> None:
    """Set a single config value, save, and return."""
    if not _loaded: load()
    _cfg.setdefault(section, {})[key] = value
    save()


def update_section(section: str, values: dict[str, Any]) -> None:
    """Merge values into a section."""
    if not _loaded: load()
    _cfg.setdefault(section, {})
    _cfg[section].update(values)
    save()


def replace_all(new_cfg: dict[str, Any]) -> None:
    """Replace the entire config (e.g. import). Validates structure."""
    global _cfg
    if not isinstance(new_cfg, dict):
        raise ValueError("Config must be a JSON object")
    # Merge onto defaults so required keys are never missing
    import copy
    merged = copy.deepcopy(_DEFAULTS)
    _deep_merge(merged, new_cfg)
    _cfg = merged
    save()


# ──────────────────────────────────────────────────────────────────────
# Snapshots
# ──────────────────────────────────────────────────────────────────────

def create_snapshot(label: str = "") -> dict[str, str]:
    """Copy current config file into snapshots/ with timestamp."""
    if not _loaded: load()
    save()  # make sure file is up-to-date
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap_name = f"{ts}_{label}" if label else ts
    snap_path = os.path.join(SNAPSHOT_DIR, f"{snap_name}.json")
    shutil.copy2(CONFIG_FILE, snap_path)
    logger.info("Snapshot created: %s", snap_name)
    return {"id": snap_name, "path": snap_path}


def list_snapshots() -> list[dict[str, Any]]:
    """Return available snapshots sorted newest-first."""
    if not os.path.isdir(SNAPSHOT_DIR):
        return []
    snaps = []
    for f in sorted(Path(SNAPSHOT_DIR).glob("*.json"), reverse=True):
        stat = f.stat()
        snaps.append({
            "id": f.stem,
            "filename": f.name,
            "size_bytes": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return snaps


def restore_snapshot(snap_id: str) -> dict[str, str]:
    """Restore a snapshot, creating a backup of current config first."""
    snap_path = os.path.join(SNAPSHOT_DIR, f"{snap_id}.json")
    if not os.path.exists(snap_path):
        raise FileNotFoundError(f"Snapshot '{snap_id}' nicht gefunden")

    # Backup current config before overwriting
    create_snapshot(label="pre_restore")

    # Read and apply snapshot
    with open(snap_path, "r", encoding="utf-8") as f:
        snap_cfg = json.load(f)
    replace_all(snap_cfg)
    logger.info("Restored snapshot: %s", snap_id)
    return {"status": "ok", "restored": snap_id}


def delete_snapshot(snap_id: str) -> dict[str, str]:
    """Delete a snapshot file."""
    snap_path = os.path.join(SNAPSHOT_DIR, f"{snap_id}.json")
    if not os.path.exists(snap_path):
        raise FileNotFoundError(f"Snapshot '{snap_id}' nicht gefunden")
    os.unlink(snap_path)
    return {"status": "ok", "deleted": snap_id}


# ──────────────────────────────────────────────────────────────────────
# API / OpenAI-compat layer
# ──────────────────────────────────────────────────────────────────────

def api_enabled() -> bool:
    if not _loaded: load()
    return bool(_cfg.get("api", {}).get("enabled", True))

def api_rag_enabled() -> bool:
    if not _loaded: load()
    return bool(_cfg.get("api", {}).get("rag_enabled", True))

def api_keys() -> list[dict]:
    if not _loaded: load()
    return list(_cfg.get("api", {}).get("keys", []))


# Key last-used debounce: avoid disk I/O on every request
_key_touch_cache: dict[str, float] = {}

def api_add_key(record: dict) -> None:
    """Append a new API key record and persist."""
    if not _loaded: load()
    _cfg.setdefault("api", {}).setdefault("keys", []).append(record)
    save()

def api_remove_key(key_id: str) -> None:
    """Remove an API key by ID. Raises KeyError if not found."""
    if not _loaded: load()
    keys = _cfg.setdefault("api", {}).get("keys", [])
    new_keys = [k for k in keys if k.get("id") != key_id]
    if len(new_keys) == len(keys):
        raise KeyError(f"API key '{key_id}' not found")
    _cfg["api"]["keys"] = new_keys
    _key_touch_cache.pop(key_id, None)
    save()

def api_touch_key(key_id: str) -> None:
    """Update last_used timestamp (debounced — max one write per 60s per key)."""
    import time as _time
    now = _time.monotonic()
    if now - _key_touch_cache.get(key_id, 0.0) < 60.0:
        return
    _key_touch_cache[key_id] = now
    if not _loaded: load()
    ts = datetime.now(timezone.utc).isoformat()
    for key in _cfg.get("api", {}).get("keys", []):
        if key.get("id") == key_id:
            key["last_used"] = ts
            break
    save()
