# Architektur — RAG-Chat

## Container-Architektur

### Nginx (Frontend-Proxy)
- Image: `nginx:alpine`
- Exponierter Port: `${HTTP_PORT:-8080}`
- Routing: `/` → Chat-Frontend, `/admin` → Admin-Panel (Basic Auth), `/api/*` → FastAPI Backend
- Statische Dateien: `/frontend/` und `/admin/` gemountet als read-only
- Rate-Limiting: 10 req/s pro IP auf `/api/chat`

### FastAPI Backend
- Image: Custom (`python:3.11-slim`)
- Interner Port: 8000
- Nicht nach außen exponiert
- Async: Uvicorn mit 1 Worker (GPU ist der Bottleneck, nicht CPU)
- Endpoints: Chat (SSE), Upload, Admin-API

### Ollama
- Image: `ollama/ollama`
- Interner Port: 11434
- GPU: `runtime: nvidia`, `NVIDIA_VISIBLE_DEVICES=all`
- Volume: `ollama-models:/root/.ollama`
- Kein externer Zugriff

### ChromaDB
- Image: `chromadb/chroma`
- Interner Port: 8000 (intern remapped auf 8001)
- Volume: `chromadb-data:/chroma/chroma`
- Persistenz: SQLite + HNSW Index auf Disk
- Kein externer Zugriff

## Datenfluss

### Chat-Anfrage
```
User → Nginx → FastAPI POST /api/chat
  → ChromaDB: Similarity Search (Top-K Chunks)
  → Prompt bauen: System-Prompt + Chunks + User-Query
  → Ollama: Generate (Stream)
  → SSE Stream → Nginx → User
```

### Datei-Indexierung
```
Admin legt Datei in /data/knowledge/Ordner/
  → watchdog erkennt neue Datei
  → Parser (PDF/DOCX/TXT/MD/CSV)
  → Chunking (1000 Tokens, 200 Overlap)
  → Embedding via Ollama (nomic-embed-text)
  → ChromaDB: Upsert mit Metadaten (Ordner=Tag, Dateiname, Hash)
  → Log-Eintrag (JSON)
```

### Config-Änderung
```
Admin ändert Setting im Admin-Panel
  → POST /admin/api/config {partial update}
  → Backend: Pydantic-Validierung
  → Snapshot der alten Config erstellen
  → Neue Config schreiben
  → Betroffene Services benachrichtigen (z.B. Ollama Modell wechseln)
```

## RAM-Planung

| Komponente | Minimum | Empfohlen |
|------------|---------|-----------|
| Ollama (8B Modell) | 6 GB | 8 GB |
| ChromaDB (500k Chunks) | 2 GB | 4 GB |
| ChromaDB (2M Chunks) | 8 GB | 10 GB |
| FastAPI Backend | 0.5 GB | 1 GB |
| Nginx | 50 MB | 100 MB |
| **Gesamt (klein)** | **~9 GB** | **~13 GB** |
| **Gesamt (groß, 20 GB Dateien)** | **~15 GB** | **~19 GB** |

## GPU-Nutzung

- Ollama nutzt die GPU für Inferenz (Chat) UND Embeddings
- Embedding und Chat können nicht gleichzeitig laufen (Ollama queued)
- Bei Erstindexierung: GPU ist voll ausgelastet mit Embeddings
- Empfehlung: Erstindexierung vor Produktivbetrieb abschließen

## Sicherheitsmodell

- **Netzwerk:** Nur für lokales Netzwerk gedacht, kein Internet-Exposure
- **Admin:** HTTP Basic Auth (Nginx), Credentials bei Installation gesetzt
- **Chat:** Kein Login, kein Auth — offen für alle im Netzwerk
- **Dateien:** Admin-Upload in Wissensbasis, User-Upload nur temporär
- **Config:** Nur über Admin-Panel oder direkte Dateibearbeitung änderbar
