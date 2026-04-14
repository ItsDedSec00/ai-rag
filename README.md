# RAG-Chat

Lokale, selbstgehostete KI-Chat-Anwendung mit Wissensdatenbank (RAG) für Linux-Server mit Nvidia-GPUs. Kein Internet erforderlich nach der Installation.

**Entwickelt von [David Dülle](https://duelle.org)**

---

## Inhalt

- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Erster Start](#erster-start)
- [Admin-Panel](#admin-panel)
- [Wissensdatenbank befüllen](#wissensdatenbank-befüllen)
- [API-Zugang (OpenAI-kompatibel)](#api-zugang-openai-kompatibel)
- [Cloudflare Tunnel (externer Zugriff)](#cloudflare-tunnel-externer-zugriff)
- [Update](#update)
- [Deinstallation](#deinstallation)
- [Troubleshooting](#troubleshooting)

---

## Voraussetzungen

| Komponente | Minimum | Empfohlen |
|-----------|---------|-----------|
| Betriebssystem | Ubuntu 20.04 / Debian 11 | Ubuntu 22.04 LTS |
| RAM | 8 GB | 16 GB+ |
| Speicher | 20 GB frei | 50 GB+ |
| Docker | 24.0+ | aktuell |
| Docker Compose | 2.20+ | aktuell |
| GPU (optional) | Nvidia mit 4 GB VRAM | 8 GB+ VRAM |

Ohne GPU läuft die Anwendung im CPU-Modus — Antworten sind deutlich langsamer.

---

## Installation

```bash
# Repository klonen
git clone https://github.com/ItsDedSec00/ai-rag.git
cd rag-chat

# Installer ausführen
sudo bash install.sh
```

Der Installer erledigt automatisch:
- Docker & Docker Compose prüfen/installieren
- GPU-Erkennung (Nvidia)
- `.env` Datei erstellen
- Docker-Container starten
- Nginx Basic Auth einrichten
- Systemd-Dienste für Autostart registrieren

**Installationsdauer:** ca. 5–15 Minuten (je nach Internetgeschwindigkeit für Modell-Download)

---

## Erster Start

Nach der Installation ist die Anwendung erreichbar unter:

```
http://<server-ip>
```

Beim ersten Start wird automatisch das Standardmodell heruntergeladen. Dies kann einige Minuten dauern — der Fortschritt ist im Admin-Panel unter **Modelle** sichtbar.

---

## Admin-Panel

Das Admin-Panel ist erreichbar unter:

```
http://<server-ip>/admin
```

**Standard-Zugangsdaten** (werden bei Installation gesetzt):
- Benutzername: `admin`
- Passwort: `admin`

> ⚠️ Das Passwort sollte nach der ersten Anmeldung geändert werden.

### Tabs im Admin-Panel

| Tab | Funktion |
|-----|----------|
| **Dashboard** | System-Status, RAM, CPU, GPU, Anfragen-Statistik |
| **Modelle** | KI-Modell wechseln, herunterladen, Generierungsparameter |
| **Dateien** | Wissensdatenbank verwalten (Upload, Löschen) |
| **Einstellungen** | RAG-Parameter, Chat-Einstellungen, Branding |
| **Performance** | Anfragen-Verlauf, Token/s, Latenz-Statistiken |
| **Updates** | Versionsstand prüfen, Update auslösen |
| **Erweiterungen** | Zukünftige Erweiterungen (in Entwicklung) |
| **API-Schlüssel** | API-Schlüssel für die OpenAI-kompatible Schnittstelle verwalten |

---

## Wissensdatenbank befüllen

Dokumente können auf zwei Wegen hinzugefügt werden:

### 1. Über das Admin-Panel (empfohlen)
Admin-Panel → **Dateien** → Datei hochladen

Unterstützte Formate: `PDF`, `DOCX`, `TXT`, `MD`, `CSV`

### 2. Direkt im Dateisystem
Dateien in den `data/knowledge/` Ordner auf dem Server legen. Der Indexer erkennt neue Dateien automatisch und verarbeitet sie.

```bash
cp meine-dokumente/*.pdf /pfad/zu/rag-chat/data/knowledge/
```

Die Verarbeitung (Indexierung) läuft im Hintergrund. Fortschritt ist im Dashboard sichtbar.

---

## API-Zugang (OpenAI-kompatibel)

RAG-Chat stellt eine OpenAI-kompatible API bereit. Andere Anwendungen (z. B. eigene Webapps, n8n, LangChain, Open WebUI) können RAG-Chat damit wie ein normales OpenAI-Modell ansprechen — inklusive Wissensdatenbank.

### API-Schlüssel erstellen

1. Admin-Panel öffnen → Tab **API-Schlüssel**
2. „Neuen Schlüssel erstellen" klicken und einen Namen vergeben
3. Den angezeigten Schlüssel (`rck-...`) kopieren — er wird nur einmal angezeigt

### Endpunkte

| Methode | Pfad | Funktion |
|---------|------|----------|
| `GET` | `/v1/models` | Verfügbares Modell abfragen |
| `POST` | `/v1/chat/completions` | Chat-Anfrage (mit RAG-Kontext) |

### Verwendung

**Python (openai SDK):**
```python
from openai import OpenAI

client = OpenAI(
    api_key="rck-...",
    base_url="http://<server-ip>:8080/v1"
)

resp = client.chat.completions.create(
    model="llama3.2:1b",
    messages=[{"role": "user", "content": "Was steht in meinen Dokumenten?"}]
)
print(resp.choices[0].message.content)
```

**curl:**
```bash
curl http://<server-ip>:8080/v1/chat/completions \
  -H "Authorization: Bearer rck-..." \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"Hallo"}]}'
```

**Streaming** wird mit `"stream": true` im Request-Body aktiviert und liefert Token-für-Token im OpenAI SSE-Format.

> Die RAG-Wissensdatenbank wird automatisch durchsucht. Quellen werden als `x_rag_sources` im Response-Objekt mitgeliefert (von Standard-OpenAI-Clients ignoriert).

---

## Cloudflare Tunnel (externer Zugriff)

Mit einem Cloudflare Tunnel kann RAG-Chat sicher über das Internet erreichbar gemacht werden — ohne Port-Weiterleitung oder selbstsignierte Zertifikate. Der Tunnel verschlüsselt die Verbindung über Cloudflares Netzwerk.

### Einrichtung

1. Unter [one.dash.cloudflare.com](https://one.dash.cloudflare.com) anmelden → **Zero Trust → Networks → Tunnels**
2. „Create a tunnel" → Name: `rag-chat`
3. Den angezeigten Token kopieren (aus dem `cloudflared service install ...`-Befehl)
4. Token in der `.env` Datei auf dem Server eintragen:
   ```bash
   CLOUDFLARE_TUNNEL_TOKEN=eyJ...
   ```
5. Im Cloudflare-Dashboard unter **Public Hostname** eine Subdomain anlegen:
   - Subdomain: z. B. `chat.meineschule.de`
   - Service: `http://nginx:80`
6. Tunnel starten:
   ```bash
   docker compose --profile tunnel up -d
   ```

Danach ist RAG-Chat (und die API) unter `https://chat.meineschule.de` erreichbar.

> ⚠️ Die API-Schlüssel schützen den `/v1/`-Endpunkt. Stelle sicher, dass mindestens ein Schlüssel erstellt ist, bevor der Tunnel aktiviert wird.

---

## Update

### Automatisch
Updates werden täglich automatisch geprüft und im Admin-Panel unter **Updates** angezeigt. Ein Update kann dort mit einem Klick ausgelöst werden.

### Manuell
```bash
cd /pfad/zu/rag-chat
bash update.sh
```

### Rollback
```bash
bash update.sh --rollback
```

---

## Deinstallation

```bash
cd /pfad/zu/rag-chat
bash uninstall.sh
```

> ⚠️ Die Wissensdatenbank und alle Einstellungen werden dabei gelöscht.

---

## Troubleshooting

### Container startet nicht

```bash
cd /pfad/zu/rag-chat
docker compose logs backend
docker compose logs ollama
```

### GPU wird nicht erkannt

```bash
# Nvidia-Treiber prüfen
nvidia-smi

# GPU-Modus manuell setzen
echo "gpu" > .gpu-mode
docker compose restart backend
```

### Modell lädt nicht / Antworten sehr langsam

- RAM-Auslastung im Dashboard prüfen (Admin-Panel → Dashboard)
- Kleineres Modell wählen (Admin-Panel → Modelle)
- Im CPU-Modus sind Antwortzeiten von 30–120 Sekunden normal

### Wissensdatenbank wird nicht indexiert

```bash
# Indexer-Status prüfen
docker compose logs backend | grep indexer

# Container neu starten
docker compose restart backend
```

### Admin-Panel nicht erreichbar

```bash
# Nginx-Status prüfen
docker compose logs nginx

# Container-Status
docker compose ps
```

### Alle Container neu starten (Einstellungen bleiben erhalten)

```bash
docker compose restart
```

### Komplett neu aufbauen (Einstellungen bleiben erhalten)

```bash
docker compose down && docker compose up -d --build
```

> ⚠️ **Niemals** `docker compose down -v` verwenden — das löscht alle Daten und Einstellungen.

---

## Technischer Stack

- **Backend:** Python 3.11, FastAPI, ChromaDB, Ollama
- **Frontend:** Vanilla HTML/CSS/JS (kein Build-Step)
- **Infrastruktur:** Docker Compose, Nginx

---

## Lizenz

Siehe [LICENSE](LICENSE)

---

© 2026 [David Dülle](https://duelle.org)
