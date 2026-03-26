#!/bin/sh
# RAG-Chat — © 2026 David Dülle
# https://duelle.org
#
# Generiert /etc/nginx/htpasswd beim ersten Start aus Umgebungsvariablen.
# Behebt auch den Windows-Docker-Desktop-Bug (Verzeichnis statt Datei).

HTPASSWD="/etc/nginx/htpasswd"

# Windows-Fix: Docker Desktop legt manchmal ein Verzeichnis statt einer Datei an
if [ -d "$HTPASSWD" ]; then
    rm -rf "$HTPASSWD"
    echo "[nginx] htpasswd-Verzeichnis entfernt (Windows-Docker-Fix)"
fi

# Datei anlegen falls nicht vorhanden
if [ ! -f "$HTPASSWD" ]; then
    USER="${ADMIN_USER:-admin}"
    PASS="${ADMIN_PASSWORD:-admin}"
    htpasswd -bc "$HTPASSWD" "$USER" "$PASS"
    echo "[nginx] htpasswd erstellt — Benutzer: $USER"
    if [ "$PASS" = "admin" ]; then
        echo "[nginx] WARNUNG: Standard-Passwort aktiv! Im Admin-Panel ändern."
    fi
fi
