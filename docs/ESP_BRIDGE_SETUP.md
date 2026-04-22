# ESP32 BLE Bridge Setup Guide

This guide explains how to set up an ESP32 as a Bluetooth Low Energy (BLE) bridge
for the Philips Shaver Home Assistant integration. The ESP32 connects to the shaver
via BLE and relays data to Home Assistant over WiFi, removing the need for direct
Bluetooth access from the HA host.

> [!IMPORTANT]
> This is a **dedicated ESPHome component**, not a standard
> [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html).
> The standard Bluetooth Proxy does **not** support the LE Secure Connections
> pairing that Philips shavers require. If you already have an ESP32 running
> a Bluetooth Proxy, you still need to flash this custom component — the proxy
> alone will fail with `ESP_GATT_CONN_FAIL_ESTABLISH`.

## Tested Hardware

| Board | Status |
|-------|--------|
| [M5Stack Atom Lite](https://docs.m5stack.com/en/core/ATOM%20Lite) (ESP32-PICO) | Confirmed (maintainer, [#3](https://github.com/mtheli/philips_shaver/issues/3)) |
| Lolin D32 (ESP32) | Confirmed ([forum](https://community.home-assistant.io/t/philips-bluetooth-shaver-monitoring/858822/)) |
| [M5Stack NanoC6](https://docs.m5stack.com/en/core/M5NanoC6) (ESP32-C6) | Confirmed ([#7](https://github.com/mtheli/philips_shaver/issues/7)) |
| [M5Stack AtomS3R](https://docs.m5stack.com/en/core/AtomS3R) (ESP32-S3) | Confirmed (maintainer) |
| ESP32-S3 DevKitC-1 | Partial — first pairing works, bond after reboot unstable on some setups ([#6](https://github.com/mtheli/philips_shaver/issues/6)) |
| Generic ESP32-DevKit | Should work (same SoC) |
| ESP32-C3 | Untested — BLE stack should be compatible |

## Prerequisites

- **ESP32 board** — see [Tested Hardware](#tested-hardware) above
- **ESPHome** — installed as Home Assistant add-on or standalone
- **Philips Shaver or OneBlade** — see [Tested Models](../README.md#tested-models)

## Step 1: Find Your Shaver's MAC Address

The shaver advertises via BLE when it is powered on or placed on the charging stand.

**Option A — Home Assistant Bluetooth:**
1. Go to **Settings > Devices & Services > Bluetooth**
2. Look for a device named "Philips XP9201" or "Philips XP9400" (or similar)
3. Note the MAC address (e.g. `AA:BB:CC:11:22:33`)

**Option B — nRF Connect (Android/iOS):**
1. Open the nRF Connect app and scan for devices
2. Filter for "Philips" — the shaver shows up with its MAC address

**Option C — ESPHome logs:**
1. Deploy any ESP32 with `esp32_ble_tracker` enabled
2. Check logs for `Found device ... Name: 'Philips XP9201'` (or your model name)

## Step 2: Create the ESPHome Configuration

Choose a template based on your board:

| Board | Template |
|-------|----------|
| Generic ESP32 (DevKit, etc.) | [`esphome/esp32-generic.yaml`](../esphome/esp32-generic.yaml) |
| M5Stack Atom Lite | [`esphome/atom-lite.yaml`](../esphome/atom-lite.yaml) |

Copy the template to your ESPHome configuration directory and customize:

### Required changes

1. **Shaver MAC address** — replace `XX:XX:XX:XX:XX:XX` with your shaver's MAC:
   ```yaml
   ble_client:
     - mac_address: "XX:XX:XX:XX:XX:XX"   # <-- your shaver's MAC
   ```

2. **Board type** (generic template only) — change `esp32dev` if needed:
   ```yaml
   esp32:
     board: esp32dev   # or esp32-s3-devkitc-1, m5stack-atoms3, etc.
   ```

3. **Secrets** — create or update your `secrets.yaml` with:
   ```yaml
   api_encryption_key: "<generate with `esphome wizard`>"
   ota_password: "<your OTA password>"
   wifi_ssid: "<your WiFi SSID>"
   wifi_password: "<your WiFi password>"
   fallback_password: "<fallback AP password>"
   ```

### What you should NOT change

- **Framework**: must be `esp-idf` (not Arduino) — required for configurable BLE limits
- **sdkconfig options**: `CONFIG_BT_GATTC_MAX_CACHE_CHAR` and
  `CONFIG_BT_GATTC_NOTIF_REG_MAX` — the shaver has ~66 GATT attributes and
  we subscribe to 17+ characteristics. Use `100`/`30` for a single device, `160`/`50`
  for two devices (see [Multi-Device Setup](#multi-device-setup) below)
- **API flags**: `custom_services: true` and `homeassistant_services: true` — required
  for the bridge component to register its services
- **`max_connections`** under `esp32_ble:` — `4` for single device, `5` for two devices
  (bluetooth_proxy uses 3 slots + 1 slot per ble_client)
- **external_components**: the component is loaded directly from this GitHub repository.
  The `refresh: 0s` setting ensures the latest code is fetched on every build

## Step 3: Flash the ESP32

1. Open the **ESPHome Dashboard** in Home Assistant
2. Add a new device or upload your customized YAML
3. Click **Install** and choose your flashing method:
   - USB for first-time flash
   - OTA for subsequent updates
4. Wait for the build and flash to complete

> **Note:** Switching between Arduino and ESP-IDF framework requires a full clean build
> ("Clean Build Files" in the ESPHome dashboard before flashing).

## Step 4: Verify BLE Connection and Pairing

After flashing, check the ESPHome device logs for a successful connection sequence:

```
[D][esp32_ble_tracker:726]:   Name: 'Philips XP9201'
[I][esp32_ble_client:111]: [0] [XX:XX:XX:XX:XX:XX] 0x01 Connecting
[I][esp32_ble_client:326]: [0] [XX:XX:XX:XX:XX:XX] Connection open
[I][philips_shaver:061]: Connected to shaver
[I][esp32_ble_client:435]: [0] [XX:XX:XX:XX:XX:XX] Service discovery complete
[D][esp32_ble_client:547]: [0] [XX:XX:XX:XX:XX:XX] auth success type = 1 mode = 9
```

The key line is **`auth success type = 1`** — this confirms LE Secure Connections
pairing succeeded. The `mode` value depends on your shaver model (9 = Just Works, 13 = Numeric Comparison with MITM). Both are valid. If you don't see this, check the troubleshooting section below.

## Step 5: Add the Integration in Home Assistant

1. Go to **Settings > Devices & Services > Integrations**
2. Click **+ Add Integration** and search for **Philips Shaver**
3. Select **ESP32 Bridge (ESPHome)**
4. Choose your ESP device from the dropdown (e.g. "Atom Lite BLE Bridge (atom-lite)")
5. The **Bridge Status** page shows the bridge health: component version, BLE connection
   state, pairing status, and shaver MAC address — verify everything looks good and click **Submit**
6. The integration reads the shaver's hardware capabilities and GATT services via the bridge
7. Review the detected capabilities and click **Submit** to finish — the shaver appears as a
   sub-device of the ESP32

## Multi-Device Setup

A single ESP32 can bridge **two Philips devices** simultaneously (e.g. a shaver and an
OneBlade). The [`atom-lite.yaml`](../esphome/atom-lite.yaml) template shows a dual-device
configuration.

### Key differences from single-device

| Setting | Single device | Two devices |
|---------|--------------|-------------|
| `CONFIG_BT_GATTC_MAX_CACHE_CHAR` | `"100"` | `"160"` |
| `CONFIG_BT_GATTC_NOTIF_REG_MAX` | `"30"` | `"50"` |
| `max_notifications` | 30 | 50 |
| `max_connections` | 4 | 5 |
| `ble_client` entries | 1 | 2 |
| `philips_shaver` entries | 1 | 2 (each with `device_id`) |

### Configuration

Each device needs its own `ble_client` and `philips_shaver` entry. When using multiple
devices, each `philips_shaver` entry **must** have a unique `bridge_id`:

```yaml
ble_client:
  - mac_address: "AA:BB:CC:DD:EE:01"   # Shaver MAC
    id: shaver_ble
    auto_connect: true

  - mac_address: "AA:BB:CC:DD:EE:02"   # OneBlade MAC
    id: oneblade_ble
    auto_connect: true

philips_shaver:
  - ble_client_id: shaver_ble
    bridge_id: "shaver"

  - ble_client_id: oneblade_ble
    bridge_id: "oneblade"
```

The `bridge_id` is used to namespace the ESPHome service calls (e.g. `ble_read_char_shaver`
vs `ble_read_char_oneblade`). For a **single device**, you can omit `bridge_id` entirely.

> **Note:** Encryption is handled automatically by the C++ component after service discovery —
> no `on_connect` lambda needed. Old YAMLs with `device_id` still work (deprecated alias).

### Adding devices in Home Assistant

When setting up via **ESP32 Bridge** in the integration config flow, a device selector
appears if multiple devices are detected. It shows each device's `device_id`, MAC address,
and connection status. Each device is added as a separate integration entry.

## Troubleshooting

### Unpairing before switching to the ESP32 Bridge

The shaver can only be paired with **one device at a time**. If it is currently paired with
your phone or your HA host via Direct Bluetooth, you must unpair it first before the ESP32
bridge can connect.

Follow the [Unpairing Guide](UNPAIRING.md) for step-by-step instructions.

### Pairing fails (no `auth success` in logs)

- Ensure the shaver is **not connected to your phone** (disconnect Bluetooth or
  close the [GroomTribe](https://www.philips.at/c-w/malegrooming/products/groomtribe-app.html) app)
- The shaver must be **powered on or on the charging stand**
- Pairing is handled automatically on connect — no manual button press required
- The SMP parameters in the component work across all ESP32 boards

### "No ESPHome devices found" in HA config flow

- The ESP32 must be fully set up and connected to Home Assistant via the ESPHome
  integration first
- Check **Settings > Devices & Services > ESPHome** — your device should be listed there
- If using a fresh ESPHome install, wait for the device to come online after flashing

### "Failed to connect to the shaver" during setup

- The ESP32 must be connected and paired with the shaver (check Step 4)
- Ensure the shaver is powered on and in range of the ESP32
- Check ESPHome logs for connection errors or disconnect events

### No data after OTA update

After an OTA flash, the ESP32 reboots and reconnects to the shaver via BLE before
Home Assistant re-establishes the API stream (~5-10 seconds). The bridge automatically
re-fires the "ready" event every 15 seconds until HA subscribes to notifications.
If data still doesn't flow:

- **Reload the integration** in HA (Settings > Devices & Services > Philips Shaver > ⋮ > Reload)
- Check ESPHome logs for `BLE connected, no subscriptions — re-firing ready`
- Check HA logs for `ESP bridge rebooted — forcing re-setup`

### ESP32 disconnects frequently

- Place the ESP32 within ~5m of the shaver for a stable BLE connection
- The `auto_connect: true` setting will automatically reconnect after disconnections
- WiFi and BLE coexistence is managed automatically (`balanced` mode)

## Architecture

```
┌──────────┐   BLE    ┌─────────┐  WiFi/API  ┌─────────────────┐
│  Shaver  │◄────────►│  ESP32  │◄──────────►│ Home Assistant   │
│          │  paired  │  Bridge │  ESPHome   │ Philips Shaver   │
└──────────┘          └─────────┘  services  │ Integration      │
                                              └─────────────────┘
```

- **ESP32 → HA**: fires `esphome.philips_shaver_ble_data` events with characteristic
  UUID and hex payload
- **HA → ESP32**: calls ESPHome services (`ble_read_char`, `ble_subscribe`,
  `ble_write_char`, `ble_unsubscribe`, `ble_get_info`) with service and characteristic UUIDs
- **Diagnostics**: `ble_get_info` returns bridge version, uptime, free heap, pairing status,
  and active subscription count — used during config flow and for troubleshooting
