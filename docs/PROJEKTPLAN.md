# Projektplan — RAG-Chat

## Übersicht

| | |
|---|---|
| **Phasen** | 5 |
| **Aufgaben** | 20 |
| **Geschätzte Dauer** | ~10 Wochen |
| **Entwickler** | 1 (Solo) |
| **Tool** | Claude Code + GitHub |

---

## Phase 1 — Infrastruktur & Installer (W1–W2)

### INF-01: Docker-Compose-Setup
**Priorität:** Hoch  
**Abhängigkeiten:** Keine

Zentrales `docker-compose.yml` mit allen vier Services: Ollama (nvidia runtime), ChromaDB, FastAPI-Backend, Nginx. Internes Docker-Netzwerk — nur Nginx-Port (z.B. 8080) wird nach außen exponiert.

**Checkliste:**
- [ ] docker-compose.yml mit allen 4 Services
- [ ] GPU-Passthrough via nvidia-container-toolkit
- [ ] Internes Docker-Netzwerk (nur Nginx exponiert)
- [ ] Named Volumes für Modelle, ChromaDB, Upload-Ordner
- [ ] Health-Checks + restart: unless-stopped
- [ ] Bind-Mount für Admin-Wissensordner vom Host
- [ ] .env.example mit allen konfigurierbaren Werten

### INF-02: GPU-Autodetection
**Priorität:** Hoch  
**Abhängigkeiten:** INF-01

Bash-Script via nvidia-smi: GPU-Typ, VRAM, Treiber-Version. Automatische Empfehlung welche Ollama-Modelle passen. Fallback auf CPU. Ergebnisse als JSON für Admin-Panel.

**Checkliste:**
- [ ] nvidia-smi Parsing → JSON
- [ ] VRAM-basierte Modellempfehlung (8B bei ≤8GB, 70B bei ≥48GB)
- [ ] Fallback CPU-Modus erkennen
- [ ] Multi-GPU Support (CUDA_VISIBLE_DEVICES)
- [ ] GPU-Info Endpoint für Admin-Panel

### INF-03: One-Click Installer
**Priorität:** Hoch  
**Abhängigkeiten:** Keine

Ein einziger Befehl: `curl -fsSL https://raw.github.com/.../install.sh | bash`. Prüft Dependencies, klont Repo, baut Container, erstellt systemd-Service.

**Checkliste:**
- [ ] Dependency-Check (Docker, nvidia-toolkit, git)
- [ ] Auto-Install fehlender Pakete via apt
- [ ] Repository klonen nach /opt/rag-chat
- [ ] docker-compose build + pull
- [ ] systemd-Service erstellen + enablen
- [ ] Interaktives Setup (Port, Standardmodell)
- [ ] --uninstall Flag (Container, Images, Service entfernen)
- [ ] Farbige Konsolenausgabe mit Status-Icons

### INF-04: Auto-Update Handler
**Priorität:** Mittel  
**Abhängigkeiten:** INF-01, INF-03

systemd-Timer prüft 1x täglich GitHub API auf neue Releases. Bei Update: git pull, docker-compose build, Neustart. Bei Fehler: Rollback.

**Checkliste:**
- [ ] systemd-Timer (1x täglich)
- [ ] GitHub Release API abfragen
- [ ] git pull + docker-compose build
- [ ] Container-Neustart mit Health-Check
- [ ] Rollback bei fehlerhaftem Start (git checkout)
- [ ] Update-Log (JSON) für Admin-Panel

---

## Phase 2 — RAG-Pipeline (W3–W5)

### RAG-01: ChromaDB + Embeddings
**Priorität:** Hoch  
**Abhängigkeiten:** INF-01

ChromaDB als Container mit persistentem Volume. Embedding-Modell via Ollama (nomic-embed-text). Collections nach Ordnernamen des Admin-Wissensordners.

**Checkliste:**
- [ ] ChromaDB Container + Volume
- [ ] Embedding-Modell via Ollama (nomic-embed-text)
- [ ] Collection pro Ordner (Ordnername = Metadaten-Tag)
- [ ] Persistenz über Container-Restart verifizieren
- [ ] Collection-Statistiken Endpoint (Anzahl Chunks, Größe)

### RAG-02: Dokument-Indexer
**Priorität:** Hoch  
**Abhängigkeiten:** RAG-01

Python-Service mit watchdog überwacht den Host-Ordner. Neue/geänderte Dateien werden geparst, gechankt, embedded und gespeichert. Gelöschte Dateien werden synchronisiert.

**Checkliste:**
- [ ] watchdog File-Watcher auf Bind-Mount
- [ ] Parser: PDF (PyPDF2), DOCX (python-docx), TXT, MD, CSV
- [ ] RecursiveCharacterTextSplitter (1000 Tokens, 200 Overlap)
- [ ] Inkrementelle Indexierung (nur geänderte Dateien, Hash-basiert)
- [ ] Lösch-Synchronisation (Datei gelöscht → Chunks entfernen)
- [ ] Indexierungs-Log (JSON): Datei, Status, Chunks, Dauer
- [ ] Fortschrittsanzeige: Gesamtfortschritt, pro Datei, ETA
- [ ] Erstindexierungs-Modus mit Restzeit-Schätzung
- [ ] Fehlerbehandlung: Datei nicht lesbar → Status "error", weiter

### RAG-03: Query-Engine + Streaming
**Priorität:** Hoch  
**Abhängigkeiten:** RAG-01, RAG-02

POST /chat: User-Query → ChromaDB Similarity Search → System-Prompt + Kontext + Query → Ollama → SSE-Stream.

**Checkliste:**
- [ ] POST /chat Endpoint (FastAPI)
- [ ] ChromaDB Similarity Search (Top-K, konfigurierbar)
- [ ] System-Prompt Template (aus Config laden)
- [ ] Context-Window Management (Chunks kürzen wenn nötig)
- [ ] SSE Streaming via Ollama API
- [ ] Source-Attribution (Dateiname + Similarity Score)
- [ ] Concurrent Request Handling (asyncio)
- [ ] Fehler-Streaming (Ollama nicht erreichbar, kein Modell geladen)

### RAG-04: Temporärer User-Upload
**Priorität:** Mittel  
**Abhängigkeiten:** RAG-03

User kann Dateien hochladen als Session-Kontext. Wird nicht in ChromaDB gespeichert. Auto-Cleanup.

**Checkliste:**
- [ ] Upload-Endpoint (multipart, max 10MB konfigurierbar)
- [ ] Temporäres Parsing (gleiche Parser wie Indexer)
- [ ] Session-basierte Kontexterweiterung (UUID)
- [ ] Auto-Cleanup (30min TTL, konfigurierbar)
- [ ] Fortschritts-Feedback für Frontend

---

## Phase 3 — Chat-Frontend (W5–W7)

### FE-01: Chat-UI (statisches HTML)
**Priorität:** Hoch  
**Abhängigkeiten:** Keine

Einzelne index.html, von Nginx ausgeliefert. Kein Build-Step.

**Checkliste:**
- [ ] Responsive Chat-Layout (Mobile + Desktop)
- [ ] Markdown-Rendering (marked.js via CDN)
- [ ] Code-Syntax-Highlighting (highlight.js via CDN)
- [ ] Dark/Light Mode Toggle + prefers-color-scheme
- [ ] Datei-Upload Button + Drag & Drop
- [ ] Typing-Indicator während Streaming
- [ ] Neuer Chat Button
- [ ] Eingabefeld: Shift+Enter für Newline, Enter zum Senden

### FE-02: SSE-Streaming
**Priorität:** Hoch  
**Abhängigkeiten:** FE-01, RAG-03

Token-by-Token Rendering mit Abbruch und Reconnect.

**Checkliste:**
- [ ] fetch() + ReadableStream SSE Client
- [ ] Token-by-Token DOM-Update (performant, kein innerHTML)
- [ ] Abort-Controller für Abbruch-Button
- [ ] Auto-Reconnect bei Disconnect
- [ ] Error-State im Chat anzeigen (rote Nachricht)
- [ ] Scroll-to-Bottom während Stream (smart scroll)

### FE-03: Quellenanzeige
**Priorität:** Niedrig  
**Abhängigkeiten:** FE-02

Klappbare Quellenangaben unter jeder Antwort.

**Checkliste:**
- [ ] Klappbare Quellenansicht (Details/Summary oder Custom)
- [ ] Dateiname + Relevanz-Score
- [ ] Chunk-Preview (erste 100 Zeichen)
- [ ] Visueller Score-Balken

### FE-04: Lokale Chat-History
**Priorität:** Niedrig  
**Abhängigkeiten:** FE-01

Chat-Verlauf in localStorage, kein Server-State.

**Checkliste:**
- [ ] localStorage Speicherung (Conversations Array)
- [ ] Chat-Liste (Sidebar, ein-/ausklappbar)
- [ ] Neuer Chat / Chat löschen
- [ ] Export als .txt

---

## Phase 4 — Admin-Panel (W7–W9)

### ADM-01: Admin-Dashboard
**Priorität:** Hoch  
**Abhängigkeiten:** INF-01

Statische HTML-Seite unter /admin, geschützt via HTTP Basic Auth.

**Checkliste:**
- [ ] Statische Admin-Seite unter /admin (Nginx)
- [ ] HTTP Basic Auth (Nginx, Credentials bei Install gesetzt)
- [ ] System-Info Endpoint (GPU-Name, VRAM, RAM, Disk)
- [ ] Anfragen-Counter (total, heute, letzte Stunde)
- [ ] Uptime-Anzeige
- [ ] Auto-Refresh Polling (5s Intervall)
- [ ] Responsive Layout

### ADM-02: Modell-Verwaltung
**Priorität:** Hoch  
**Abhängigkeiten:** ADM-01, INF-02

Modelle über Ollama API verwalten.

**Checkliste:**
- [ ] Installierte Modelle anzeigen (Name, Größe, Quantisierung)
- [ ] Modell herunterladen mit Progress-Bar (Ollama Pull API)
- [ ] Aktives Modell wechseln (Config updaten + Ollama laden)
- [ ] VRAM-Kompatibilitäts-Warnung (GPU-Info vs. Modellgröße)
- [ ] System-Prompt Editor (Textarea, aus Config)
- [ ] Temperatur / Top-P Slider (mit Live-Vorschau der Werte)

### ADM-03: RAG-Datei-Manager
**Priorität:** Mittel  
**Abhängigkeiten:** ADM-01, RAG-02

Übersicht aller Dateien mit Upload und Ordner-Tags.

**Checkliste:**
- [ ] Dateiliste mit Indexierungs-Status (indexiert/pending/error)
- [ ] Upload per Drag & Drop in Ordnerstruktur
- [ ] Ordner erstellen/umbenennen (= ChromaDB Collection Tags)
- [ ] Datei löschen + ChromaDB Sync
- [ ] Indexierungs-Log einsehen (letzte N Einträge)
- [ ] Chunk-Vorschau pro Datei (erste 3 Chunks anzeigen)
- [ ] Erstindexierungs-Fortschritt mit ETA

### ADM-04: Update-Manager
**Priorität:** Mittel  
**Abhängigkeiten:** ADM-01, INF-04

Versionsstatus und manueller Update-Trigger.

**Checkliste:**
- [ ] Versions-Vergleich (lokal vs. GitHub Latest Release)
- [ ] Changelog anzeigen (Release Notes aus GitHub API)
- [ ] Manueller Update-Trigger (Button → update.sh)
- [ ] Update-Log anzeigen (letzte N Updates)
- [ ] Rollback-Button (auf vorherige Version)

### ADM-05: Performance-Monitor
**Priorität:** Niedrig  
**Abhängigkeiten:** ADM-01

Live-Charts mit Metriken.

**Checkliste:**
- [ ] Token/s Tracking pro Request
- [ ] First-Token-Latency Messung
- [ ] GPU-Temperatur Abfrage (nvidia-smi)
- [ ] SQLite Zeitreihen (letzte 24h, 1-Minuten-Intervall)
- [ ] Chart.js Live-Charts (Line + Bar)
- [ ] Durchschnittswerte-Karten (Heute, 7 Tage)

### ADM-06: Config-Manager
**Priorität:** Mittel  
**Abhängigkeiten:** ADM-01

Config Export/Import/Snapshots.

**Checkliste:**
- [ ] GET /admin/api/config — aktuelle Config als JSON
- [ ] POST /admin/api/config — Config updaten (Pydantic-Validierung)
- [ ] GET /admin/api/config/export — Download als rag-config.json
- [ ] POST /admin/api/config/import — Upload + Validierung + Anwenden
- [ ] POST /admin/api/config/snapshot — Snapshot mit Zeitstempel
- [ ] GET /admin/api/config/snapshots — Snapshot-Liste
- [ ] POST /admin/api/config/restore/{id} — Snapshot wiederherstellen
- [ ] Änderungsverlauf (was wurde wann geändert)
- [ ] UI: Übersicht, JSON-Vorschau, Verlauf-Tab

---

## Phase 5 — Testing & Dokumentation (W9–W10)

### DOC-01: Installations-Dokumentation
**Priorität:** Hoch  
**Abhängigkeiten:** Keine

README.md mit Quick-Start und Troubleshooting.

**Checkliste:**
- [ ] Systemvoraussetzungen (Ubuntu 22/24, Nvidia-Treiber ≥525, Docker)
- [ ] Quick-Start (1 Befehl)
- [ ] Manuelle Installation (Schritt für Schritt)
- [ ] Konfigurationsreferenz (alle Config-Felder)
- [ ] FAQ + Troubleshooting (GPU nicht erkannt, Port belegt, etc.)
- [ ] Screenshots / GIFs der Oberfläche

### DOC-02: GPU-Kompatibilitätsmatrix
**Priorität:** Mittel  
**Abhängigkeiten:** INF-02, RAG-03

Getestete GPUs mit Benchmarks.

**Checkliste:**
- [ ] Benchmark auf verfügbaren GPUs
- [ ] Token/s pro GPU + Modell-Kombination
- [ ] VRAM-Empfehlungen tabellarisch
- [ ] In README einbetten oder als docs/GPU-MATRIX.md
