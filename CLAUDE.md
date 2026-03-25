# RAG-Chat — Lokale AI-RAG-Anwendung

## Projektübersicht

Lokale, selbstgehostete RAG-Chat-Anwendung für Linux-Server mit Nvidia-GPUs. Zielgruppe: Laien in Bildungseinrichtungen. Kein Internet erforderlich nach Installation.

**Stack:** Docker Compose (Ollama + ChromaDB + FastAPI + Nginx), statisches HTML-Frontend, Python-Backend.

**Kernprinzipien:**
- Ein-Klick-Installation via `install.sh`
- Kein Login, kein HTTPS — läuft lokal im Netzwerk auf HTTP
- Admin-Panel unter `/admin` (HTTP Basic Auth)
- Statisches Frontend: Vanilla HTML/CSS/JS, kein Build-Step, kein Framework
- Config als einzelne JSON-Datei, export-/importierbar
- Auto-Updates via GitHub Releases

## Architektur

```
┌─────────────────────────────────────────────┐
│                  Nginx (:8080)               │
│  ┌──────────────┐  ┌──────────────────────┐ │
│  │  Chat-UI      │  │  Admin-Panel (/admin)│ │
│  │  (statisch)   │  │  (statisch + Auth)   │ │
│  └──────┬───────┘  └──────────┬───────────┘ │
├─────────┼─────────────────────┼─────────────┤
│         ▼                     ▼              │
│  ┌──────────────────────────────────────┐   │
│  │        FastAPI Backend (:8000)        │   │
│  │  - POST /chat (SSE Streaming)        │   │
│  │  - POST /upload (temp. Kontext)      │   │
│  │  - GET/POST /admin/api/*             │   │
│  └──────┬──────────────┬────────────────┘   │
│         ▼              ▼                     │
│  ┌────────────┐  ┌──────────┐               │
│  │   Ollama    │  │ ChromaDB │               │
│  │  (:11434)   │  │ (:8001)  │               │
│  │  GPU/CPU    │  │ Vektoren │               │
│  └────────────┘  └──────────┘               │
└─────────────────────────────────────────────┘
```

**Netzwerk:** Internes Docker-Netzwerk. Nur Nginx-Port (Standard: 8080) wird nach außen exponiert.

## Projektstruktur

```
rag-chat/
├── CLAUDE.md                    # Diese Datei
├── README.md                    # Installationsanleitung
├── LICENSE
├── docker-compose.yml           # Alle Services
├── .env.example                 # Umgebungsvariablen-Template
├── install.sh                   # Ein-Klick-Installer
├── uninstall.sh                 # Saubere Deinstallation
├── update.sh                    # Manuelles Update
│
├── backend/                     # FastAPI Python-Backend
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI App + Endpoints
│   ├── config.py                # Config laden/speichern/validieren
│   ├── rag/
│   │   ├── indexer.py           # File-Watcher + Chunking + Embedding
│   │   ├── query.py             # ChromaDB Search + Ollama Prompt + SSE
│   │   ├── parser.py            # PDF/DOCX/TXT/MD/CSV Parser
│   │   └── embeddings.py        # Ollama Embedding-Client
│   ├── admin/
│   │   ├── routes.py            # Admin-API Endpoints
│   │   ├── system.py            # GPU-Info, RAM, Disk, Uptime
│   │   ├── models.py            # Ollama Modell-Verwaltung
│   │   └── updates.py           # GitHub Release Check + Update
│   └── utils/
│       ├── gpu.py               # nvidia-smi Parsing
│       └── logging.py           # Strukturiertes Logging
│
├── frontend/                    # Statisches Chat-Frontend
│   ├── index.html               # Chat-UI (alles in einer Datei)
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── chat.js              # Chat-Logik + SSE-Client
│       ├── upload.js            # Datei-Upload
│       └── ui.js                # Dark Mode, Scroll, Typing-Indicator
│
├── admin/                       # Statisches Admin-Panel
│   ├── index.html               # Dashboard
│   ├── css/
│   │   └── admin.css
│   └── js/
│       ├── dashboard.js         # System-Metriken Polling
│       ├── models.js            # Modell-Verwaltung UI
│       ├── files.js             # RAG-Datei-Manager UI
│       ├── config.js            # Config Import/Export UI
│       ├── updates.js           # Update-Manager UI
│       └── performance.js       # Live-Charts (Chart.js)
│
├── nginx/
│   ├── nginx.conf               # Routing: / → Frontend, /admin → Admin
│   └── htpasswd                 # Basic Auth (generiert bei Install)
│
├── scripts/
│   ├── gpu-detect.sh            # GPU-Autodetection
│   ├── update-check.sh          # GitHub Release Check (systemd-Timer)
│   └── backup-config.sh         # Config-Snapshot erstellen
│
├── data/                        # Docker Volumes (nicht im Git)
│   ├── knowledge/               # Admin-Wissensbasis (Bind-Mount vom Host)
│   ├── chromadb/                # ChromaDB Persistenz
│   ├── ollama/                  # Ollama Modelle
│   ├── config/                  # rag-config.json + Snapshots
│   └── logs/                    # Indexierungs- und Update-Logs
│
├── docs/                        # Detaillierte Dokumentation
│   ├── ARCHITECTURE.md          # Architektur-Details
│   ├── PROJEKTPLAN.md           # Vollständiger Projektplan mit Tasks
│   ├── CONFIG-SCHEMA.md         # Config-Datei Referenz
│   ├── API-ENDPOINTS.md         # Backend-API Dokumentation
│   └── GPU-MATRIX.md            # GPU-Kompatibilitätsmatrix
│
└── tests/
    ├── test_indexer.py
    ├── test_query.py
    ├── test_config.py
    └── test_api.py
```

## Aufgaben-Referenz (Projektplan)

Der vollständige Projektplan mit Checklisten steht in `docs/PROJEKTPLAN.md`.
Hier die Kurzreferenz der Aufgaben-IDs:

### Phase 1 — Infrastruktur & Installer (W1–W2)
- **INF-01** Docker-Compose-Setup (GPU-Passthrough, Health-Checks)
- **INF-02** GPU-Autodetection (nvidia-smi → JSON → Modellempfehlung)
- **INF-03** One-Click Installer (install.sh + systemd)
- **INF-04** Auto-Update Handler (GitHub Releases + Rollback)

### Phase 2 — RAG-Pipeline (W3–W5)
- **RAG-01** ChromaDB + Embeddings (Collections nach Ordnerstruktur)
- **RAG-02** Dokument-Indexer (watchdog + Chunking + Fortschrittsanzeige)
- **RAG-03** Query-Engine + SSE-Streaming
- **RAG-04** Temporärer User-Upload (Session-Kontext, kein ChromaDB)

### Phase 3 — Chat-Frontend (W5–W7)
- **FE-01** Chat-UI (Vanilla HTML/CSS/JS, marked.js, highlight.js)
- **FE-02** SSE-Streaming (Token-by-Token, Abort, Reconnect)
- **FE-03** Quellenanzeige (klappbar, Score-Balken)
- **FE-04** Lokale Chat-History (localStorage)

### Phase 4 — Admin-Panel (W7–W9)
- **ADM-01** Admin-Dashboard (System-Status, GPU, Basic Auth)
- **ADM-02** Modell-Verwaltung (Download, Wechsel, VRAM-Check)
- **ADM-03** RAG-Datei-Manager (Upload, Ordner-Tags, Löschung)
- **ADM-04** Update-Manager (Versionsstatus, Changelog, Rollback)
- **ADM-05** Performance-Monitor (Chart.js Live-Charts, SQLite 24h)
- **ADM-06** Config-Manager (JSON Export/Import, Snapshots, Verlauf)

### Phase 5 — Testing & Dokumentation (W9–W10)
- **DOC-01** Installations-Dokumentation (README, Troubleshooting)
- **DOC-02** GPU-Kompatibilitätsmatrix (Benchmarks)

## Technische Konventionen

### Python (Backend)
- Python 3.11+
- FastAPI + Uvicorn
- Async wo möglich (httpx für Ollama, aiofiles)
- Type-Hints überall
- Pydantic-Models für Config und API Request/Response
- Logging: strukturiert (JSON), nach `/data/logs/`

### Frontend (Chat + Admin)
- Kein Build-Step, kein Node.js, kein Framework
- Vanilla HTML/CSS/JS
- CDN-Libs: marked.js (Markdown), highlight.js (Code), Chart.js (Admin-Charts)
- Responsive: Mobile-first
- Dark/Light Mode via CSS Custom Properties + `prefers-color-scheme`
- Alle Fetch-Calls mit Error-Handling und Retry-Logik

### Docker
- Base-Images: `python:3.11-slim` (Backend), `nginx:alpine` (Frontend)
- Ollama: `ollama/ollama` mit `runtime: nvidia`
- ChromaDB: `chromadb/chroma`
- Named Volumes für persistente Daten
- Health-Checks auf allen Containern
- `.env` Datei für konfigurierbare Werte (Ports, Modelle)

### Config-Datei (rag-config.json)
```json
{
  "ollama": {
    "model": "llama3.1:8b-instruct-q5_K_M",
    "temperature": 0.7,
    "top_p": 0.9,
    "context_window": 8192,
    "system_prompt": "..."
  },
  "rag": {
    "embedding_model": "nomic-embed-text",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "top_k": 5,
    "knowledge_path": "/data/knowledge",
    "supported_formats": ["pdf", "docx", "txt", "md", "csv"]
  },
  "server": {
    "http_port": 8080,
    "admin_path": "/admin",
    "max_upload_mb": 10,
    "session_timeout_min": 30,
    "bind_address": "0.0.0.0"
  },
  "updates": {
    "auto_update": true,
    "check_interval": "daily",
    "channel": "stable"
  }
}
```

### Git-Konventionen
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- Task-ID im Commit: `feat(INF-01): docker-compose with GPU passthrough`
- Branches: `main` (stable), `dev` (development), `feat/INF-01-docker-setup`
- Semantic Versioning für Releases
- `/data` Ordner ist in `.gitignore`

## Wichtige Design-Entscheidungen

1. **Warum ChromaDB?** Für 5–20 GB Quelldateien (~500k–2M Chunks) performant genug. Single-Node, kein Cluster nötig. Query-Latenz ~3ms. Braucht ~8 GB RAM für 2M Vektoren.

2. **Warum kein Framework im Frontend?** Zielgruppe sind Laien — die HTML-Dateien müssen ohne Build-Tools editierbar sein. Nginx liefert sie direkt aus.

3. **Warum JSON für Config?** Einfach zu parsen, menschenlesbar, export-/importierbar. Pydantic validiert beim Laden. Snapshots ermöglichen Rollback.

4. **Warum systemd statt Docker-eigener Restart?** systemd bietet: Boot-Start, Journal-Logging, Timer für Update-Checks, Status-Abfrage für Admin-Panel.

5. **Indexer als eigener Service vs. im Backend?** Läuft im Backend-Container als Background-Task (asyncio). Kein separater Container nötig — vereinfacht die Architektur.
