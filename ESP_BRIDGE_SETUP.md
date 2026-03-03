# ESP32 BLE Bridge Setup Guide

This guide explains how to set up an ESP32 as a Bluetooth Low Energy (BLE) bridge
for the Philips Shaver Home Assistant integration. The ESP32 connects to the shaver
via BLE and relays data to Home Assistant over WiFi, removing the need for direct
Bluetooth access from the HA host.

## Prerequisites

- **ESP32 board** — tested with [M5Stack Atom Lite](https://docs.m5stack.com/en/core/ATOM%20Lite),
  any ESP32 with BLE should work (ESP32-S3, ESP32-C3, etc.)
- **ESPHome** — installed as Home Assistant add-on or standalone
- **Philips Shaver** — tested with i9000 / XP9201, other BLE-enabled Philips shavers
  may work with the same service UUIDs

## Step 1: Find Your Shaver's MAC Address

The shaver advertises via BLE when it is powered on or placed on the charging stand.

**Option A — Home Assistant Bluetooth:**
1. Go to **Settings > Devices & Services > Bluetooth**
2. Look for a device named "Philips XP9201" (or similar)
3. Note the MAC address (e.g. `EC:EC:66:27:F0:ED`)

**Option B — nRF Connect (Android/iOS):**
1. Open the nRF Connect app and scan for devices
2. Filter for "Philips" — the shaver shows up with its MAC address

**Option C — ESPHome logs:**
1. Deploy any ESP32 with `esp32_ble_tracker` enabled
2. Check logs for `Found device ... Name: 'Philips XP9201'`

## Step 2: Create the ESPHome Configuration

Choose a template based on your board:

| Board | Template |
|-------|----------|
| Generic ESP32 (DevKit, etc.) | [`esphome/esp32-generic.yaml`](esphome/esp32-generic.yaml) |
| M5Stack Atom Lite | [`esphome/atom-lite.yaml`](esphome/atom-lite.yaml) |

Copy the template to your ESPHome configuration directory and customize:

### Required changes

1. **Shaver MAC address** — replace `EC:EC:66:27:F0:ED` with your shaver's MAC:
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
- **sdkconfig options**: `CONFIG_BT_GATTC_MAX_CACHE_CHAR: "100"` and
  `CONFIG_BT_GATTC_NOTIF_REG_MAX: "30"` — the shaver has ~66 GATT attributes and
  we subscribe to 17+ characteristics
- **API flags**: `custom_services: true` and `homeassistant_services: true` — required
  for the bridge component to register its services
- **external_components**: the component is loaded directly from this GitHub repository

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

The key line is **`auth success type = 1 mode = 9`** — this confirms LE Secure Connections
pairing succeeded. If you don't see this, check the troubleshooting section below.

## Step 5: Add the Integration in Home Assistant

1. Go to **Settings > Devices & Services > Integrations**
2. Click **+ Add Integration** and search for **Philips Shaver**
3. Select **ESP32 Bridge (ESPHome)**
4. Choose your ESP device from the dropdown (e.g. "Atom Lite BLE Bridge (atom-lite)")
5. The integration will read the shaver's capabilities via the ESP32 bridge
6. Click **Submit** to finish — the shaver appears as a sub-device of the ESP32

## Troubleshooting

### Pairing fails (no `auth success` in logs)

- Ensure the shaver is **not connected to your phone** (disconnect Bluetooth or
  close the GroomTribe app)
- The shaver must be **powered on or on the charging stand**
- Try pressing the pairing button on the ESP32 (Atom Lite: GPIO39 button)
- If using a different ESP32 board, the SMP parameters in the component should still
  work — the pairing is handled automatically

### "No ESPHome devices found" in HA config flow

- The ESP32 must be fully set up and connected to Home Assistant via the ESPHome
  integration first
- Check **Settings > Devices & Services > ESPHome** — your device should be listed there
- If using a fresh ESPHome install, wait for the device to come online after flashing

### "Failed to connect to the shaver" during setup

- The ESP32 must be connected and paired with the shaver (check Step 4)
- Ensure the shaver is powered on and in range of the ESP32
- Check ESPHome logs for connection errors or disconnect events

### ESP32 disconnects frequently

- Place the ESP32 within ~5m of the shaver for a stable BLE connection
- The `auto_connect: true` setting will automatically reconnect after disconnections
- WiFi and BLE coexistence is managed automatically (`balanced` mode)

## Architecture

```
┌──────────┐   BLE    ┌─────────┐  WiFi/API  ┌─────────────────┐
│  Shaver  │◄────────►│  ESP32  │◄──────────►│ Home Assistant   │
│ XP9201   │  paired  │  Bridge │  ESPHome   │ Philips Shaver   │
└──────────┘          └─────────┘  services  │ Integration      │
                                              └─────────────────┘
```

- **ESP32 → HA**: fires `esphome.philips_shaver_ble_data` events with characteristic
  UUID and hex payload
- **HA → ESP32**: calls ESPHome services (`ble_read_char`, `ble_subscribe`,
  `ble_write_char`, `ble_unsubscribe`) with service and characteristic UUIDs

## Tested Hardware

| Board | Status |
|-------|--------|
| M5Stack Atom Lite (ESP32-PICO) | Confirmed working |
| Generic ESP32-DevKit | Should work (same SoC) |
| ESP32-S3 / ESP32-C3 | Untested — BLE stack should be compatible |
