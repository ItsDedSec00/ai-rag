#!/usr/bin/env bash
# RAG-Chat — © 2026 David Dülle
# https://duelle.org
#
# Update-Script für RAG-Chat
# Usage: bash update.sh [--check] [--force] [--rollback]

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e " ${GREEN}✔${NC} $*"; }
warn() { echo -e " ${YELLOW}⚠${NC} $*"; }
err()  { echo -e " ${RED}✘${NC} $*"; }
info() { echo -e " ${BLUE}ℹ${NC} $*"; }

# Installationsverzeichnis ermitteln
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR"

if [[ ! -f "$INSTALL_DIR/docker-compose.yml" ]]; then
    err "docker-compose.yml nicht gefunden in $INSTALL_DIR"
    exit 1
fi

cd "$INSTALL_DIR"

# .env laden
if [[ -f "$INSTALL_DIR/.env" ]]; then
    # shellcheck disable=SC1091
    source "$INSTALL_DIR/.env"
fi

GITHUB_REPO="${GITHUB_REPO:-}"
LOG_DIR="$INSTALL_DIR/data/logs"
LOG_FILE="$LOG_DIR/update.log"
mkdir -p "$LOG_DIR" 2>/dev/null || true

MODE="update"
FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)    MODE="check"; shift ;;
        --force)    FORCE=true; shift ;;
        --rollback) MODE="rollback"; shift ;;
        --help|-h)
            echo "RAG-Chat Update"
            echo ""
            echo "Usage: bash update.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --check     Nur auf Updates prüfen (kein Update)"
            echo "  --force     Update erzwingen (auch wenn aktuell)"
            echo "  --rollback  Auf vorherige Version zurücksetzen"
            echo "  --help      Diese Hilfe anzeigen"
            exit 0
            ;;
        *) err "Unbekanntes Argument: $1"; exit 1 ;;
    esac
done

# ── Aktuelle Version ermitteln ──────────────────────────────────────
get_local_version() {
    if git describe --tags --abbrev=0 2>/dev/null; then
        return 0
    fi
    git rev-parse --short HEAD 2>/dev/null || echo "unknown"
}

get_remote_version() {
    if [[ -z "$GITHUB_REPO" ]]; then
        echo ""
        return 1
    fi
    curl -sf "https://api.github.com/repos/$GITHUB_REPO/releases/latest" 2>/dev/null | \
        grep -oP '"tag_name"\s*:\s*"\K[^"]+' || echo ""
}

log_update() {
    local status="$1"
    local from_ver="$2"
    local to_ver="$3"
    local msg="${4:-}"
    local timestamp
    timestamp=$(date -Iseconds)
    echo "{\"timestamp\":\"$timestamp\",\"status\":\"$status\",\"from\":\"$from_ver\",\"to\":\"$to_ver\",\"message\":\"$msg\"}" >> "$LOG_FILE"
}

# ═══════════════════════════════════════════════════════════════════
# CHECK MODE
# ═══════════════════════════════════════════════════════════════════
if [[ "$MODE" == "check" ]]; then
    LOCAL_VER=$(get_local_version)
    info "Aktuelle Version: $LOCAL_VER"

    if [[ -z "$GITHUB_REPO" ]]; then
        warn "Kein GitHub-Repository konfiguriert (GITHUB_REPO in .env)"
        exit 0
    fi

    REMOTE_VER=$(get_remote_version)
    if [[ -z "$REMOTE_VER" ]]; then
        warn "Konnte Remote-Version nicht ermitteln"
        exit 1
    fi

    info "Neueste Version: $REMOTE_VER"

    if [[ "$LOCAL_VER" == "$REMOTE_VER" ]]; then
        ok "System ist aktuell"
        exit 0
    else
        warn "Update verfügbar: $LOCAL_VER → $REMOTE_VER"
        info "Ausführen: bash $INSTALL_DIR/update.sh"
        exit 0
    fi
fi

# ═══════════════════════════════════════════════════════════════════
# ROLLBACK MODE
# ═══════════════════════════════════════════════════════════════════
if [[ "$MODE" == "rollback" ]]; then
    echo -e "\n${BOLD}RAG-Chat Rollback${NC}\n"

    # Vorherige Version aus Git
    CURRENT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    PREVIOUS=$(git rev-parse --short HEAD~1 2>/dev/null || echo "")

    if [[ -z "$PREVIOUS" ]]; then
        err "Keine vorherige Version verfügbar"
        exit 1
    fi

    info "Aktuelle Version:  $CURRENT"
    info "Vorherige Version: $PREVIOUS"

    read -rp "  Auf $PREVIOUS zurücksetzen? [j/N] " answer
    if [[ "${answer,,}" != "j" && "${answer,,}" != "y" ]]; then
        info "Abgebrochen."
        exit 0
    fi

    info "Erstelle Config-Backup..."
    if docker exec rag-backend curl -sf http://localhost:8000/api/admin/config/snapshot -X POST &>/dev/null; then
        ok "Config-Snapshot erstellt"
    fi

    info "Setze auf vorherige Version zurück..."
    git checkout "$PREVIOUS" -- .
    ok "Dateien zurückgesetzt"

    info "Baue Container neu..."
    docker compose build --no-cache backend 2>&1 | tail -3
    docker compose up -d 2>&1 | tail -3
    ok "Container neu gestartet"

    log_update "rollback" "$CURRENT" "$PREVIOUS" "Manual rollback"
    ok "Rollback abgeschlossen: $CURRENT → $PREVIOUS"
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════
# UPDATE MODE
# ═══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}${CYAN}RAG-Chat Update${NC}\n"

LOCAL_VER=$(get_local_version)
info "Aktuelle Version: $LOCAL_VER"

# Git pull
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Lade Updates von Git..."

    # Lokale Änderungen stashen
    if ! git diff --quiet 2>/dev/null; then
        warn "Lokale Änderungen gefunden — werden zwischengespeichert"
        git stash push -m "pre-update-$(date +%Y%m%d-%H%M%S)"
    fi

    git fetch --tags 2>/dev/null || true
    REMOTE_VER=$(get_remote_version)

    if [[ -n "$REMOTE_VER" && "$LOCAL_VER" == "$REMOTE_VER" && "$FORCE" != "true" ]]; then
        ok "Bereits auf der neuesten Version ($LOCAL_VER)"
        exit 0
    fi

    git pull --ff-only 2>/dev/null || {
        warn "Fast-forward nicht möglich — versuche rebase"
        git pull --rebase 2>/dev/null || {
            err "Update fehlgeschlagen — bitte manuell auflösen"
            log_update "failed" "$LOCAL_VER" "${REMOTE_VER:-unknown}" "Git pull failed"
            exit 1
        }
    }

    NEW_VER=$(get_local_version)
    ok "Code aktualisiert: $LOCAL_VER → $NEW_VER"

    # Update APP_VERSION in .env so the backend reports the correct version
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        if grep -q "^APP_VERSION=" "$INSTALL_DIR/.env"; then
            sed -i "s/^APP_VERSION=.*/APP_VERSION=$NEW_VER/" "$INSTALL_DIR/.env"
        else
            echo "APP_VERSION=$NEW_VER" >> "$INSTALL_DIR/.env"
        fi
        ok ".env aktualisiert: APP_VERSION=$NEW_VER"
    fi
elif [[ -n "$GITHUB_REPO" ]]; then
    err "Kein Git-Repository. Bitte neu installieren:"
    err "  git clone https://github.com/$GITHUB_REPO.git $INSTALL_DIR"
    exit 1
else
    err "Kein Git-Repository und kein GITHUB_REPO konfiguriert"
    exit 1
fi

# Config-Backup
info "Erstelle Config-Backup..."
if docker exec rag-backend curl -sf http://localhost:8000/api/admin/config/snapshot -X POST &>/dev/null; then
    ok "Config-Snapshot erstellt"
else
    warn "Config-Backup konnte nicht erstellt werden (Backend nicht erreichbar)"
fi

# Rebuild
info "Baue Container neu..."
docker compose build --no-cache backend 2>&1 | tail -5
ok "Backend neu gebaut"

docker compose pull ollama chromadb 2>&1 | tail -3
ok "Base-Images aktualisiert"

# Neustart
info "Starte Services neu..."
docker compose up -d 2>&1 | tail -3
ok "Services neu gestartet"

# Health-Check
info "Prüfe Gesundheit..."
HEALTHY=false
for i in $(seq 1 15); do
    if docker exec rag-backend curl -sf http://localhost:8000/api/health &>/dev/null; then
        HEALTHY=true
        break
    fi
    sleep 2
done

if [[ "$HEALTHY" == "true" ]]; then
    ok "System gesund"
    log_update "success" "$LOCAL_VER" "${NEW_VER:-$LOCAL_VER}" "Update completed"
else
    err "Health-Check fehlgeschlagen!"
    warn "Rollback mit: bash $INSTALL_DIR/update.sh --rollback"
    log_update "unhealthy" "$LOCAL_VER" "${NEW_VER:-$LOCAL_VER}" "Health check failed after update"
    exit 1
fi

echo ""
echo -e "${GREEN}${BOLD}  Update abgeschlossen!${NC}"
echo -e "  ${LOCAL_VER} → ${NEW_VER:-$LOCAL_VER}"
echo -e "  ${BOLD}© 2026 David Dülle${NC} — https://duelle.org"
echo ""
