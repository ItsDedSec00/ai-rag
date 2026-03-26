# RAG-Chat — © 2026 David Dülle
# https://duelle.org

"""
Admin password management via nginx htpasswd file.
"""

import os
import logging

logger = logging.getLogger(__name__)

HTPASSWD_PATH = os.getenv("HTPASSWD_PATH", "/data/nginx/htpasswd")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")


def change_password(current_password: str, new_password: str) -> dict:
    """
    Verify current password and replace it with new_password in the htpasswd file.
    Raises PermissionError if current password is wrong.
    """
    from passlib.apache import HtpasswdFile

    if not os.path.exists(HTPASSWD_PATH):
        raise FileNotFoundError(f"htpasswd-Datei nicht gefunden: {HTPASSWD_PATH}")

    ht = HtpasswdFile(HTPASSWD_PATH)

    if not ht.check_password(ADMIN_USER, current_password):
        raise PermissionError("Aktuelles Passwort ist falsch")

    ht.set_password(ADMIN_USER, new_password)
    ht.save()

    logger.info("Admin password changed for user '%s'", ADMIN_USER)
    return {"status": "ok"}
