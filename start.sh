#!/usr/bin/env bash
# RAG-Chat — © 2026 David Dülle
# https://duelle.org
#
# Startup-Skript — erkennt GPU bei jedem Start automatisch.
# Wird von systemd aufgerufen statt docker compose direkt.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILES="-f docker-compose.yml"

# GPU-Erkennung bei jedem Start
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    if docker info 2>/dev/null | grep -q "nvidia"; then
        COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
        echo "[RAG-Chat] NVIDIA GPU erkannt — GPU-Modus aktiviert"
    else
        echo "[RAG-Chat] NVIDIA GPU vorhanden, aber Docker-Runtime fehlt — CPU-Modus"
    fi
else
    echo "[RAG-Chat] Keine NVIDIA GPU — CPU-Modus"
fi

ACTION="${1:-up}"

case "$ACTION" in
    up)
        exec docker compose $COMPOSE_FILES up -d
        ;;
    down)
        exec docker compose $COMPOSE_FILES down
        ;;
    restart)
        docker compose $COMPOSE_FILES down
        exec docker compose $COMPOSE_FILES up -d
        ;;
    logs)
        exec docker compose $COMPOSE_FILES logs -f
        ;;
    *)
        exec docker compose $COMPOSE_FILES "$@"
        ;;
esac
