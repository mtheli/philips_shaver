# ESP Bridge

Everything needed to turn an ESP32 into a Bluetooth bridge for the Philips
Shaver integration. The ESP handles the BLE connection to the shaver
(including LE Secure Connections pairing) and exposes it to Home Assistant
via ESPHome service calls and events.

Use this when Home Assistant itself has no Bluetooth adapter in range of
the shaver — or when you prefer a dedicated, always-connected bridge.

For end-to-end setup instructions (flashing, integration configuration,
multi-device setups) see [`docs/ESP_BRIDGE_SETUP.md`](../docs/ESP_BRIDGE_SETUP.md).

## Contents

| File | Description |
|------|-------------|
| [`components/philips_shaver/`](components/philips_shaver/) | The C++ ESPHome external component. This is the actual bridge implementation — BLE client, GATT read/write/subscribe, pairing, and the HA event/service interface. |
| [`atom-lite.yaml`](atom-lite.yaml) | Ready-to-flash config for the M5Stack Atom Lite. Also serves as a `bluetooth_proxy` for other BLE devices in parallel. |
| [`esp32-generic.yaml`](esp32-generic.yaml) | Generic ESP32 dev-board config (`esp32dev`). Use as a starting point for other boards. |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history for the external component. |

## Requirements

- **ESP-IDF framework** (not Arduino). Arduino's precompiled Bluedroid
  has `BTA_GATTC_MAX_CACHE_CHAR=40` and `BTA_GATTC_NOTIF_REG_MAX=5`,
  both too small for the shaver's ~66 attributes and 17+ subscriptions.
  The YAMLs set the larger limits via `sdkconfig_options`.
- An ESP32 within BLE range of the shaver (ideally RSSI better than
  -85 dBm). RSSI around -100 dBm is the noise floor — pairing/connection
  will fail there.

## Mode A vs Mode B

Two ways to wire the bridge to a shaver, picked per `philips_shaver:` entry
in YAML:

### Mode A — Fixed MAC (`ble_client_id:`)

Classic setup. You declare a `ble_client:` block with the shaver's MAC,
and the `philips_shaver:` entry references it via `ble_client_id`. The
bridge always targets that MAC. Pairing happens once — manually via
`pair.sh` from the host, or by re-flashing after a factory reset.

```yaml
ble_client:
  - mac_address: "EC:EC:66:27:F0:ED"
    id: shaver_ble
    auto_connect: true

philips_shaver:
  - ble_client_id: shaver_ble
    bridge_id: "shaver"
```

Use this when:
- You already know the shaver's MAC.
- You want a deterministic slot-to-shaver mapping (multi-bridge setups).
- You don't mind the one-time `pair.sh` round-trip.

### Mode B — Auto-Discovery (no `ble_client_id:`)

The `philips_shaver:` entry runs as a self-contained BLE client. On boot,
if no MAC is pinned and NVS is empty, the bridge waits for HA to call
`ble_pair_mode`. It then scans for the universal Philips Shaver Platform
Service UUID (`8d560100`), bonds to the first match (or to a specific MAC
if you used `ble_pair_mac`), and persists the bonded MAC to NVS so future
boots auto-reconnect.

```yaml
philips_shaver:
  - bridge_id: "shaver"
    # No ble_client_id, no mac_address → auto-discovery via HA setup dialog

  # Or with a YAML-pinned MAC (skips pair-mode, uses NVS only as a marker):
  - bridge_id: "oneblade"
    mac_address: "D2:EC:C6:98:B9:67"
```

The HA integration's setup dialog detects Mode B unpaired bridges and
walks you through the pair-mode flow — no terminal access needed.

Use this when:
- You don't know the MAC up front.
- You're running a Bluetooth-Proxy-only setup (HA has no Bluetooth
  adapter that can pair) and want a dedicated bridge.
- You want to swap shavers without re-flashing.

### Mode B — re-pairing a different shaver

To bond a different shaver to a Mode B bridge that already has one
bonded, **first call `ble_unpair`** (HA → Developer Tools → Services →
`esphome.<atom_name>_ble_unpair_<bridge_id>`). The bridge clears NVS +
removes the BLE bond, drops back to UUID-scan mode, and waits for the
next `ble_pair_mode`. Removing the integration entry in HA does the
unpair automatically (`async_remove_entry`).

Mode A's YAML-pinned MAC ignores `ble_unpair` — the brush re-bonds on
the next connect because the YAML target stays.

## HA Services exposed by the bridge

Each bridge instance registers the same service set, suffixed with
`bridge_id` if set (`ble_read_char_<bridge_id>` etc.).

| Service | Direction | When |
|---------|-----------|------|
| `ble_read_char(service_uuid, char_uuid)` | HA → Bridge | Read one char, fires `..._ble_data` event with payload |
| `ble_subscribe(service_uuid, char_uuid)` | HA → Bridge | Enable notify/indicate, payloads stream as `..._ble_data` events |
| `ble_unsubscribe(service_uuid, char_uuid)` | HA → Bridge | Disable notify |
| `ble_write_char(service_uuid, char_uuid, data)` | HA → Bridge | Write hex string |
| `ble_set_throttle(throttle_ms)` | HA → Bridge | Per-char min interval between notify events |
| `ble_get_info()` | HA → Bridge | Snapshot (`mode`, `identity_source`, `pair_capable`, `paired`, `mac`, `version`, …) — fires `..._ble_status` with `status=info` |
| `ble_pair_mode(enabled, timeout_s)` | HA → Bridge | **Mode B only.** Arm/disarm UUID-scan for `timeout_s` (default 60). Fires `pair_mode_armed`, then `pair_complete` or `pair_timeout` |
| `ble_unpair()` | HA → Bridge | **Mode B only.** Remove bond + clear NVS identity. Drains 2 s, then fires `unpaired` |
| `ble_scan(timeout_s)` | HA → Bridge | **Mode B only.** Discovery without connect. Fires `scan_result` per unique MAC, then `scan_complete` |
| `ble_pair_mac(mac, timeout_s)` | HA → Bridge | **Mode B only.** Targeted pair to one specific MAC (skip UUID filter) |

Mode B services are silently no-op'd by the Coordinator on a Mode A
bridge (it logs a warning). Old bridges (< v1.8.0) don't register them
at all and the call returns ServiceNotFound — the integration handles
that gracefully.

## Version pinning

The integration enforces a minimum bridge version (`MIN_BRIDGE_VERSION`
in `custom_components/philips_shaver/const.py`). On version mismatch
Home Assistant shows a Repairs notification asking you to reflash.
Always flash a matching pair — the ref in your YAML's
`external_components:` should point at the same tag/commit as the
integration version.
