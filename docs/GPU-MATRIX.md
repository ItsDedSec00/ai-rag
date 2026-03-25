# GPU-Kompatibilitätsmatrix

## Getestete Konfigurationen

| GPU | VRAM | Empfohlene Modelle | ~Token/s (Chat) | ~Chunks/s (Embedding) |
|-----|------|--------------------|-----------------|----------------------|
| RTX 3060 | 12 GB | Llama 3.1 8B Q5_K_M | ~35 | ~80 |
| RTX 3070 | 8 GB | Llama 3.1 8B Q4_K_M | ~40 | ~90 |
| RTX 3070 Ti | 8 GB | Llama 3.1 8B Q5_K_M | ~45 | ~100 |
| RTX 3080 | 10 GB | Llama 3.1 8B Q8_0 | ~55 | ~120 |
| RTX 3090 | 24 GB | Llama 3.1 70B Q4_K_M | ~15 | ~150 |
| RTX 4060 | 8 GB | Llama 3.1 8B Q5_K_M | ~50 | ~110 |
| RTX 4070 | 12 GB | Llama 3.1 8B Q8_0 | ~65 | ~140 |
| RTX 4080 | 16 GB | Llama 3.1 8B Q8_0 | ~80 | ~170 |
| RTX 4090 | 24 GB | Llama 3.1 70B Q4_K_M | ~25 | ~200 |
| A4000 | 16 GB | Llama 3.1 8B Q8_0 | ~45 | ~100 |

> **Hinweis:** Werte sind Schätzungen und variieren je nach System-RAM, Treiber-Version und gleichzeitiger Last. Tatsächliche Benchmarks werden in Phase 5 (DOC-02) erstellt.

## Mindestanforderungen

- **GPU:** Nvidia mit CUDA-Support und ≥6 GB VRAM
- **Treiber:** Nvidia Driver ≥525
- **RAM:** ≥16 GB (≥32 GB bei >10 GB Wissensbasis)
- **Disk:** ≥50 GB frei (Modelle + ChromaDB Index)
- **OS:** Ubuntu 22.04 / 24.04 LTS

## CPU-Fallback

Ohne Nvidia-GPU läuft Ollama im CPU-Modus. Performance:
- Chat: ~5 Token/s (Llama 3.1 8B Q4_K_M)
- Embedding: ~10 Chunks/s
- Nutzbar, aber langsam. Erstindexierung von 20 GB kann >24h dauern.

## Erstindexierungs-Zeiten (geschätzt)

| Datenmenge | Chunks (ca.) | RTX 3070 Ti | RTX 4090 | CPU-only |
|------------|-------------|-------------|----------|----------|
| 1 GB | ~100k | ~17 min | ~8 min | ~2.5 h |
| 5 GB | ~500k | ~1.5 h | ~42 min | ~14 h |
| 10 GB | ~1M | ~2.8 h | ~1.4 h | ~28 h |
| 20 GB | ~2M | ~5.5 h | ~2.8 h | ~55 h |
