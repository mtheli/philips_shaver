# Philips Shaver Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/mtheli/philips_shaver)](https://github.com/mtheli/philips_shaver/releases)
[![License: MIT](https://img.shields.io/github/license/mtheli/philips_shaver)](LICENSE)

This is a custom component for Home Assistant to integrate **Philips Bluetooth-enabled shavers**.

The integration connects to your shaver via **Bluetooth Low Energy (BLE)** to provide status, usage, and advanced telemetry data. It automatically detects the capabilities of your specific model during setup to only show relevant entities.

![Device overview in Home Assistant](./images/device.png)

Two connection methods are supported:

1.  **Direct Bluetooth** — connects from the HA host's Bluetooth adapter. Event-driven: detects when the shaver wakes up via BLE advertisements, then establishes a persistent live connection.
2.  **ESP32 BLE Bridge** — an ESP32 running ESPHome acts as a wireless BLE relay. Ideal when the shaver is out of Bluetooth range of the HA host.

See [Configuration](#configuration) for setup instructions.

---

## Table of Contents

- [Tested Models](#tested-models)
- [Lovelace Card](#lovelace-card)
- [Community](#community)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Option A: Direct Bluetooth](#option-a-direct-bluetooth-pairing)
  - [Option B: ESP32 BLE Bridge](#option-b-esp32-ble-bridge)
- [Example Automations](#example-automations)
- [Troubleshooting & Caveats](#troubleshooting--caveats)
- [BLE Protocol](#ble-protocol)
- [Screenshots](#screenshots)

---

## Tested Models

| Model | Type | Direct BLE | ESP32 Bridge | Tested by |
| :--- | :--- | :---: | :---: | :--- |
| [**Series 7000 / S7886**](https://www.usa.philips.com/c-p/S7886_84/shaver-series-7000-wet-dry-electric-shaver) | Shaver | :white_check_mark: | | Community ([#5](https://github.com/mtheli/philips_shaver/issues/5)) |
| [**Series 7000 / S7887**](https://www.usa.philips.com/c-p/S7887_82/shaver-series-7000-wet-dry-electric-shaver) | Shaver | | :white_check_mark: | Community ([forum](https://community.home-assistant.io/t/philips-bluetooth-shaver-monitoring/858822/8)) |
| [**Series 9000 / XP9201**](https://www.usa.philips.com/c-p/XP9201_88/i9000-prestige-wet-dry-electric-shaver-with-senseiq) | Shaver | :white_check_mark: | :white_check_mark: | Maintainer |
| [**Series 9000 / XP9400**](https://www.usa.philips.com/c-p/XP9400_89/i9000-prestige-ultra-wet-dry-electric-shaver-with-senseiq-pr) | Shaver | | :white_check_mark: | Community ([#3](https://github.com/mtheli/philips_shaver/issues/3)) |
| [**Series 9000 / XP9405**](https://www.usa.philips.com/c-p/XP9405_84/i9000-prestige-ultra-wet-dry-electric-shaver-with-senseiq-pr) | Shaver | :white_check_mark: | | Community ([forum](https://community.home-assistant.io/t/has-anyone-integrated-philips-s9000-with-home-assistant/592101/6)) |
| [**OneBlade 360 / QP4530**](https://www.usa.philips.com/c-p/QP4530_90/oneblade-360-with-connectivity-face) | Groomer | :white_check_mark: | :white_check_mark: | Maintainer |

Other BLE-enabled Philips shavers and groomers using the same GATT services may also work. The integration auto-detects available services and capabilities during setup — entities are only created for features your device supports. If your model works, please [let us know](https://github.com/mtheli/philips_shaver/issues) so we can add it to the list!

---

## Lovelace Card

A dedicated dashboard card is available: **[Philips Shaver Card](https://github.com/mtheli/philips_shaver_card)**

![Philips Shaver Card](./images/card_shaving.png)

The card automatically switches between standby, shaving, charging, and cleaning modes with live pressure gauge, battery status, and session stats.

---

## Community

- [Smartes Badezimmer? So hilft dir ein Shelly Wall Display beim Zähneputzen & Rasieren!](https://www.youtube.com/watch?v=ROI91x2Swv8) — Video by [@smartmatic](https://github.com/smartmatic) showing the integration and card on a Shelly Wall Display with XP9405 and ESP32 Bridge (German)

---

## Features

This integration creates a new device for your shaver and provides the following entities based on your device's hardware:

### Main Controls & Status
| Entity | Type | Description |
| :--- | :--- | :--- |
| **Activity** | Sensor | Current detailed status (`Off`, `Shaving`, `Charging`, `Cleaning`, `Locked`). |
| **Shaving Mode** | Select | Change the shaving intensity (e.g., `Sensitive`, `Normal`, `Intense`, `Custom`, `Foam`). |
| **Battery Level** | Sensor | The current battery charge level (`%`). |
| **Travel Lock** | Binary Sensor | Indicates if the travel lock is active. |
| **Charging** | Binary Sensor | Indicates if the shaver is currently charging. |
| **Light Ring** | Switch | Enable or disable the pressure coaching light ring. |
| **Handle Load Type** | Sensor | Detected head attachment (`Shaving Heads`, `Trimmer`, `Styler`, `Brush`, etc.). |
| **Motion** | Sensor | Live motion feedback (`No Motion`, `Small Circles`, `Large Strokes`). |

### Pressure, Motor & Coaching (S7000/S9000)
| Entity | Type | Description |
| :--- | :--- | :--- |
| **Pressure Value** | Sensor | Live pressure data from the sensor. |
| **Pressure State** | Sensor | Categorized feedback (`Too Low`, `Optimal`, `Too High`). |
| **Pressure Light Ring** | Light | Configure the LED ring colors for various pressure states. |
| **Light Ring Brightness** | Select | Adjust the pressure light ring brightness (`High`, `Medium`, `Low`). |
| **Motor Speed** | Sensor | Current motor speed in RPM (e.g., ~2200 RPM). |
| **Motor Current** | Sensor | Current motor power consumption in mA. |

### Speed Coaching (OneBlade)
| Entity | Type | Description |
| :--- | :--- | :--- |
| **Speed** | Sensor | Live grooming speed (0–200 raw). |
| **Speed Verdict** | Sensor | Real-time feedback (`Optimal`, `Too Slow`, `Too Fast`). Computed locally from speed and zone thresholds. |

### Usage & Maintenance
| Entity | Type | Description |
| :--- | :--- | :--- |
| **Last Session Duration** | Sensor | Duration of the last shaving session in seconds. |
| **Total Operating Time** | Sensor | Lifetime usage of the shaver. |
| **Days Since Last Used** | Sensor | Days elapsed since the last use. |
| **Charge Cycles** | Sensor | Total number of charge cycles. |
| **Remaining Shaves** | Sensor | Estimated number of shaves remaining based on battery level and usage history. |
| **Number of Uses** | Sensor | Total number of operational uses. |
| **Head Remaining** | Sensor | The remaining life of the shaver head (`%`). |
| **Blade Replacement** | Button | Confirm a blade replacement — resets the head remaining counter to 100%. |
| **Cleaning Progress** | Sensor | Progress of the cleaning cycle in `%` (if applicable). |
| **Cleaning Cycles** | Sensor | Total number of cleaning cycles. |
| **Cleaning Cartridge Remaining** | Sensor | Estimated remaining cleaning cartridge uses (accounts for fluid evaporation). |
| **Reset Cleaning Cartridge** | Button | Reset the cleaning cartridge counter after inserting a new cartridge. |

### Diagnostics
| Entity | Type | Description |
| :--- | :--- | :--- |
| **Last Seen** | Sensor | Time in minutes since the device was last reachable. |
| **RSSI** | Sensor | Bluetooth signal strength (`dBm`, direct BLE only). |
| **Shaver BLE** | Binary Sensor | BLE connection status to the shaver. |
| **ESP Bridge** | Binary Sensor | ESP32 bridge online status (ESP bridge only). |
| **Bridge Version** | Sensor | ESP bridge firmware version (ESP bridge only). |
| **Firmware** | Sensor | Installed firmware version (disabled by default). |
| **Model Number** | Sensor | Device model number (disabled by default). |

---

## Prerequisites

* A compatible Philips Shaver (see [Tested Models](#tested-models) above).
* **Either** a Home Assistant instance with the **Bluetooth integration** enabled and a working Bluetooth adapter, **or** an ESP32 running the [BLE bridge component](docs/ESP_BRIDGE_SETUP.md).
* The shaver supports only one active connection at a time — it must be **unpaired from your phone**, any manufacturer app ([GroomTribe](https://www.philips.at/c-w/malegrooming/products/groomtribe-app.html) / [OneBlade](https://www.philips.com/c-w/country-selectorpage/myoneblade.html)), **and from the device itself** before Home Assistant can connect.

---

## Installation

### HACS (Recommended)

> Don't have HACS yet? Follow the [HACS installation guide](https://hacs.xyz/docs/use/) first.

1.  Go to **HACS** > **Integrations** in your Home Assistant UI.
2.  Click the three-dot menu in the top right and select **Custom repositories**.
3.  Add the URL to this repository and select the category **Integration**.
4.  Find the "Philips Shaver" integration and click **Install**.
5.  Restart Home Assistant.

### Manual Installation

1.  Copy the `custom_components/philips_shaver` directory from this repository into your Home Assistant `config/custom_components/` folder.
2.  Restart Home Assistant.

---

## Configuration

The integration supports two connection methods:

| | Method | Best for |
| :--- | :--- | :--- |
| **[Option A](#option-a-direct-bluetooth-pairing)** | **Direct Bluetooth** | HA host is within Bluetooth range of the shaver (typically 5–10 m / 15–30 ft, less through walls) |
| **[Option B](#option-b-esp32-ble-bridge)** | **ESP32 BLE Bridge** | Shaver is out of range — a small ESP32 device placed near the shaver relays data over WiFi |

> [!IMPORTANT]
> The shaver must be **fully unpaired** (from your phone **and** the device itself) before connecting to Home Assistant.
> Follow the [Unpairing Guide](docs/UNPAIRING.md) for step-by-step instructions.

### Option A: Direct Bluetooth (Pairing)

1.  Ensure the shaver is **turned on**.
2.  Navigate to **Settings > Devices & Services**.
3.  The shaver should appear under **Discovered** — click **Configure**.
    - If not discovered automatically, click **+ Add Integration**, search for "**Philips Shaver**", and enter the MAC address manually.
4.  Click **Submit**. The integration connects and pairs automatically.

> [!TIP]
> **Automatic pairing** works out of the box on Home Assistant OS and any Linux system with BlueZ. Pairing, trusting, and stale bond removal are handled automatically via D-Bus — no terminal commands needed.

<details>
<summary>Manual Pairing (Fallback for Docker, macOS, etc.)</summary>

On systems without D-Bus, the integration will show instructions for manual pairing via terminal instead. You have two options:

#### Automated Pairing Script

```bash
bash /config/custom_components/philips_shaver/scripts/pair.sh
```

The script scans for nearby Philips devices, lets you choose which one to pair, and handles the `bluetoothctl` agent setup required for LE Secure Connections.

You can also pair a specific device directly:

```bash
bash /config/custom_components/philips_shaver/scripts/pair.sh AA:BB:CC:11:22:33
```

#### Manual Pairing with `bluetoothctl`

1.  Start the Bluetooth control tool:

    ```bash
    bluetoothctl
    ```

2.  Register the pairing agent (required for LE Secure Connections):

    ```bash
    agent KeyboardDisplay
    default-agent
    ```

3.  Start scanning to find your shaver. It will appear as "Philips XP9201" or similar. Note down its **MAC Address** (e.g., `AA:BB:CC:11:22:33`).

    ```bash
    scan on
    # ... Wait for the shaver to appear and note the address.
    scan off
    ```

4.  Pair and trust the device:

    ```bash
    pair AA:BB:CC:11:22:33
    trust AA:BB:CC:11:22:33
    exit
    ```

After manual pairing, return to the integration setup dialog and click **Submit** to retry.

</details>

### Option B: ESP32 BLE Bridge

If your Home Assistant host is too far from the shaver for a direct Bluetooth connection, you can use an [ESP32](https://esphome.io/components/esp32.html) as a wireless BLE bridge. The ESP32 connects to the shaver and relays data to HA over WiFi.

This is **not** a standard ESPHome Bluetooth Proxy — it is a custom component that handles the shaver's LE Secure Connections pairing and provides full read/write/subscribe access to all GATT characteristics.

A single ESP32 can bridge **multiple devices** (e.g. a shaver and an OneBlade simultaneously).

> **Note:** This option requires basic [ESPHome](https://esphome.io/) knowledge (flashing firmware, editing YAML configs). If you're new to ESPHome, check out [Getting Started with ESPHome](https://esphome.io/guides/getting_started_hassio) first.

For the complete setup guide, see **[ESP Bridge Setup Guide](docs/ESP_BRIDGE_SETUP.md)**.

---

## Example Automations

See **[AUTOMATIONS.md](docs/AUTOMATIONS.md)** for ready-to-use automation examples, including low battery alerts, smart plug charging, usage reminders, and maintenance notifications.

---

## Troubleshooting & Caveats

* *Pairing fails*: The shaver must be unpaired from **both** your phone's Bluetooth settings **and** from the device itself. Unpairing in the app alone is not enough — see the [unpairing instructions](#configuration) for your model. This is the most common cause of pairing failures.
* *Connection Conflict*: If the integration fails to set up, ensure no smartphone is currently connected to the shaver.
* *ESPHome Bluetooth Proxy*: The standard ESPHome Bluetooth Proxy does **not** work with this shaver because it requires LE Secure Connections pairing. Use the dedicated [ESP32 BLE Bridge](docs/ESP_BRIDGE_SETUP.md) instead.
* *Stability:* Bluetooth signals are weak. Ensure your HA host or ESP32 bridge is placed as close to the shaver's location as possible.

---

## BLE Protocol

The integration communicates directly via BLE — no cloud, no app required. All communication is fully local.

The shaver exposes multiple GATT services with individual characteristics for each data point (battery, motor, pressure, light ring, etc.). Data is read directly from these characteristics and live updates are received via GATT notifications.

For a detailed technical description of the BLE protocol including service UUIDs, characteristic reference, data formats, and capability flags, see [PROTOCOL.md](docs/PROTOCOL.md).

For debug service actions (reading arbitrary BLE characteristics via Developer Tools), see [ADVANCED.md](docs/ADVANCED.md).

## Screenshots

| Discovery | Capabilities | Device | Diagnostics |
| :---: | :---: | :---: | :---: |
| ![Discovery](./images/discovery.png) | ![Capabilities](./images/capabilities.png) | ![Device](./images/device.png) | ![Diagnostics](./images/diagnostic.png) |

## Disclaimer

This is an independent community project and is not affiliated with, endorsed by, or sponsored by Philips. All product names, trademarks, and registered trademarks are property of their respective owners.

## License

[MIT](LICENSE)