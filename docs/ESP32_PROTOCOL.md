# ESP32 Bridge — HA-Service Protocol

This document describes the Home Assistant–facing protocol of the
`philips_shaver` ESPHome component: which services it registers, what
arguments they take, and which events the bridge fires in response.

The bridge is a thin facade — every action HA wants the ESP to perform is an
`esphome.<device>_<service>` call, every reply comes back as a Home Assistant
event the integration listens for. There is no direct return value.

> Component version: **1.8.0-rc.1**

## Architecture

```
┌──────────┐   BLE    ┌─────────┐  WiFi/API  ┌─────────────────┐
│  Shaver  │◄────────►│  ESP32  │◄──────────►│ Home Assistant  │
│          │  paired  │  Bridge │  ESPHome   │ Philips Shaver  │
│          │          │         │  services  │ Integration     │
└──────────┘          └─────────┘            └─────────────────┘
```

- **HA → ESP32**: ESPHome service calls (`ble_read_char`, `ble_subscribe`,
  `ble_write_char`, `ble_unsubscribe`, `ble_set_throttle`, `ble_get_info`,
  `ble_pair_mode`, `ble_unpair`, `ble_scan`, `ble_pair_mac`) — see
  [Services](#services).
- **ESP32 → HA**: events on the HA event bus (`_ble_data`, `_ble_status`) —
  see [Events](#events).
- **Heartbeat**: the bridge fires a `_ble_status` event with `status="heartbeat"`
  every 15 s, regardless of any service call.

## Conventions

### Service names and `bridge_id`

Service names are constructed as:

```
esphome.<esphome_device_name>_<service>[_<bridge_id>]
```

The `bridge_id` suffix is **only present** when the YAML sets a non-empty
`bridge_id` for the `philips_shaver:` block. Single-bridge setups omit it:

```yaml
philips_shaver:
  - bridge_id: ""        # default — no suffix
```

Multi-bridge setups (multiple Philips devices on the same ESP) add a unique
suffix:

```yaml
philips_shaver:
  - bridge_id: shaver    # services become …_ble_read_char_shaver etc.
  - bridge_id: oneblade
```

### Events and `bridge_id`

The bridge emits two event types — see [Events](#events) for the full
field reference. Every event payload includes a `bridge_id` field; for
single-bridge setups it is an empty string, multi-bridge setups must filter
on it because the ESP fires the same event names regardless of which slot
triggered them.

### UUID parsing

UUIDs accept three forms:

- **4 hex chars** → 16-bit BLE UUID, e.g. `"180a"`
- **8 hex chars** → 32-bit BLE UUID
- **Anything else** → treated as a 128-bit raw UUID
  (`"8d560100-3cb9-4387-a7e8-b79d826a7025"`)

Garbage input is rejected with a warning and falls back to raw, which usually
fails downstream as `error="not_found"`.

---

## Operation modes

The bridge runs in one of two modes, chosen at build time by the YAML schema.
HA detects which is active by reading `ble_get_info` and checking the `mode`
field — the values below are exactly what that field reports.

| `mode` field | Trigger in YAML | Pair-flow |
|---|---|---|
| `"external"` | uses an external `ble_client:` block (`ble_client_id` set) | MAC is fixed in YAML, no pair-mode |
| `"standalone"` | no `ble_client:` block, optional `mac_address:` | If no MAC and no NVS identity: `pair_capable=true`, HA must call `ble_pair_mode` to bond a shaver |

A `"standalone"` bridge that has either a YAML MAC or a previously bonded
shaver (persisted in NVS) reports `pair_capable=false` — same as `"external"`
from HA's point of view.

> [!NOTE]
> The `"external"` mode is kept for backwards compatibility with older configs
> that wired up an external `ble_client:` block. New setups should use
> `"standalone"`; see [ESP Bridge Setup](ESP_BRIDGE_SETUP.md) for the
> user-facing **Auto-Discovery** (no MAC) and **Fixed MAC** flows, both of
> which run in `"standalone"` mode.

### `external` — external `ble_client`

The classic ESPHome BLE-client wiring with a fixed MAC. Kept for backwards
compatibility — offers no advantage over `standalone` with `mac_address:`.

```yaml
ble_client:
  - id: shaver_ble
    mac_address: "AA:BB:CC:DD:EE:FF"
    auto_connect: true

philips_shaver:
  - ble_client_id: shaver_ble
    bridge_id: shaver       # optional, suffixes HA service names
```

`ble_client_id` is required for `external` mode. If omitted, the schema falls
through to `standalone`.

### `standalone` — fixed MAC

You know your shaver's MAC and don't want a pair-flow. The bridge connects
the same way as `external` mode but without the dummy `ble_client:` block.

```yaml
philips_shaver:
  - mac_address: "AA:BB:CC:DD:EE:FF"
    bridge_id: shaver
    auto_connect: true       # default true when mac_address is set
```

### `standalone` — pair-flow (recommended for fresh setups)

No MAC, no NVS identity yet. The bridge stays passive on boot and only
scans for shavers when HA arms `ble_pair_mode` (e.g. via the integration's
config flow). After successful pairing, the identity address is persisted
to flash and subsequent boots auto-reconnect.

```yaml
philips_shaver:
  - bridge_id: shaver
    # No mac_address — bridge waits for HA to arm pair-mode
```

To bond multiple devices on a single ESP32, repeat the block with distinct
`bridge_id`s — each gets its own service-name suffix:

```yaml
philips_shaver:
  - bridge_id: shaver
  - bridge_id: oneblade
```

---

## Services

| # | Service | Args | Available since |
|---|---|---|---|
| 1 | [`ble_read_char`](#ble_read_char) | `service_uuid`, `char_uuid` | 1.0.0 |
| 2 | [`ble_subscribe`](#ble_subscribe) | `service_uuid`, `char_uuid` | 1.0.0 |
| 3 | [`ble_unsubscribe`](#ble_unsubscribe) | `service_uuid`, `char_uuid` | 1.0.0 |
| 4 | [`ble_write_char`](#ble_write_char) | `service_uuid`, `char_uuid`, `data` | 1.0.0 |
| 5 | [`ble_set_throttle`](#ble_set_throttle) | `throttle_ms` | 1.0.0 |
| 6 | [`ble_get_info`](#ble_get_info) | — | 1.0.0 (extended in 1.8.0) |
| 7 | [`ble_pair_mode`](#ble_pair_mode) | `enabled`, `timeout_s` | 1.8.0 |
| 8 | [`ble_unpair`](#ble_unpair) | — | 1.8.0 |
| 9 | [`ble_scan`](#ble_scan) | `timeout_s` | 1.8.0 |
| 10 | [`ble_pair_mac`](#ble_pair_mac) | `mac`, `timeout_s` | 1.8.0 |

Services 7–10 are meaningful only in `standalone` mode. Calling them on an
`external` bridge emits a warning to the log and is otherwise a no-op.

### `ble_read_char`

*Available since 1.0.0.*

Read a GATT characteristic on the bonded shaver.

| | |
|---|---|
| **Args** | `service_uuid: string`, `char_uuid: string` |
| **Side-effect** | Issues an `esp_ble_gattc_read_char`. On `INSUF_AUTH/ENCR` it transparently triggers SMP and retries the read once `AUTH_CMPL` succeeds. Concurrent reads that race the SMP handshake — common when HA fires its poll cycle concurrently — are requeued via the bridge's pending-calls queue and drained on `AUTH_CMPL` (added in 1.10.0). |
| **Reply** | `_ble_data` event |

**`_ble_data` (success):**

| Field | Type | Note |
|---|---|---|
| `uuid` | string | The `char_uuid` requested |
| `payload` | string (hex) | Raw bytes, lowercase hex |
| `mac` | string | Shaver MAC |
| `bridge_id` | string | Possibly empty |

**`_ble_data` (failure):**

| Field | Value |
|---|---|
| `payload` | `""` |
| `error` | `not_connected` \| `not_found` \| `read_failed` \| `auth_failed` \| `gatt_err_<n>` \| `queue_full` |

If service discovery hasn't completed yet — or any other GATT operation is
in flight (a read, a characteristic write, the encryption probe, or the
subscribe burst's CCCD writes; since 1.10.0) — the call is **queued** and
replayed once the ATT slot frees up. Queued operations execute back-to-back
at BLE pace, so callers may fire several `ble_read_char` calls
concurrently. A queued read whose response is lost is force-cleared by a
10 s watchdog (`error=read_timeout`) and the queue keeps draining.
Overflowing the queue (64 entries) yields `error=queue_full`.

### `ble_subscribe`

*Available since 1.0.0.*

Enable notifications/indications on a characteristic.

| | |
|---|---|
| **Args** | `service_uuid: string`, `char_uuid: string` |
| **Side-effect** | `esp_ble_gattc_register_for_notify` + CCCD write. Idempotent — duplicate subscribes are silently ignored. |
| **Reply** | None directly. Each notification triggers a `_ble_data` event with `uuid`, `payload`, `mac`, `bridge_id`. |
| **Throttling** | Per-characteristic minimum interval, default 500 ms. Tunable via `ble_set_throttle`. |

Subscriptions are tracked in `desired_subscriptions_` and **automatically
restored** on reconnect.

### `ble_unsubscribe`

*Available since 1.0.0.*

Disable notifications and remove from auto-resubscribe list.

| | |
|---|---|
| **Args** | `service_uuid: string`, `char_uuid: string` |
| **Reply** | None |

### `ble_write_char`

*Available since 1.0.0.*

Write a characteristic with response.

| | |
|---|---|
| **Args** | `service_uuid: string`, `char_uuid: string`, `data: string` (hex, no separators) |
| **Side-effect** | `esp_ble_gattc_write_char` with `WRITE_TYPE_RSP`. Since 1.10.0 the write shares the single ATT slot with reads/probe/subscribes: it is queued while another GATT operation is in flight and executed as soon as the slot frees up. |
| **Reply** | None — success/failure only in the ESP log |

Hex parsing rejects malformed input silently (warning in log, no event).

### `ble_set_throttle`

*Available since 1.0.0.*

Adjust the minimum interval between notification events forwarded to HA.

| | |
|---|---|
| **Args** | `throttle_ms: string` (uint, in ms) |
| **Side-effect** | `notify_throttle_ms_` is updated globally for this bridge. |
| **Reply** | None |

Invalid values (non-numeric, trailing junk) are rejected with a log warning;
the previous value is kept.

### `ble_get_info`

*Available since 1.0.0. Extended with `mode`, `pair_capable`, `identity_address`, `identity_source` in 1.8.0.*

Snapshot of bridge + shaver state. **Primary capability-detection call** for
HA during config flow.

| | |
|---|---|
| **Args** | — |
| **Reply** | `_ble_status` event with `status="info"` |

**Event fields:**

| Field | Type | Note |
|---|---|---|
| `status` | `"info"` | |
| `mode` | `"external"` \| `"standalone"` | |
| `pair_capable` | `"true"` \| `"false"` | True only when standalone + no YAML MAC + no NVS identity |
| `identity_address` | string (optional) | Persistent BLE identity (post-bond). Same value as in `pair_complete`. Only set when an identity exists. |
| `identity_source` | `"yaml"` \| `"nvs"` \| `"none"` | Where the identity comes from — see [Identity sources](#identity-sources) below. |
| `ble_connected` | `"true"` \| `"false"` | |
| `paired` | `"true"` \| `"false"` | True if BD addr appears in `esp_ble_get_bond_device_list` |
| `mac` | string | Currently used remote MAC (may be RPA pre-bond) |
| `ble_name` | string (optional) | GAP 0x2A00 |
| `uptime_s`, `free_heap`, `subscriptions`, `notify_throttle_ms`, `version`, `bridge_id` | misc | Diagnostic |

#### Identity sources

`identity_source` tells HA where the bridge's currently bound identity came
from. The value is stable across the lifetime of the bond and used by HA's
in-place reconfigure flow to decide whether the bridge can be retargeted at
runtime.

| Value | Provenance | Reconfigurable at runtime? |
|---|---|---|
| `"yaml"` | `external` mode (`ble_client:` block) **or** `standalone` with `mac_address:` in YAML. The identity is re-applied at every boot regardless of NVS state. | **No.** A YAML rebuild + reflash is required to retarget. |
| `"nvs"` | `standalone` auto-discovery — the shaver was bonded via `ble_pair_mode` and the resulting identity was persisted to NVS. | **Yes.** `ble_unpair` wipes the NVS slot and the bridge becomes available for a new shaver. |
| `"none"` | `standalone` without YAML MAC and without a persisted NVS identity — bridge is unpaired and waiting for `ble_pair_mode`. | n/a (already unbound) |

State transitions during runtime:

- `"none"` → `"nvs"` on successful `pair_complete` (`standalone` auto-discovery only)
- `"nvs"` → `"none"` on `ble_unpair` (`standalone` auto-discovery only)
- `"yaml"` never transitions — the YAML config is the source of truth and
  re-applies on every boot

### `ble_pair_mode`

*Available since 1.8.0.*

Arm or cancel the UUID-scan + auto-pair window.

| | |
|---|---|
| **Args** | `enabled: bool`, `timeout_s: string` (default 60, max 600) |
| **Side-effect** (enable) | Worker switches to UUID-scan, the first shaver advertising the Philips Shaver Platform Service UUID (`8d560100`) triggers connect → SMP. Auto-disables after `timeout_s`. |
| **Side-effect** (disable) | Cancels the timer and disables the worker (no event fired). |
| **Replies** | One `pair_mode_armed`, then exactly one of `pair_complete` / `pair_timeout` / `pair_failed` |

**Reply events** (`_ble_status`):

| `status` | When | Extra fields |
|---|---|---|
| `pair_mode_armed` | Pair-mode armed | `timeout_s`, `target_mac` (only when armed via `ble_pair_mac`) |
| `pair_complete` | Pairing succeeded — identity persisted | `identity_address`, `identity_source` (always `"nvs"` post-pair), `bonding` (`"bonded"`), `mac`, `version` |
| `pair_timeout` | Window expired without successful pairing | `version` |
| `pair_failed` | SMP hit `MAX_AUTH_FAILURES` (3) during pair-mode — shaver likely retains a stale bond from a previous device | `reason` (`"auth_max_failures"`), `mac`, `version` |

> [!NOTE]
> `pair_failed` is shaver-specific (not present in the Sonicare bridge). When
> the shaver still has a bond from a phone or a previous ESP, fresh-pair
> attempts get rejected with auth failures. The bridge surfaces this
> distinctly so HA can prompt the user to clear the shaver's Bluetooth
> pairing instead of silently waiting out the 60 s window.

### `ble_unpair`

*Available since 1.8.0.*

Remove the BLE bond and clear any persisted identity. Bridge ends up with
`pair_capable=true` again.

| | |
|---|---|
| **Args** | — |
| **Side-effect** | `esp_ble_remove_bond_device`, NVS identity wiped (`standalone` mode), UUID-scan re-armed, BLE client cycled to drop the current connection. |
| **Reply** | `_ble_status` event with `status="unpaired"` |

**Event fields:**

| Field | Note |
|---|---|
| `status` | `"unpaired"` |
| `previous_mac` | The MAC that was bonded |
| `identity_source` | Post-unpair source — `"none"` (`standalone` auto-discovery, fully unpaired), `"yaml"` (`external` mode or `standalone` with `mac_address:` — bond gone but YAML pin remains) |

In `external` mode, only the BLE bond is removed — the YAML MAC is unaffected
and the bridge will attempt to re-pair on the next connection.

### `ble_scan`

*Available since 1.8.0.*

Discovery-only — list all Philips devices in range without connecting.

| | |
|---|---|
| **Args** | `timeout_s: string` (default 30, max 300) |
| **Side-effect** | Worker observes UUID-matching adverts for `timeout_s` and emits one event per unique MAC. **Does not connect**. `standalone` mode only. Refused while pair-mode is active. |
| **Replies** | One `scan_started`, then multiple `scan_result` (one per unique MAC observed), then one `scan_complete` |

**`scan_started` fields:** `status="scan_started"`, `timeout_s`, `mac`, `bridge_id`

**`scan_result` fields:**

| Field | Note |
|---|---|
| `status` | `"scan_result"` |
| `mac` | MAC currently advertising (`AA:BB:CC:DD:EE:FF`) |
| `addr_type` | `"public"` \| `"random"` |
| `local_name` | Possibly empty |
| `mfr_data` | Hex (Company-ID little-endian + payload), possibly empty |
| `rssi` | Signed int as string |
| `service_uuid` | Always `"philips_shaver_platform"` (`8d560100-3cb9-4387-a7e8-b79d826a7025`) |

**`scan_complete` fields:** `status="scan_complete"`, `count` (number of unique MACs)

### `ble_pair_mac`

*Available since 1.8.0.*

Targeted pairing — bond a specific MAC instead of the first UUID-match.

| | |
|---|---|
| **Args** | `mac: string` (accepts `AA:BB:CC:DD:EE:FF`, `AABBCCDDEEFF`, or with dashes), `timeout_s: string` (default 60) |
| **Side-effect** | Worker sets internal `target_mac_=normalized(mac)`; `parse_device` matches on that MAC instead of UUID. Otherwise reuses `ble_pair_mode`'s plumbing. `standalone` mode only. |
| **Replies** | `pair_mode_armed` (with `target_mac`), then one of `pair_complete` / `pair_timeout` / `pair_failed` |
| **Validation** | Invalid MAC (≠ 12 hex chars after stripping separators) is rejected in the log; no pair-mode is armed |

Use cases this enables:

- HA shows a `ble_scan` result list and lets the user pick which Philips
  device to bond
- Power-user enters a MAC manually (from another tool, prior bond, etc.)
- Multi-device setups where the convenience pair-mode would race

---

## Events

The bridge publishes two event types on the Home Assistant event bus. All
can be watched live in **Developer Tools → Events** by entering the event
name and clicking **Start Listening**.

| Event name | Used for |
|---|---|
| `esphome.philips_shaver_ble_status` | Bridge lifecycle, info, pair-mode, scan, errors |
| `esphome.philips_shaver_ble_data` | GATT read replies + notifications |

> [!NOTE]
> A third event name `esphome.philips_shaver_ble_services` is reserved in the
> firmware but currently unused — the equivalent `ble_list_services` service
> from the Sonicare bridge is not implemented here (HA reads everything via
> `ble_get_info` and known service UUIDs). The slot is kept for forward
> compatibility.

### `esphome.philips_shaver_ble_data`

GATT-side traffic — notifications, read results, and read errors.

| Field        | When set                            | Example                                  |
|--------------|-------------------------------------|------------------------------------------|
| `mac`        | Always (the shaver MAC)             | `AA:BB:CC:DD:EE:FF`                      |
| `uuid`       | Characteristic UUID                 | `8d560117-3cb9-4387-a7e8-b79d826a7025`   |
| `payload`    | Hex-encoded bytes (notify or read)  | `02`                                     |
| `error`      | Read failure reason (mutually exclusive with `payload`) | `auth_failed` |
| `bridge_id`  | Multi-device setups — identifies which bridge fired the event | `shaver` |

### `esphome.philips_shaver_ble_status`

Bridge lifecycle — heartbeats, info responses, pair-mode replies, scan
replies, ready/connected/disconnected transitions. The exact field set
depends on the value of `status`. Service-reply statuses are also documented
on the originating service in [Services](#services).

| `status`            | Meaning                                                     | Trigger / Reply to                              |
|---------------------|-------------------------------------------------------------|-------------------------------------------------|
| `heartbeat`         | Periodic keep-alive (every ~15 s)                           | Unconditional, every 15 s                       |
| `info`              | Bridge + shaver state snapshot                              | [`ble_get_info`](#ble_get_info) reply           |
| `connected`         | BLE link came up (before service discovery completes)       | `OPEN_EVT` succeeded                            |
| `ready`             | GATT discovery complete and bridge ready for I/O            | `SEARCH_CMPL_EVT` (or post-auth probe done)     |
| `disconnected`      | BLE link dropped                                            | `DISCONNECT_EVT`                                |
| `auth_failed`       | Repeated SMP failure → backoff                              | 3× consecutive `AUTH_CMPL.success=false`        |
| `pair_mode_armed`   | Pair-mode armed                                             | [`ble_pair_mode`](#ble_pair_mode) (enable) / [`ble_pair_mac`](#ble_pair_mac) |
| `pair_complete`     | Pairing succeeded — identity persisted                      | [`ble_pair_mode`](#ble_pair_mode) / [`ble_pair_mac`](#ble_pair_mac) |
| `pair_timeout`      | Pair-mode window expired without success                    | [`ble_pair_mode`](#ble_pair_mode) / [`ble_pair_mac`](#ble_pair_mac) |
| `pair_failed`       | SMP hit `MAX_AUTH_FAILURES` during pair-mode (stale bond on shaver) | [`ble_pair_mode`](#ble_pair_mode) / [`ble_pair_mac`](#ble_pair_mac) |
| `unpaired`          | Bond removed                                                | [`ble_unpair`](#ble_unpair) reply               |
| `scan_started`      | Discovery scan armed                                        | [`ble_scan`](#ble_scan) (start)                 |
| `scan_result`       | One advertised device seen                                  | [`ble_scan`](#ble_scan)                         |
| `scan_complete`     | Discovery scan ended                                        | [`ble_scan`](#ble_scan)                         |

Common fields on every `_ble_status` event: `bridge_id` (always),
`mac` (when relevant), `version` + `uptime_s` (on `heartbeat`, `ready`,
`info`). The per-service tables in [Services](#services) list the additional
fields each status carries.

After OTA, if the bridge is connected with services discovered but has no
active subscriptions, it will re-fire `ready` once on the next heartbeat — so
HA can re-subscribe even if it missed the original event during reboot.

### Filtering by `bridge_id`

In multi-bridge setups, every event carries a `bridge_id` field
(`""` for single-bridge configs). To watch a single device, filter on
`bridge_id == "<your_id>"` in your automation/script. The integration's
`EspBridgeTransport` does this internally.

### Heartbeat-driven restart detection

The integration tracks `uptime_s` across heartbeats; a regression flags an ESP
restart and triggers BLE re-subscription. So if you spot the bridge boot-time
sensor jumping in HA, that is what the heartbeat told us.
