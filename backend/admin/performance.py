# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
Performance metrics: SQLite storage for request stats.
Tracks first-token latency, token/s, request counts per hour.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("/data/logs/performance.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    model             TEXT    NOT NULL DEFAULT '',
    first_token_ms    REAL,
    total_tokens      INTEGER,
    tokens_per_second REAL,
    duration_ms       REAL,
    source_count      INTEGER DEFAULT 0
);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    """Create tables if they don't exist. Called once on startup."""
    with _conn() as c:
        c.executescript(_SCHEMA)


def log_request(
    model: str,
    first_token_ms: float | None,
    total_tokens: int | None,
    tokens_per_second: float | None,
    duration_ms: float | None,
    source_count: int = 0,
) -> None:
    """Persist one completed request. Never raises — errors are swallowed."""
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with _conn() as c:
            c.execute(
                """INSERT INTO requests
                   (timestamp, model, first_token_ms, total_tokens,
                    tokens_per_second, duration_ms, source_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ts, model or "", first_token_ms, total_tokens,
                 tokens_per_second, duration_ms, source_count),
            )
    except Exception:
        pass


def get_summary() -> dict:
    """KPI summary for today and all-time."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT")
    try:
        with _conn() as c:
            row = c.execute(
                """SELECT
                     COUNT(*)                         AS total_today,
                     ROUND(AVG(first_token_ms),  0)   AS avg_first_token_ms,
                     ROUND(AVG(tokens_per_second), 1) AS avg_tps,
                     ROUND(AVG(duration_ms),      0)  AS avg_duration_ms
                   FROM requests WHERE timestamp >= ?""",
                (today,),
            ).fetchone()
            last_hour = c.execute(
                """SELECT COUNT(*) FROM requests
                   WHERE timestamp >= datetime('now', '-1 hour')"""
            ).fetchone()[0]
            total_all = c.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        return {
            "total_today":        row["total_today"]        or 0,
            "total_all":          total_all                 or 0,
            "last_hour":          last_hour                 or 0,
            "avg_first_token_ms": row["avg_first_token_ms"],
            "avg_tps":            row["avg_tps"],
            "avg_duration_ms":    row["avg_duration_ms"],
        }
    except Exception:
        return {"total_today": 0, "total_all": 0, "last_hour": 0,
                "avg_first_token_ms": None, "avg_tps": None, "avg_duration_ms": None}


def get_hourly_stats(hours: int = 24) -> list[dict]:
    """Requests-per-hour and avg tps for the last N hours."""
    try:
        with _conn() as c:
            rows = c.execute(
                """SELECT
                     strftime('%Y-%m-%dT%H:00:00Z', timestamp) AS hour,
                     COUNT(*)                                   AS requests,
                     ROUND(AVG(tokens_per_second), 1)           AS avg_tps,
                     ROUND(AVG(first_token_ms),    0)           AS avg_latency_ms
                   FROM requests
                   WHERE timestamp >= datetime('now', ?)
                   GROUP BY hour ORDER BY hour ASC""",
                (f"-{hours} hours",),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_recent_requests(n: int = 20) -> list[dict]:
    """Last N completed requests, newest first."""
    try:
        with _conn() as c:
            rows = c.execute(
                """SELECT timestamp, model, first_token_ms, tokens_per_second,
                          duration_ms, source_count
                   FROM requests ORDER BY id DESC LIMIT ?""",
                (n,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
