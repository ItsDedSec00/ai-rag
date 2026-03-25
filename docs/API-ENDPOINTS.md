# API-Endpoints — RAG-Chat Backend

Basis-URL: `http://<server>:8080/api`

## Chat

### POST /api/chat
Sendet eine Nachricht und streamt die Antwort via SSE.

**Request:**
```json
{
  "message": "Was ist ein Transformator?",
  "session_id": "optional-uuid",
  "uploaded_file_ids": ["uuid-1"]
}
```

**Response:** `text/event-stream`
```
data: {"type": "token", "content": "Ein"}
data: {"type": "token", "content": " Trans"}
data: {"type": "token", "content": "formator"}
data: {"type": "sources", "content": [{"file": "Trafo_Handbuch.pdf", "score": 0.89, "chunk": "Ein Transformator wandelt..."}]}
data: {"type": "done"}
```

### POST /api/upload
Temporärer Datei-Upload als Session-Kontext.

**Request:** `multipart/form-data`
- `file`: Datei (max. 10 MB, Formate: pdf, docx, txt, md, csv)

**Response:**
```json
{
  "file_id": "uuid",
  "filename": "dokument.pdf",
  "chunks": 42,
  "expires_in_min": 30
}
```

## Admin — System

### GET /admin/api/system
System-Informationen.

**Response:**
```json
{
  "gpu": {"name": "NVIDIA RTX 3070 Ti", "vram_total_mb": 8192, "vram_used_mb": 4200, "temperature_c": 62, "driver": "535.183.01"},
  "ram": {"total_mb": 32768, "used_mb": 18432},
  "disk": {"total_gb": 500, "used_gb": 120},
  "uptime_seconds": 86400,
  "version": "v1.2.0",
  "requests": {"total": 1547, "today": 89, "last_hour": 12}
}
```

## Admin — Modelle

### GET /admin/api/models
Installierte Ollama-Modelle.

### POST /admin/api/models/pull
Modell herunterladen. Response: SSE mit Download-Fortschritt.

### POST /admin/api/models/active
Aktives Modell wechseln.

## Admin — RAG / Indexierung

### GET /admin/api/files
Indexierte Dateien auflisten.

### GET /admin/api/indexing/status
Aktueller Indexierungs-Fortschritt.

**Response:**
```json
{
  "running": true,
  "total_files": 847,
  "files_done": 312,
  "total_chunks": 124000,
  "chunks_done": 45600,
  "current_file": "Schaltanlagen_Handbuch.docx",
  "eta_seconds": 1840,
  "chunks_per_second": 42.5,
  "errors": [{"file": "corrupt.pdf", "error": "PDF parsing failed"}]
}
```

### POST /admin/api/files/upload
Datei in Wissensbasis hochladen.

### DELETE /admin/api/files/{id}
Datei aus Wissensbasis und ChromaDB entfernen.

### GET /admin/api/files/{id}/chunks
Chunk-Vorschau einer Datei.

## Admin — Config

### GET /admin/api/config
Aktuelle Konfiguration.

### POST /admin/api/config
Config aktualisieren (partielles Update, Pydantic-validiert).

### GET /admin/api/config/export
Config als Datei herunterladen.

### POST /admin/api/config/import
Config-Datei hochladen und anwenden.

### POST /admin/api/config/snapshot
Manuellen Snapshot erstellen.

### GET /admin/api/config/snapshots
Snapshot-Liste.

### POST /admin/api/config/restore/{snapshot_id}
Snapshot wiederherstellen.

## Admin — Updates

### GET /admin/api/updates/status
Versionsstatus (lokal vs. GitHub).

### POST /admin/api/updates/trigger
Manuelles Update starten.

### GET /admin/api/updates/log
Update-Verlauf.

### POST /admin/api/updates/rollback
Auf vorherige Version zurückrollen.

## Admin — Performance

### GET /admin/api/performance
Aktuelle Performance-Metriken.

### GET /admin/api/performance/history?hours=24
Historische Metriken.
