# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
API Key authentication for the OpenAI-compatible endpoint.

Keys are stored as SHA-256 hashes in the config (api.keys[]).
The plaintext key is shown exactly once on creation and never stored.

Format: rck-<32 hex chars>  (128 bits of entropy)
"""

import hashlib
import secrets

from fastapi import Header, HTTPException, status

import config as cfg

KEY_PREFIX = "rck-"


def generate_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns:
        (plaintext_key, sha256_hex_hash)
    """
    raw = secrets.token_hex(16)          # 32 hex chars = 128 bits
    key = f"{KEY_PREFIX}{raw}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return key, digest


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def require_api_key(
    authorization: str | None = Header(default=None),
) -> dict:
    """FastAPI Depends() — validates Bearer token against stored hashes.

    Returns the matching key record on success.
    Raises 403 if the API is disabled, 401 if the key is missing or invalid.
    """
    if not cfg.api_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API access is disabled",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            detail="Missing or invalid Authorization header. "
                   "Use: Authorization: Bearer rck-<key>",
        )

    token = authorization[7:]
    token_hash = _hash(token)

    for record in cfg.api_keys():
        if secrets.compare_digest(record.get("hash", ""), token_hash):
            cfg.api_touch_key(record["id"])
            return record

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
        detail="Invalid API key",
    )
