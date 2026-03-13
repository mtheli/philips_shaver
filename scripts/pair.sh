#!/usr/bin/env bash
# Philips Shaver BLE Pairing Script
# Scans for Philips shavers/groomers, pairs and trusts them for Home Assistant.
#
# Usage: ./scripts/pair.sh [MAC_ADDRESS]
#   If no MAC is given, scans for nearby Philips devices and lets you choose.

set -euo pipefail

SCAN_SECONDS=10
PHILIPS_SERVICE_UUID="8d560100-3cb9-4387-a7e8-b79d826a7025"

# --- colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*" >&2; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*" >&2; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*" >&2; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- pre-checks ---
if ! command -v bluetoothctl &>/dev/null; then
    err "bluetoothctl not found. Install bluez or run this on your Home Assistant host."
    exit 1
fi

# Check if bluetooth is powered on
if ! bluetoothctl show 2>/dev/null | grep -q "Powered: yes"; then
    warn "Bluetooth adapter is not powered on. Attempting to power on..."
    bluetoothctl power on 2>/dev/null || true
    sleep 1
    if ! bluetoothctl show 2>/dev/null | grep -q "Powered: yes"; then
        err "Could not power on Bluetooth adapter."
        exit 1
    fi
    ok "Bluetooth adapter powered on."
fi

# --- functions ---

find_philips_devices() {
    # Returns lines of: MAC<TAB>NAME  (stdout only)
    bluetoothctl devices 2>/dev/null | while read -r _ mac name; do
        if bluetoothctl info "$mac" 2>/dev/null | grep -qi "$PHILIPS_SERVICE_UUID"; then
            echo -e "${mac}\t${name}"
        fi
    done
}

scan_for_devices() {
    info "Scanning for Philips BLE devices (${SCAN_SECONDS}s)..."
    echo "    Make sure your shaver is turned on or on its charging stand." >&2
    echo "" >&2

    # Scan — all output to stderr (display only)
    bluetoothctl --timeout "$SCAN_SECONDS" scan on 2>/dev/null | \
        grep --line-buffered -i "philips\|shaver\|NEW" | \
        sed 's/^/    /' >&2 &
    local scan_pid=$!
    wait "$scan_pid" 2>/dev/null || true
    echo "" >&2
}

is_paired() {
    bluetoothctl info "$1" 2>/dev/null | grep -q "Paired: yes"
}

is_trusted() {
    bluetoothctl info "$1" 2>/dev/null | grep -q "Trusted: yes"
}

unpair_device() {
    local mac=$1
    info "Removing existing pairing for $mac..."
    bluetoothctl remove "$mac" 2>/dev/null || true
    sleep 2
    # Rescan to rediscover the device
    bluetoothctl --timeout 5 scan on 2>/dev/null > /dev/null || true
    ok "Previous pairing removed."
}

pair_device() {
    local mac=$1
    local name=$2

    echo "" >&2
    echo -e "${BOLD}=== Pairing ${name} (${mac}) ===${NC}" >&2
    echo "" >&2

    if is_paired "$mac" && is_trusted "$mac"; then
        ok "Already paired and trusted. Nothing to do."
        return 0
    fi

    if is_paired "$mac"; then
        warn "Device is paired but not trusted."
        read -rp "    Re-pair from scratch? [y/N] " answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            unpair_device "$mac"
        else
            info "Trusting device..."
            bluetoothctl trust "$mac" 2>/dev/null
            ok "Device trusted."
            return 0
        fi
    fi

    # Pair — Philips shavers require LE Secure Connections (agent KeyboardDisplay)
    info "Pairing with $mac..."
    echo "    This may take a few seconds..." >&2

    local pair_output
    pair_output=$( {
        echo "agent KeyboardDisplay"
        sleep 0.5
        echo "default-agent"
        sleep 0.5
        echo "pair $mac"
        # LE Secure Connections pairing + GATT discovery takes several seconds
        sleep 15
        echo "quit"
    } | bluetoothctl 2>&1 ) || true

    if echo "$pair_output" | grep -q "Pairing successful"; then
        ok "Pairing successful!"
    elif is_paired "$mac"; then
        ok "Pairing successful!"
    else
        local fail_reason
        fail_reason=$(echo "$pair_output" | grep -oP "Failed to pair: \K.*" || echo "unknown")
        err "Pairing failed: $fail_reason"
        echo "" >&2
        if echo "$fail_reason" | grep -qi "AuthenticationFailed"; then
            echo "    The shaver may have a stale bond from a previous pairing." >&2
            echo "    Try: turn the shaver off, wait a few seconds, turn it back on." >&2
            echo "    If that doesn't help, factory-reset the shaver's Bluetooth." >&2
        else
            echo "    Make sure:" >&2
            echo "    1. Shaver is turned on or on charging stand" >&2
            echo "    2. Shaver is NOT connected to a phone" >&2
            echo "       (unpair from GroomTribe/OneBlade app first)" >&2
            echo "    3. Shaver is within Bluetooth range" >&2
        fi
        return 1
    fi

    # Trust
    info "Trusting device for auto-reconnection..."
    bluetoothctl trust "$mac" 2>/dev/null
    ok "Device trusted."

    # Disconnect (HA will reconnect on its own)
    bluetoothctl disconnect "$mac" 2>/dev/null || true

    echo "" >&2
    ok "${name} is ready for Home Assistant!"
}

# --- main ---

echo "" >&2
echo -e "${BOLD}Philips Shaver BLE Pairing${NC}" >&2
echo "────────────────────────────────────" >&2
echo "" >&2

# If MAC provided as argument, pair directly
if [[ ${1:-} =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
    mac="${1^^}"  # uppercase
    name=$(bluetoothctl info "$mac" 2>/dev/null | grep "Name:" | sed 's/.*Name: //')
    name=${name:-"Unknown Device"}
    pair_device "$mac" "$name"
    exit $?
fi

# Scan, then find Philips devices from bluetoothctl's device cache
scan_for_devices
devices=$(find_philips_devices)

if [[ -z "$devices" ]]; then
    warn "No Philips devices found."
    echo "" >&2
    echo "Troubleshooting:" >&2
    echo "  1. Make sure the shaver is turned on or on its charging stand" >&2
    echo "  2. Move closer to the Bluetooth adapter" >&2
    echo "  3. Unpair the shaver from your phone first" >&2
    echo "  4. Try running the scan again" >&2
    echo "" >&2
    echo "You can also pair manually:" >&2
    echo "  $0 AA:BB:CC:11:22:33" >&2
    exit 1
fi

# Display found devices
echo -e "${BOLD}Found Philips devices:${NC}" >&2
echo "" >&2

declare -a macs=()
declare -a names=()
i=1
while IFS=$'\t' read -r mac name; do
    status_text=""
    if is_paired "$mac" && is_trusted "$mac"; then
        status_text=" ${GREEN}(paired & trusted)${NC}"
    elif is_paired "$mac"; then
        status_text=" ${YELLOW}(paired, not trusted)${NC}"
    fi

    echo -e "  ${BOLD}${i})${NC} ${name} (${mac})${status_text}" >&2
    macs+=("$mac")
    names+=("$name")
    ((i++))
done <<< "$devices"

echo "" >&2

if [[ ${#macs[@]} -eq 1 ]]; then
    read -rp "Pair this device? [Y/n] " answer
    if [[ "$answer" =~ ^[Nn]$ ]]; then
        echo "Cancelled." >&2
        exit 0
    fi
    pair_device "${macs[0]}" "${names[0]}"
else
    echo "  a) Pair all devices" >&2
    echo "" >&2
    read -rp "Select device (1-${#macs[@]}, a=all): " choice

    if [[ "$choice" == "a" || "$choice" == "A" ]]; then
        for idx in "${!macs[@]}"; do
            pair_device "${macs[$idx]}" "${names[$idx]}"
        done
    elif [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#macs[@]} )); then
        idx=$((choice - 1))
        pair_device "${macs[$idx]}" "${names[$idx]}"
    else
        err "Invalid selection."
        exit 1
    fi
fi

echo "" >&2
echo "────────────────────────────────────" >&2
echo -e "${BOLD}Next steps:${NC}" >&2
echo "  1. Go to Home Assistant → Settings → Devices & Services" >&2
echo "  2. The shaver should appear under 'Discovered'" >&2
echo "  3. Or click 'Add Integration' → 'Philips Shaver'" >&2
echo "" >&2
