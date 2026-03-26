#!/usr/bin/env bash
# RAG-Chat — © 2026 David Dülle
# https://duelle.org
#
# One-Click Installer für RAG-Chat
# Usage: curl -fsSL https://raw.githubusercontent.com/REPO/main/install.sh | bash
#    or: bash install.sh [--uninstall] [--port 8080] [--no-gpu]

set -euo pipefail

# ── Farben & Symbole ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e " ${GREEN}✔${NC} $*"; }
warn() { echo -e " ${YELLOW}⚠${NC} $*"; }
err()  { echo -e " ${RED}✘${NC} $*"; }
info() { echo -e " ${BLUE}ℹ${NC} $*"; }
step() { echo -e "\n${CYAN}${BOLD}── $* ──${NC}"; }

# ── Defaults ────────────────────────────────────────────────────────
INSTALL_DIR="/opt/rag-chat"
HTTP_PORT=8080
ADMIN_USER="admin"
ADMIN_PASSWORD=""
ENABLE_GPU=auto          # auto | yes | no
GITHUB_REPO=""
SKIP_MODEL_PULL=false
INTERACTIVE=true

# ── CLI-Argumente ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)       HTTP_PORT="$2"; shift 2 ;;
        --dir)        INSTALL_DIR="$2"; shift 2 ;;
        --no-gpu)     ENABLE_GPU=no; shift ;;
        --gpu)        ENABLE_GPU=yes; shift ;;
        --admin-user) ADMIN_USER="$2"; shift 2 ;;
        --admin-pass) ADMIN_PASSWORD="$2"; shift 2 ;;
        --repo)       GITHUB_REPO="$2"; shift 2 ;;
        --skip-model) SKIP_MODEL_PULL=true; shift ;;
        --non-interactive) INTERACTIVE=false; shift ;;
        --help|-h)
            echo "RAG-Chat Installer"
            echo ""
            echo "Usage: bash install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --port PORT       HTTP-Port (default: 8080)"
            echo "  --dir PATH        Installationsverzeichnis (default: /opt/rag-chat)"
            echo "  --no-gpu          GPU-Support deaktivieren (CPU-only)"
            echo "  --gpu             GPU-Support erzwingen"
            echo "  --admin-user USER Admin-Benutzername (default: admin)"
            echo "  --admin-pass PASS Admin-Passwort (sonst generiert)"
            echo "  --repo USER/REPO  GitHub-Repository für Updates"
            echo "  --skip-model      Standard-Modell nicht herunterladen"
            echo "  --non-interactive Keine interaktiven Prompts"
            echo "  --help            Diese Hilfe anzeigen"
            exit 0
            ;;
        *)
            err "Unbekanntes Argument: $1"
            exit 1
            ;;
    esac
done

# ── Root-Check ──────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "Bitte als root ausführen: sudo bash install.sh"
    exit 1
fi

# ── Banner ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║         RAG-Chat  Installer          ║"
echo "  ║    Lokale KI für Ihre Dokumente      ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}© 2026 David Dülle${NC} — https://duelle.org"
echo ""

# ═══════════════════════════════════════════════════════════════════
# 1. DEPENDENCY CHECK
# ═══════════════════════════════════════════════════════════════════
step "1/7  Abhängigkeiten prüfen"

MISSING_DEPS=()

# Docker
if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' | head -1)
    ok "Docker $DOCKER_VERSION"
else
    MISSING_DEPS+=("docker")
    warn "Docker nicht gefunden"
fi

# Docker Compose (v2 plugin)
if docker compose version &>/dev/null 2>&1; then
    COMPOSE_VERSION=$(docker compose version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' | head -1)
    ok "Docker Compose $COMPOSE_VERSION"
else
    MISSING_DEPS+=("docker-compose")
    warn "Docker Compose nicht gefunden"
fi

# curl
if command -v curl &>/dev/null; then
    ok "curl"
else
    MISSING_DEPS+=("curl")
    warn "curl nicht gefunden"
fi

# git
if command -v git &>/dev/null; then
    ok "git"
else
    MISSING_DEPS+=("git")
    warn "git nicht gefunden"
fi

# htpasswd (apache2-utils)
if command -v htpasswd &>/dev/null; then
    ok "htpasswd"
else
    MISSING_DEPS+=("apache2-utils")
    warn "htpasswd nicht gefunden"
fi

# ── Fehlende Pakete installieren ────────────────────────────────────
if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    step "Fehlende Pakete installieren"
    info "Installiere: ${MISSING_DEPS[*]}"

    apt-get update -qq

    for dep in "${MISSING_DEPS[@]}"; do
        case "$dep" in
            docker)
                info "Installiere Docker via offizielles Skript..."
                curl -fsSL https://get.docker.com | bash
                systemctl enable --now docker
                ok "Docker installiert"
                ;;
            docker-compose)
                # Docker Compose v2 kommt als Plugin mit Docker
                if ! docker compose version &>/dev/null 2>&1; then
                    apt-get install -y -qq docker-compose-plugin 2>/dev/null || true
                fi
                ok "Docker Compose Plugin"
                ;;
            *)
                apt-get install -y -qq "$dep"
                ok "$dep installiert"
                ;;
        esac
    done
fi

# ═══════════════════════════════════════════════════════════════════
# 2. GPU DETECTION
# ═══════════════════════════════════════════════════════════════════
step "2/7  GPU erkennen"

GPU_MODE="cpu"
DEFAULT_MODEL="llama3.2:1b"

if [[ "$ENABLE_GPU" == "no" ]]; then
    info "GPU deaktiviert per --no-gpu Flag"
else
    # nvidia-container-toolkit prüfen
    NVIDIA_TOOLKIT=false
    if command -v nvidia-smi &>/dev/null; then
        ok "nvidia-smi gefunden"

        # Check for nvidia-container-toolkit
        if dpkg -l nvidia-container-toolkit &>/dev/null 2>&1 || \
           rpm -q nvidia-container-toolkit &>/dev/null 2>&1; then
            NVIDIA_TOOLKIT=true
            ok "nvidia-container-toolkit installiert"
        else
            warn "nvidia-container-toolkit fehlt"
            if [[ "$INTERACTIVE" == "true" ]]; then
                echo ""
                read -rp "  nvidia-container-toolkit installieren? [J/n] " answer
                if [[ "${answer,,}" != "n" ]]; then
                    info "Installiere nvidia-container-toolkit..."
                    distribution=$(. /etc/os-release; echo "$ID$VERSION_ID")
                    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
                        gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
                    curl -s -L "https://nvidia.github.io/libnvidia-container/${distribution}/libnvidia-container.list" | \
                        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
                    apt-get update -qq
                    apt-get install -y -qq nvidia-container-toolkit
                    nvidia-ctk runtime configure --runtime=docker
                    systemctl restart docker
                    NVIDIA_TOOLKIT=true
                    ok "nvidia-container-toolkit installiert"
                fi
            fi
        fi

        if [[ "$NVIDIA_TOOLKIT" == "true" ]]; then
            GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | xargs)
            GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | xargs)
            ok "GPU: $GPU_NAME (${GPU_VRAM} MB VRAM)"
            GPU_MODE="nvidia"
        else
            warn "NVIDIA GPU erkannt, aber Container-Toolkit fehlt → CPU-Modus"
        fi
    else
        info "Keine NVIDIA GPU erkannt → CPU-Modus"
    fi
fi

ok "Modus: ${GPU_MODE^^}"

# ═══════════════════════════════════════════════════════════════════
# 3. INTERAKTIVE KONFIGURATION
# ═══════════════════════════════════════════════════════════════════
step "3/7  Konfiguration"

if [[ "$INTERACTIVE" == "true" ]]; then
    echo ""
    read -rp "  HTTP-Port [$HTTP_PORT]: " input_port
    HTTP_PORT="${input_port:-$HTTP_PORT}"

    read -rp "  Admin-Benutzer [$ADMIN_USER]: " input_user
    ADMIN_USER="${input_user:-$ADMIN_USER}"

    if [[ -z "$ADMIN_PASSWORD" ]]; then
        read -rsp "  Admin-Passwort (leer = auto-generiert): " input_pass
        echo ""
        ADMIN_PASSWORD="${input_pass}"
    fi
fi

# Passwort generieren falls leer
if [[ -z "$ADMIN_PASSWORD" ]]; then
    ADMIN_PASSWORD=$(tr -dc 'A-Za-z0-9!@#$%' </dev/urandom | head -c 16)
    info "Admin-Passwort generiert: ${BOLD}$ADMIN_PASSWORD${NC}"
    warn "Bitte notieren — wird nur einmal angezeigt!"
fi

ok "Port: $HTTP_PORT"
ok "Admin: $ADMIN_USER"

# ═══════════════════════════════════════════════════════════════════
# 4. INSTALLATION
# ═══════════════════════════════════════════════════════════════════
step "4/7  Dateien installieren"

# Prüfen ob wir schon im Repo-Verzeichnis sind
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/docker-compose.yml" ]]; then
    # Installer wird aus dem Repo ausgeführt
    if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
        info "Kopiere Dateien nach $INSTALL_DIR..."
        mkdir -p "$INSTALL_DIR"
        cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
        cp -r "$SCRIPT_DIR"/.env* "$INSTALL_DIR/" 2>/dev/null || true
        cp -r "$SCRIPT_DIR"/.gitignore "$INSTALL_DIR/" 2>/dev/null || true
    fi
    ok "Dateien aus lokalem Repository"
elif [[ -n "$GITHUB_REPO" ]]; then
    # Aus GitHub klonen
    info "Klone Repository von GitHub..."
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        cd "$INSTALL_DIR"
        git pull --ff-only
        ok "Repository aktualisiert"
    else
        git clone "https://github.com/$GITHUB_REPO.git" "$INSTALL_DIR"
        ok "Repository geklont"
    fi
else
    err "Kein Repository angegeben und kein lokales Repo gefunden."
    err "Verwende: --repo USER/REPO oder führe das Skript aus dem Repo-Verzeichnis aus."
    exit 1
fi

cd "$INSTALL_DIR"

# ── .env erstellen ──────────────────────────────────────────────────
info "Erstelle .env Konfiguration..."

cat > "$INSTALL_DIR/.env" << EOF
# RAG-Chat — Konfiguration (generiert von install.sh)
# © 2026 David Dülle · https://duelle.org

# Server
HTTP_PORT=$HTTP_PORT

# Admin-Zugang
ADMIN_USER=$ADMIN_USER
ADMIN_PASSWORD=$ADMIN_PASSWORD

# Ollama
OLLAMA_HOST=ollama
OLLAMA_PORT=11434
NVIDIA_VISIBLE_DEVICES=all

# ChromaDB
CHROMA_HOST=chromadb
CHROMA_PORT=8000

# Pfade
KNOWLEDGE_PATH=/data/knowledge
CONFIG_PATH=/data/config

# Modelle
CHAT_MODEL=$DEFAULT_MODEL
EMBEDDING_MODEL=nomic-embed-text

# RAG
RAG_TOP_K=5
CONTEXT_WINDOW=4096
TEMPERATURE=0.7

# Updates
GITHUB_REPO=${GITHUB_REPO:-}
UPDATE_CHANNEL=stable
EOF

ok ".env erstellt"

# ── htpasswd erstellen ──────────────────────────────────────────────
info "Erstelle Admin-Zugangsdaten..."
mkdir -p "$INSTALL_DIR/nginx"
htpasswd -bc "$INSTALL_DIR/nginx/htpasswd" "$ADMIN_USER" "$ADMIN_PASSWORD" 2>/dev/null
ok "htpasswd erstellt ($ADMIN_USER)"

# ── GPU in docker-compose aktivieren ────────────────────────────────
if [[ "$GPU_MODE" == "nvidia" ]]; then
    info "Aktiviere GPU-Passthrough in docker-compose.yml..."
    # Uncomment the GPU deploy section
    if grep -q '# deploy:' "$INSTALL_DIR/docker-compose.yml"; then
        sed -i 's/^    # deploy:/    deploy:/' "$INSTALL_DIR/docker-compose.yml"
        sed -i 's/^    #   resources:/      resources:/' "$INSTALL_DIR/docker-compose.yml"
        sed -i 's/^    #     reservations:/        reservations:/' "$INSTALL_DIR/docker-compose.yml"
        sed -i 's/^    #       devices:/          devices:/' "$INSTALL_DIR/docker-compose.yml"
        sed -i 's/^    #         - driver: nvidia/            - driver: nvidia/' "$INSTALL_DIR/docker-compose.yml"
        sed -i 's/^    #           count: all/              count: all/' "$INSTALL_DIR/docker-compose.yml"
        sed -i 's/^    #           capabilities: \[gpu\]/              capabilities: [gpu]/' "$INSTALL_DIR/docker-compose.yml"
        ok "GPU-Passthrough aktiviert"
    else
        ok "GPU-Passthrough bereits aktiv"
    fi
fi

# ═══════════════════════════════════════════════════════════════════
# 5. DOCKER BUILD
# ═══════════════════════════════════════════════════════════════════
step "5/7  Docker-Container bauen"

info "Lade Images und baue Container..."
docker compose pull ollama chromadb 2>&1 | tail -5
ok "Base-Images geladen"

docker compose build --no-cache backend 2>&1 | tail -5
ok "Backend gebaut"

# ═══════════════════════════════════════════════════════════════════
# 6. SYSTEMD SERVICE
# ═══════════════════════════════════════════════════════════════════
step "6/7  systemd-Service einrichten"

cat > /etc/systemd/system/rag-chat.service << EOF
[Unit]
Description=RAG-Chat — Lokale KI-Dokumentensuche
Documentation=https://duelle.org
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose restart
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable rag-chat.service
ok "rag-chat.service erstellt und aktiviert"

# ── Update-Timer (prüft 1x täglich auf Updates) ────────────────────
if [[ -n "$GITHUB_REPO" ]]; then
    cat > /etc/systemd/system/rag-chat-update.service << EOF
[Unit]
Description=RAG-Chat Update Check
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/update.sh --check
EOF

    cat > /etc/systemd/system/rag-chat-update.timer << EOF
[Unit]
Description=RAG-Chat täglicher Update-Check

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=3600

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable rag-chat-update.timer
    ok "Update-Timer aktiviert (täglich)"
fi

# ═══════════════════════════════════════════════════════════════════
# 7. START & MODELL
# ═══════════════════════════════════════════════════════════════════
step "7/7  Starten"

info "Starte alle Services..."
docker compose up -d 2>&1 | tail -5
ok "Container gestartet"

# Warte auf Ollama
info "Warte auf Ollama..."
OLLAMA_READY=false
for i in $(seq 1 30); do
    if docker exec rag-ollama curl -sf http://localhost:11434/api/tags &>/dev/null; then
        OLLAMA_READY=true
        break
    fi
    sleep 2
done

if [[ "$OLLAMA_READY" == "true" ]]; then
    ok "Ollama bereit"

    # Embedding-Modell herunterladen
    info "Lade Embedding-Modell (nomic-embed-text)..."
    docker exec rag-ollama ollama pull nomic-embed-text 2>&1 | tail -3
    ok "Embedding-Modell geladen"

    # Standard Chat-Modell herunterladen
    if [[ "$SKIP_MODEL_PULL" != "true" ]]; then
        info "Lade Chat-Modell ($DEFAULT_MODEL)..."
        docker exec rag-ollama ollama pull "$DEFAULT_MODEL" 2>&1 | tail -3
        ok "Chat-Modell geladen"
    fi
else
    warn "Ollama reagiert noch nicht — Modelle müssen manuell geladen werden"
    warn "  docker exec rag-ollama ollama pull nomic-embed-text"
    warn "  docker exec rag-ollama ollama pull $DEFAULT_MODEL"
fi

# Warte auf Backend
info "Warte auf Backend..."
BACKEND_READY=false
for i in $(seq 1 20); do
    if docker exec rag-backend curl -sf http://localhost:8000/api/health &>/dev/null; then
        BACKEND_READY=true
        break
    fi
    sleep 2
done

if [[ "$BACKEND_READY" == "true" ]]; then
    ok "Backend bereit"
else
    warn "Backend noch nicht bereit — bitte warten oder Logs prüfen:"
    warn "  docker compose -f $INSTALL_DIR/docker-compose.yml logs backend"
fi

# ═══════════════════════════════════════════════════════════════════
# FERTIG
# ═══════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║     Installation abgeschlossen!      ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo -e "  ${BOLD}Chat:${NC}   http://${LOCAL_IP}:${HTTP_PORT}"
echo -e "  ${BOLD}Admin:${NC}  http://${LOCAL_IP}:${HTTP_PORT}/admin"
echo ""
echo -e "  ${BOLD}Admin-Login:${NC}"
echo -e "    Benutzer: ${CYAN}$ADMIN_USER${NC}"
echo -e "    Passwort: ${CYAN}$ADMIN_PASSWORD${NC}"
echo ""
echo -e "  ${BOLD}Modell:${NC} $DEFAULT_MODEL (${GPU_MODE^^})"
echo ""
echo -e "  ${BOLD}Nützliche Befehle:${NC}"
echo -e "    Status:    ${CYAN}systemctl status rag-chat${NC}"
echo -e "    Stoppen:   ${CYAN}systemctl stop rag-chat${NC}"
echo -e "    Starten:   ${CYAN}systemctl start rag-chat${NC}"
echo -e "    Logs:      ${CYAN}docker compose -C $INSTALL_DIR logs -f${NC}"
echo -e "    Update:    ${CYAN}bash $INSTALL_DIR/update.sh${NC}"
echo -e "    Entfernen: ${CYAN}bash $INSTALL_DIR/uninstall.sh${NC}"
echo ""
echo -e "  ${BOLD}© 2026 David Dülle${NC} — https://duelle.org"
echo ""
