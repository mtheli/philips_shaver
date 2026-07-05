# ESP Bridge

Everything needed to turn an ESP32 into a Bluetooth bridge for the Philips
Shaver integration. The ESP handles the BLE connection to the shaver
(including LE Secure Connections pairing) and exposes it to Home Assistant
via ESPHome service calls and events.

Use this when Home Assistant itself has no Bluetooth adapter in range of
the shaver, when you want to monitor multiple devices from one bridge, or
when you prefer a dedicated, always-connected bridge.

Side by side with the Direct BLE path (Home Assistant's own Bluetooth
adapter), which the integration uses when no bridge is configured:

```text
  Direct BLE                            ESP bridge

  ┌─────────────────────┐              ┌─────────────────────┐
  │   Home Assistant    │              │   Home Assistant    │
  │  ┌───────────────┐  │              │  ┌───────────────┐  │
  │  │  integration  │  │              │  │  integration  │  │
  │  └───────┬───────┘  │              │  └───────┬───────┘  │
  │   bleak / BlueZ     │              │  ESPHome native API │
  │  ┌───────┴───────┐  │              └──────────┼──────────┘
  │  │  BT adapter   │  │                    Wi-Fi│ services ▼
  │  └───────┬───────┘  │                         │ events   ▲
  └──────────┼──────────┘              ┌──────────┴──────────┐
             │ BLE                     │        ESP32        │
             ▼                         │   philips_shaver    │
      ┌────────────┐                   │  BLE client — owns  │
      │   shaver   │                   │  connection + bond  │
      └────────────┘                   └─────┬─────────┬─────┘
                                          BLE│          │BLE
                                             ▼          ▼
                                       ┌──────────┐ ┌──────────┐
                                       │  shaver  │ │ OneBlade │
                                       └──────────┘ └──────────┘
```

- **Where the BLE link lives:** Direct BLE ties the connection to the HA
  host's adapter — the shaver must be in radio range of your server. With
  the bridge, the BLE link terminates on the ESP32, which you can place
  anywhere with Wi-Fi coverage (e.g. in the bathroom).
- **Who holds the bond:** on the bridge path the ESP stores the LE bond
  in its own flash (NVS), independent of Home Assistant restarts,
  container rebuilds, or the host's BlueZ state.
- **What travels over Wi-Fi:** plain ESPHome traffic — HA calls services
  (`ble_read_char_<bridge_id>`, …) and the bridge answers with events.
  No Bluetooth stack is involved on the HA side at all.
- **Multi-device:** one bridge serves several devices, each as its own
  slot with its own service set (e.g. shaver + OneBlade).

For end-to-end setup instructions (configuration paths, flashing, multi-device
setups, troubleshooting) see [`docs/ESP_BRIDGE_SETUP.md`](../docs/ESP_BRIDGE_SETUP.md).

## Contents

| File | Description |
|------|-------------|
| [`components/philips_shaver/`](components/philips_shaver/) | The C++ ESPHome external component. This is the actual bridge implementation — BLE client, GATT read/write/subscribe, pairing, and the HA event/service interface. |
| [`atom-lite.yaml`](atom-lite.yaml) | Ready-to-flash config for the M5Stack Atom Lite, configured for **two** devices via one bridge (e.g. shaver + OneBlade). Raises `BTA_GATTC_NOTIF_REG_MAX` and `BTA_GATTC_MAX_CACHE_CHAR` accordingly. Also runs `bluetooth_proxy` for other BLE devices in parallel. |
| [`esp32-generic.yaml`](esp32-generic.yaml) | Generic ESP32 dev-board config (`esp32dev`), single device. Use as a starting point for other boards. |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history for the external component. |

## Requirements

- **ESP-IDF framework** (not Arduino). Arduino's precompiled Bluedroid
  has `BTA_GATTC_MAX_CACHE_CHAR=40` and `BTA_GATTC_NOTIF_REG_MAX=5`,
  both too small for the shaver's ~66 attributes and 17+ subscriptions
  per device. The YAMLs set the larger limits via `sdkconfig_options`.
- An ESP32 within BLE range of the shaver (ideally RSSI better than
  -85 dBm). RSSI around -100 dBm is the noise floor — pairing/connection
  will fail there.

## Pipelined GATT reads (bridge ≥ 1.10.0)

How the integration polls characteristics depends on the bridge firmware
version, which the bridge reports in its status events:

- **Bridge ≥ 1.10.0 (pipelined):** Home Assistant fires the whole poll
  batch at once. The firmware serialises everything through a single
  ATT-operation scheduler — only one GATT read/write/subscribe is in
  flight on the BLE link at any time; the rest wait in the bridge's
  pending-calls queue and are drained back-to-back as each operation
  completes. Reads deferred behind connection setup (service discovery,
  subscription writes) simply wait in the queue instead of timing out
  individually, so a poll batch completes without lost values.
  A 10-second ATT watchdog recovers the queue if the BLE stack ever
  drops a completion event, so a lost read costs one 10 s stall instead
  of a stuck connection.

  ```text
  HA                ESP                 Device
  │── N reads ─────►│ queue [████ N]      │
  │                 │── request #1 ──────►│
  │◄──── event ─────│◄─── response #1 ────│
  │◄──── event ─────│── request #2 ──────►│  ◄─ back-to-back at radio
  │◄──── event ─────│── request #3 ──────►│     pace, no HA round-trip
  ⋮                 ⋮                     ⋮     in between

  • one timeout budgets the whole batch (15 s + 1 s per read)
  • waiting behind connection setup is safe: the queue holds the reads
    instead of letting them time out
  ```

- **Bridge < 1.10.0 (sequential):** older firmware has a single response
  slot, so overlapping reads would silently drop all but the last reply.
  The integration detects this from the reported version and falls back
  to reading one characteristic at a time, waiting for each reply —
  exactly the pre-1.10.0 behavior. Everything keeps working, just with
  a slower read phase, and a read fired during connection setup can
  time out on the HA side before the bridge executes it.

  ```text
  HA                ESP                 Device
  │── read #1 ─────►│                     │
  │                 │── ATT request ─────►│ ╮
  │                 │◄──── ATT response ──│ ╯ a few conn events
  │◄──── event ─────│                     │
  │── read #2 ─────►│                     │  ◄─ next read only after a
  │                 │──────►              │     full HA↔ESP round-trip
  ⋮                 ⋮                     ⋮     (× N reads)

  • per read: radio round-trip + HA↔ESP round-trip
  • each read has its own 5 s timeout → a read fired while the bridge
    is still subscribing can expire before it ever executes
  ```

How fast a batch completes is bounded by the BLE **connection
interval**, which the device itself renegotiates depending on its
state: fast right after connecting, a power-save interval (with slave
latency) once idle, and fast again while the motor runs. Each GATT
read costs a few connection events, so the same 28-characteristic
batch can take ~3 s on a fresh connection and ~14 s on a long-idle
one — in both modes. Pipelining removes the per-read HA→ESP
round-trip and the timeout risk; it cannot make the radio tick
faster. The firmware logs `Conn params initial/now: interval=… ms`
lines (INFO) whenever the parameters change, which makes this
directly visible.

## Connection-parameter boost (bridge ≥ 1.11.0)

To lift that radio bound too, the bridge asks the device for a short
connection interval (30–45 ms, no slave latency) whenever a batch
piles up in its queue while the link sits in the power-save profile.
The device is free to reject the request, but in practice it accepts
and the batch then runs at fresh-connection speed. No restore step is
needed: the device renegotiates its own power-save parameters once it
goes idle again, exactly as it does after a fresh connect. The boost
request is logged as `Requesting conn-param boost … ms/lat …` (INFO)
and the accepted parameters appear in the next `Conn params now` line.

No action is required when updating: the integration picks the right
mode automatically. Pipelining can also be turned off without
reflashing via the integration options ("Pipelined GATT reads",
enabled by default) — useful if the bridge logs show repeated read
timeouts or ATT watchdog messages, e.g. in a congested radio
environment.

## Version pinning

The integration enforces a minimum bridge version (`MIN_BRIDGE_VERSION`
in `custom_components/philips_shaver/const.py`). On version mismatch
Home Assistant shows a Repairs notification asking you to reflash.
Always flash a matching pair — the ref in your YAML's
`external_components:` should point at the same tag/commit as the
integration version.
