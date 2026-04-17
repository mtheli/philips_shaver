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

## Version pinning

The integration enforces a minimum bridge version (`MIN_BRIDGE_VERSION`
in `custom_components/philips_shaver/const.py`). On version mismatch
Home Assistant shows a Repairs notification asking you to reflash.
Always flash a matching pair — the ref in your YAML's
`external_components:` should point at the same tag/commit as the
integration version.
