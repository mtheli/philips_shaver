# ESP Bridge Changelog

## v1.8.2 — 2026-06-26

- **Firmware version is now a single source of truth.** The bridge version
  lives in `esphome/components/philips_shaver/VERSION` and is baked into the
  firmware at build time (injected as a compile define by `__init__.py`, read
  via the `PHILIPS_SHAVER_BRIDGE_VERSION` macro in `coordinator.h`) instead of
  a hard-coded constant. The Home Assistant integration reads the same file
  from GitHub to power a passive firmware-update notification, so new bridge
  firmware is surfaced without shipping an integration release. No behavioural
  change to the bridge itself — the bump from v1.8.1 only reflects the new
  version plumbing.

  > The firmware-update notification in Home Assistant is supported from
  > **integration version 0.16.0** onwards. Older integration versions ignore
  > this and keep working unchanged.

## v1.8.1 — 2026-05-22

- **Fix Mode B YAML validation error (Issue #10).** Configurations that
  followed the documented Fixed-MAC example (`mac_address:` without
  `ble_client_id:`) failed with the misleading `"'ble_client_id' is a
  required option for [philips_shaver]"` error. Root cause: `cv.Any`'s
  backtracking could not fall back cleanly from Mode A to Mode B when the
  nested `connected:` binary_sensor schema fired its deferred `declare_id`
  during the first attempt. Replaced `cv.Any` with explicit key-based
  routing — presence of `ble_client_id` selects Mode A, absence selects
  Mode B. Each schema now runs exactly once against a fresh config dict.
  No YAML changes needed; existing Mode A and Mode B configs continue to
  validate.

## v1.8.0 — 2026-05-08

- **Mode B auto-discovery pair flow.** YAML configs without
  `ble_client_id:` now define a self-contained `BLEClientBase` subclass
  that pairs to the first `8d560100`-advertising shaver via the new
  `ble_pair_mode` service, persists the bonded MAC in NVS, and
  auto-reconnects on subsequent boots. Eliminates the manual
  `pair.sh` round-trip for Bluetooth-Proxy-only setups.
- **Component refactored to 3 classes** (`ShaverCoordinator`,
  `ShaverBridge`, `PhilipsShaver` / `PhilipsShaverStandalone`). All
  GATT logic lives in the mode-agnostic Coordinator; the Bridge owns
  HA service registration; Workers are thin BLE-stack adapters. No
  user-visible behavior change in Mode A — the existing
  `ble_client_id`-based YAML configs flash and run unchanged.
- **4 new HA services** (Mode B only — guarded inside the Coordinator):
  - `ble_pair_mode(enabled, timeout_s)` — arm/disarm UUID-scan
  - `ble_unpair()` — remove the bond + clear NVS identity
  - `ble_scan(timeout_s)` — discovery-only; emits `scan_result` events
  - `ble_pair_mac(mac, timeout_s)` — targeted pair to a specific MAC
- **`ble_get_info` extended** with `mode`, `identity_source`
  (yaml/nvs/none), `identity_address`, `pair_capable`. HA-side config
  flow uses these to detect Mode B unpaired bridges and route to the
  setup-dialog pair flow instead of attempting a doomed capability
  fetch.
- **Auto-injected `bridge_id` on every event.** `fire_event()` now
  fills the `bridge_id` field if the emitting site didn't, so
  HA-side multi-bridge filtering works for `pair_complete`,
  `scan_result`, `unpaired`, etc. without each emit-site having to
  remember to set it.
- **Fix `pair_capable` semantic in `ble_get_info`.** The field used to be
  hardcoded `true` for every Mode B (standalone) bridge regardless of
  bond state. Now correctly reports `true` only when
  `mode == standalone && identity_source == "none"` — service-call
  consumers (Developer Tools, third-party automations) now see the
  field's real meaning.

## v1.7.0 — 2026-05-01

- **Fix BLE re-encrypt race on ESP32-S3 with hot GATT cache (Issue #6).**
  Bonded reconnects on ESP32-S3 could fail with auth `reason=97`
  (`SMP_ENC_FAIL`) when `SEARCH_CMPL_EVT` fires before BTM has
  rehydrated the bonded device record from NVS. The proactive
  `esp_ble_set_encryption()` call then ran while BTM still reported
  "Device not found", and the 3-strike auto-clean nuked the otherwise
  valid bond. Replaced with a lazy-encrypt pattern: `SEARCH_CMPL` issues
  a probe read on a Philips proprietary characteristic with
  `ESP_GATT_AUTH_REQ_NONE`. Bluedroid's automatic peer-encryption
  handles the bonded path transparently; if the probe surfaces
  `INSUF_AUTH`/`INSUF_ENCR`, encryption is initiated then and the read
  is retried after `AUTH_CMPL.success`. Fallback path for unknown
  models without the probe characteristic preserves the previous v1.5.2
  behaviour.
- **Defer `ready` event when `AUTH_CMPL.success` fires before
  `SEARCH_CMPL_EVT`.** When Bluedroid auto-encrypts on bonded
  reconnect, the auth event arrives before service discovery completes;
  firing `ready` from there raced with the probe-OK path and produced
  duplicate events. Three-way logic now distinguishes (a) probe-retry
  pending, (b) probe done or absent, and (c) discovery not yet
  complete. The new `start_post_auth_setup_()` helper is guarded by a
  per-connection `ready_fired_` flag.
- **Per-instance log tag for multi-bridge YAMLs.** Each
  `philips_shaver:` entry now uses `philips_shaver.<bridge_id>` as its
  ESP-IDF log tag, so dual-bridge setups (e.g. OneBlade + XP9201 on the
  same AtomS3R) produce unambiguous lines. Logger filter can target a
  single bridge by suffix.

## v1.6.2 — 2026-04-22

- Include `uptime_s` in `heartbeat` and `ready` events (previously only
  in `info`). Enables HA to detect bridge restarts via uptime
  regression and clear stale subscription state, so auto-resubscribe
  triggers when the API reconnects after an ESP reboot — even without
  HA actively requesting `ble_get_info`.

## v1.6.1 — 2026-04-17

- Stale-bond detection tuning: `RAPID_DISCONNECT_THRESHOLD_MS` raised
  from 5s to 10s. Service discovery on the XP9201 takes ~5.5s, so a
  disconnect right after re-encrypt (observed at ~5.7s) was missing the
  previous 5s window and the 3-fail auto-clear never triggered. 10s
  covers it with margin. Disconnect log now includes connect duration
  and reason code to make rapid-disconnect traces easier to read.

## v1.6.0 — 2026-04-17

- Fire `ready` status event from `AUTH_CMPL_EVT` (on success) instead of
  `SEARCH_CMPL_EVT`. Some shaver models expose a larger GATT table after
  bonding; reading before encryption completes caused "not found" errors
  for characteristics that only appear in the post-auth cache (observed
  with S7887 / Firmware Revision 0x2A26).
- Heartbeat-based `ready` re-fire is gated on `auth_completed_` for the
  same reason.
- `auth_completed_` is reset on disconnect as a safety.
- Subscribe guard: reject `on_subscribe` calls for characteristics that
  advertise neither `NOTIFY` nor `INDICATE`. Previously the CCCD write
  would fail silently and no data would ever arrive.
- Indicate support: CCCD value is now chosen from the characteristic
  properties (0x0001 notify, 0x0002 indicate, 0x0003 both) instead of
  always writing 0x0001. Notify log line distinguishes Notify vs
  Indicate events.

## v1.5.2 — 2026-04-12

- Fix BLE auth failure after reboot on ESP32-S3. The stricter BLE 5.0
  stack rejected `SEC_ENCRYPT_MITM` on bonds that had originally been
  created via Just Works (e.g. OneBlade QP4530). The bridge now checks
  the stored bond list and uses `SEC_ENCRYPT` for known bonds,
  reserving `SEC_ENCRYPT_MITM` for fresh pairings.

## v1.5.1 — 2026-04-07

- Rename `device_id` to `bridge_id` in config and heartbeat/info events
  to align with the multi-device setup model. Backwards-compatible
  YAML: both keys are accepted.

## v1.5.0 — 2026-03-18

- Move BLE encryption params from YAML to C++ so pairing is driven by
  the component itself.
- Fix CCCD handle discovery to use the ESP-IDF API directly
  (`esp_ble_gattc_get_descr_by_char_handle`) instead of ESPHome's
  descriptor cache, which could be empty after service discovery.

## v1.4.0 — 2026-03-10

- Fire error events from `on_read_characteristic` when a read fails or
  the characteristic is not found (`not_found`, `not_connected`,
  `gatt_err_*`). HA can now resolve the pending read immediately
  instead of waiting for the timeout.

## v1.3.1 — 2026-03-09

- Auto-clear stale BLE bond after OTA or re-flash. Detects rapid
  disconnects without successful auth and removes the bond so the next
  connection starts fresh pairing.

## v1.3.0 — 2026-03-09

- Heartbeat-based `ready` re-fire when BLE is connected but no
  subscriptions are active (e.g. after OTA reboot, when the initial
  ready event is lost before the HA API stream is up). Self-terminates
  once any subscription is registered.

## v1.2.0 — 2026-03-08

- Re-apply SMP params right before pairing (in `GATTC_OPEN_EVT`) so
  Numeric Comparison is advertised correctly on reconnect.
- Auto-confirm Numeric Comparison requests in the GAP event handler so
  pairing works unattended on models that report DisplayYesNo.

## v1.1.0 — 2026-03-08

- Initial ESP32 Bridge release.
- BLE client for Philips shavers (S7000/S8000/S9000/XP9000 series) and
  OneBlade groomers (QP4000).
- Read, write, subscribe/unsubscribe via ESPHome service calls.
- Status events: `connected`, `ready`, `disconnected`, `heartbeat`,
  `auth_failed`.
- `connected` binary sensor for device presence.
- `ble_get_info` diagnostic service for runtime stats.
- Component version reporting in heartbeat and ready events.
