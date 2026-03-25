#!/usr/bin/env bash
# gpu-detect.sh — GPU detection for RAG-Chat installer
# Outputs JSON. Used by install.sh and admin panel.
# Exit codes: 0 = success, 1 = error

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

recommend_model() {
    local vram_mb="${1:-0}"
    local ram_gb="${2:-0}"
    local mode="${3:-cpu}"

    if [[ "$mode" == "nvidia" || "$mode" == "amd" ]]; then
        if   (( vram_mb >= 48000 )); then echo "llama3.1:70b-instruct-q5_K_M"
        elif (( vram_mb >= 24000 )); then echo "mixtral:8x7b-instruct-v0.1-q5_K_M"
        elif (( vram_mb >= 12000 )); then echo "llama3.1:8b-instruct-q8_0"
        elif (( vram_mb >=  6000 )); then echo "llama3.1:8b-instruct-q5_K_M"
        elif (( vram_mb >=  4000 )); then echo "llama3.1:8b-instruct-q4_K_M"
        else                               echo "llama3.2:1b"
        fi
    else
        # CPU — use RAM
        local ram_int="${ram_gb%.*}"
        if   (( ram_int >= 16 )); then echo "llama3.1:8b-instruct-q4_K_M"
        elif (( ram_int >=  8 )); then echo "llama3.2:3b"
        else                           echo "llama3.2:1b"
        fi
    fi
}

json_escape() {
    # minimal JSON string escaping
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

# ---------------------------------------------------------------------------
# NVIDIA
# ---------------------------------------------------------------------------

detect_nvidia() {
    command -v nvidia-smi &>/dev/null || return 1

    local csv
    csv=$(nvidia-smi \
        --query-gpu=index,name,memory.total,memory.used,memory.free,driver_version,temperature.gpu \
        --format=csv,noheader,nounits 2>/dev/null) || return 1

    [[ -z "$csv" ]] && return 1

    local gpus_json=""
    local max_vram=0
    local first=1

    while IFS=',' read -r idx name total used free driver temp; do
        idx="${idx// /}"
        name="${name## }"; name="${name%% }"
        total="${total// /}"
        used="${used// /}"
        free="${free// /}"
        driver="${driver// /}"
        temp="${temp// /}"

        (( total > max_vram )) && max_vram=$total

        local gpu_entry
        gpu_entry=$(printf '{"index":%s,"name":"%s","vram_total_mb":%s,"vram_used_mb":%s,"vram_free_mb":%s,"driver_version":"%s","temperature_c":%s}' \
            "$idx" "$(json_escape "$name")" "$total" "$used" "$free" \
            "$(json_escape "$driver")" "${temp:-null}")

        if [[ $first -eq 1 ]]; then
            gpus_json="$gpu_entry"
            first=0
        else
            gpus_json="$gpus_json,$gpu_entry"
        fi
    done <<< "$csv"

    local model
    model=$(recommend_model "$max_vram" 0 "nvidia")
    local cuda_devices="${CUDA_VISIBLE_DEVICES:-all}"

    printf '{"mode":"nvidia","gpus":[%s],"recommendation":{"model":"%s","reason":"%d MB VRAM"},"cuda_visible_devices":"%s"}' \
        "$gpus_json" "$model" "$max_vram" "$cuda_devices"
    return 0
}

# ---------------------------------------------------------------------------
# AMD
# ---------------------------------------------------------------------------

detect_amd() {
    # Try rocm-smi
    if command -v rocm-smi &>/dev/null; then
        local info
        info=$(rocm-smi --showmeminfo vram 2>/dev/null | grep -E "GPU|vram" || true)
        if [[ -n "$info" ]]; then
            printf '{"mode":"amd","gpus":[],"note":"AMD GPU detected via rocm-smi. ROCm required for GPU inference.","recommendation":{"model":"%s","reason":"AMD GPU (ROCm mode)"}}' \
                "$(recommend_model 8000 0 amd)"
            return 0
        fi
    fi

    # sysfs fallback: AMD vendor = 0x1002
    local amd_found=0
    if [[ -d /sys/class/drm ]]; then
        for card in /sys/class/drm/card*/device/vendor; do
            [[ -f "$card" ]] || continue
            local vendor; vendor=$(cat "$card" 2>/dev/null || echo "")
            if [[ "$vendor" == "0x1002" ]]; then
                amd_found=1
                break
            fi
        done
    fi

    if (( amd_found )); then
        local ram_gb
        ram_gb=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo "0")
        local model; model=$(recommend_model 0 "$ram_gb" "cpu")
        printf '{"mode":"amd","gpus":[],"note":"AMD integrated/discrete GPU detected. No ROCm — running CPU mode.","recommendation":{"model":"%s","reason":"AMD GPU without ROCm, using CPU inference"}}' \
            "$model"
        return 0
    fi

    return 1
}

# ---------------------------------------------------------------------------
# CPU fallback
# ---------------------------------------------------------------------------

detect_cpu() {
    local cpu_name="Unknown CPU"
    if [[ -f /proc/cpuinfo ]]; then
        cpu_name=$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | sed 's/^ //')
    fi

    local ram_total_gb="0"
    local ram_available_gb="0"
    if [[ -f /proc/meminfo ]]; then
        ram_total_gb=$(awk '/MemTotal/     {printf "%.1f", $2/1024/1024}' /proc/meminfo)
        ram_available_gb=$(awk '/MemAvailable/ {printf "%.1f", $2/1024/1024}' /proc/meminfo)
    fi

    local ram_int="${ram_total_gb%.*}"
    local model; model=$(recommend_model 0 "${ram_int:-0}" "cpu")

    printf '{"mode":"cpu","gpus":[],"cpu":{"name":"%s","ram_total_gb":%s,"ram_available_gb":%s},"note":"No GPU detected. CPU-only inference (slow).","recommendation":{"model":"%s","reason":"CPU-only, %s GB RAM"}}' \
        "$(json_escape "$cpu_name")" "$ram_total_gb" "$ram_available_gb" \
        "$model" "$ram_total_gb"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    local result

    if result=$(detect_nvidia 2>/dev/null); then
        echo "$result"
        exit 0
    fi

    if result=$(detect_amd 2>/dev/null); then
        echo "$result"
        exit 0
    fi

    detect_cpu
    exit 0
}

main "$@"
