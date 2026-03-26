#!/usr/bin/env bash
# RAG-Chat — © 2026 David Dülle
# https://duelle.org
#
# Deinstallation von RAG-Chat

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e " ${GREEN}✔${NC} $*"; }
warn() { echo -e " ${YELLOW}⚠${NC} $*"; }
err()  { echo -e " ${RED}✘${NC} $*"; }
info() { echo -e " ${CYAN}ℹ${NC} $*"; }

INSTALL_DIR="/opt/rag-chat"
REMOVE_DATA=false
REMOVE_IMAGES=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)          INSTALL_DIR="$2"; shift 2 ;;
        --remove-data)  REMOVE_DATA=true; shift ;;
        --remove-images) REMOVE_IMAGES=true; shift ;;
        --all)          REMOVE_DATA=true; REMOVE_IMAGES=true; shift ;;
        --help|-h)
            echo "RAG-Chat Uninstaller"
            echo ""
            echo "Usage: bash uninstall.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dir PATH        Installationsverzeichnis (default: /opt/rag-chat)"
            echo "  --remove-data     Docker-Volumes löschen (Wissensbasis, Config, etc.)"
            echo "  --remove-images   Docker-Images entfernen"
            echo "  --all             Alles entfernen (Daten + Images)"
            echo "  --help            Diese Hilfe anzeigen"
            exit 0
            ;;
        *) err "Unbekanntes Argument: $1"; exit 1 ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    err "Bitte als root ausführen: sudo bash uninstall.sh"
    exit 1
fi

echo ""
echo -e "${BOLD}${RED}  RAG-Chat Deinstallation${NC}"
echo ""

# Bestätigung
read -rp "  RAG-Chat wirklich deinstallieren? [j/N] " answer
if [[ "${answer,,}" != "j" && "${answer,,}" != "y" ]]; then
    info "Abgebrochen."
    exit 0
fi

# ── Container stoppen ───────────────────────────────────────────────
echo ""
info "Stoppe Container..."
if [[ -f "$INSTALL_DIR/docker-compose.yml" ]]; then
    cd "$INSTALL_DIR"
    docker compose down 2>/dev/null || true
    ok "Container gestoppt"
else
    warn "docker-compose.yml nicht gefunden in $INSTALL_DIR"
fi

# ── systemd entfernen ──────────────────────────────────────────────
info "Entferne systemd-Services..."
systemctl disable --now rag-chat.service 2>/dev/null || true
systemctl disable --now rag-chat-update.timer 2>/dev/null || true
rm -f /etc/systemd/system/rag-chat.service
rm -f /etc/systemd/system/rag-chat-update.service
rm -f /etc/systemd/system/rag-chat-update.timer
systemctl daemon-reload
ok "systemd-Services entfernt"

# ── Volumes ─────────────────────────────────────────────────────────
if [[ "$REMOVE_DATA" == "true" ]]; then
    info "Entferne Docker-Volumes..."
    docker volume rm rag-ollama-data 2>/dev/null && ok "Volume: rag-ollama-data" || true
    docker volume rm rag-chromadb-data 2>/dev/null && ok "Volume: rag-chromadb-data" || true
    docker volume rm rag-knowledge-data 2>/dev/null && ok "Volume: rag-knowledge-data" || true
    docker volume rm rag-config-data 2>/dev/null && ok "Volume: rag-config-data" || true
    docker volume rm rag-logs-data 2>/dev/null && ok "Volume: rag-logs-data" || true
else
    warn "Docker-Volumes bleiben erhalten. Zum Löschen: --remove-data"
    info "Vorhandene Volumes:"
    docker volume ls --filter name=rag- --format "    {{.Name}}" 2>/dev/null || true
fi

# ── Images ──────────────────────────────────────────────────────────
if [[ "$REMOVE_IMAGES" == "true" ]]; then
    info "Entferne Docker-Images..."
    docker rmi ollama/ollama 2>/dev/null && ok "Image: ollama/ollama" || true
    docker rmi chromadb/chroma 2>/dev/null && ok "Image: chromadb/chroma" || true
    docker rmi nginx:alpine 2>/dev/null && ok "Image: nginx:alpine" || true
    # Backend image (name varies)
    BACKEND_IMG=$(docker images --filter "reference=*rag*backend*" -q 2>/dev/null)
    if [[ -n "$BACKEND_IMG" ]]; then
        docker rmi "$BACKEND_IMG" 2>/dev/null && ok "Image: backend" || true
    fi
else
    warn "Docker-Images bleiben erhalten. Zum Löschen: --remove-images"
fi

# ── Installationsverzeichnis ────────────────────────────────────────
if [[ -d "$INSTALL_DIR" ]]; then
    read -rp "  Installationsverzeichnis $INSTALL_DIR löschen? [j/N] " answer
    if [[ "${answer,,}" == "j" || "${answer,,}" == "y" ]]; then
        rm -rf "$INSTALL_DIR"
        ok "Verzeichnis $INSTALL_DIR entfernt"
    else
        warn "Verzeichnis $INSTALL_DIR bleibt erhalten"
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}  RAG-Chat wurde deinstalliert.${NC}"
echo -e "  ${BOLD}© 2026 David Dülle${NC} — https://duelle.org"
echo ""
