# Config-Schema — rag-config.json

## Übersicht

Die gesamte Anwendungskonfiguration wird in einer einzigen JSON-Datei gespeichert:  
**Pfad:** `/data/config/rag-config.json`

Beim Start lädt das Backend die Datei und validiert sie mit Pydantic. Fehlende Felder werden mit Standardwerten ergänzt. Ungültige Werte führen zu einem Fehler im Log — die letzte gültige Config wird beibehalten.

## Schema

### ollama

| Feld | Typ | Standard | Beschreibung |
|------|-----|----------|-------------|
| `model` | string | `"llama3.1:8b-instruct-q5_K_M"` | Aktives Ollama-Modell |
| `temperature` | float | `0.7` | Kreativität (0.0–2.0) |
| `top_p` | float | `0.9` | Nucleus Sampling (0.0–1.0) |
| `context_window` | int | `8192` | Max. Kontext-Tokens |
| `system_prompt` | string | *siehe unten* | System-Anweisung für das Modell |

**Standard System-Prompt:**
```
Du bist ein hilfreicher Assistent. Beantworte Fragen basierend auf dem bereitgestellten Kontext. Wenn du die Antwort nicht im Kontext findest, sage es ehrlich.
```

### rag

| Feld | Typ | Standard | Beschreibung |
|------|-----|----------|-------------|
| `embedding_model` | string | `"nomic-embed-text"` | Ollama-Modell für Embeddings |
| `chunk_size` | int | `1000` | Chunk-Größe in Tokens |
| `chunk_overlap` | int | `200` | Überlappung zwischen Chunks |
| `top_k` | int | `5` | Anzahl relevanter Chunks pro Query |
| `knowledge_path` | string | `"/data/knowledge"` | Pfad zur Wissensbasis |
| `supported_formats` | string[] | `["pdf","docx","txt","md","csv"]` | Erlaubte Dateiformate |

### server

| Feld | Typ | Standard | Beschreibung |
|------|-----|----------|-------------|
| `http_port` | int | `8080` | HTTP-Port (Nginx) |
| `admin_path` | string | `"/admin"` | URL-Pfad zum Admin-Panel |
| `max_upload_mb` | int | `10` | Max. Upload-Größe in MB |
| `session_timeout_min` | int | `30` | Timeout für temporäre Uploads |
| `bind_address` | string | `"0.0.0.0"` | Bind-Adresse |

### updates

| Feld | Typ | Standard | Beschreibung |
|------|-----|----------|-------------|
| `auto_update` | bool | `true` | Automatische Updates aktiviert |
| `check_interval` | string | `"daily"` | Prüfintervall: `"daily"`, `"weekly"`, `"never"` |
| `channel` | string | `"stable"` | Update-Kanal: `"stable"`, `"beta"` |

## API-Endpoints

| Method | Pfad | Beschreibung |
|--------|------|-------------|
| GET | `/admin/api/config` | Aktuelle Config lesen |
| POST | `/admin/api/config` | Config aktualisieren (partiell) |
| GET | `/admin/api/config/export` | Download als Datei |
| POST | `/admin/api/config/import` | Config-Datei hochladen |
| POST | `/admin/api/config/snapshot` | Snapshot erstellen |
| GET | `/admin/api/config/snapshots` | Snapshot-Liste |
| POST | `/admin/api/config/restore/{id}` | Snapshot wiederherstellen |

## Snapshots

Bei jeder Änderung wird automatisch ein Snapshot erstellt:  
**Pfad:** `/data/config/snapshots/rag-config_2026-03-25_14-32-00.json`

Maximale Snapshot-Anzahl: 50 (älteste werden automatisch gelöscht).
