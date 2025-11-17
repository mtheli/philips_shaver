# Philips Shaver Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

This is a custom component for Home Assistant to integrate **Philips Bluetooth-enabled shavers**, specifically tested with the **i9000 / XP9201 series**.

![Screenshot of the device inHA](./images/screenshot.png)

The integration connects to your shaver via **Bluetooth Low Energy (BLE)** to provide status and usage data. It employs a dual-connection approach:

1.  **Live Connection:** A persistent connection is maintained while the device is in range, offering instant updates for the device state (Shaving/Charging) and travel lock status.
2.  **Poll Fallback:** A periodic poll (every 60 seconds) runs as a fallback to retrieve other device data.

---

## Features

This integration creates a new device for your shaver and provides the following entities:

| Entity | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| **Battery Level** | Sensor | `%` | The current battery charge level. |
| **Head Remaining** | Sensor | `%` | The remaining life of the shaver head. |
| **Last Shaving Time** | Sensor | `s` | Duration of the last shave. |
| **Days Since Last Used** | Sensor | `d` | Days elapsed since the last use. |
| **State** | Select | - | Current operating status (`Off`, `Shaving`, `Charging`). |
| **Travel Lock** | Binary Sensor | - | Indicates if the travel lock is active. |
| **In Use** | Binary Sensor | - | Indicates if the device is actively shaving. |
| **RSSI** | Sensor | `dBm` | Bluetooth signal strength. (Diagnostic) |
| **Firmware** | Sensor | - | Firmware version. (Diagnostic) |

---

## Prerequisites

* A Home Assistant instance with the **Bluetooth integration** enabled and a working Bluetooth adapter.
* A compatible Philips Shaver (e.g., i9000/XP9201).
* The shaver must be within Bluetooth range of your Home Assistant device or a Bluetooth proxy.

---

## Installation

### HACS (Recommended)

1.  Go to **HACS** > **Integrations** in your Home Assistant UI.
2.  Click the three-dot menu in the top right and select **Custom repositories**.
3.  Add the URL to this repository and select the category **Integration**.
4.  Find the "Philips Shaver" integration and click **Install**.
5.  Restart Home Assistant.

### Manual Installation

1.  Copy the `custom_components/philips_shaver` directory from this repository into your Home Assistant `config/custom_components/` folder.
2.  Restart Home Assistant.

---

## Configuration (Pairing)

**Crucial Step:** This integration requires that the shaver be **paired at the operating system (OS) level** of your Home Assistant host before you can add the integration in Home Assistant.

### Step 1: OS-Level Pairing with `bluetoothctl`

You must access the terminal of your Home Assistant server (e.g., via SSH or the "Terminal & SSH" add-on).

1.  Ensure your shaver is **turned on or placed on its charging stand**.
2.  Start the Bluetooth control tool:

    ```bash
    bluetoothctl
    ```

3.  Start scanning to find your shaver. It will likely appear as "Shaver" or similar. Note down its **MAC Address** (e.g., `AA:BB:CC:11:22:33`).

    ```bash
    scan on
    # ... Wait for the shaver to appear and note the address.
    scan off
    ```

4.  Perform the pairing with the shaver's MAC address. **Replace** the placeholder with your device's actual address.

    ```bash
    pair AA:BB:CC:11:22:33
    ```

5.  Trust the device to ensure stable auto-reconnection:

    ```bash
    trust AA:BB:CC:11:22:33
    ```

6.  Exit the tool:

    ```bash
    exit
    ```

The shaver is now paired with your host system.

### Step 2: Adding the Integration in Home Assistant

Once the OS-level pairing is complete, proceed to add the integration via the Home Assistant UI.

#### Method 1: Automatic Discovery (Recommended)

1.  Navigate to **Settings > Devices & Services**.
2.  If pairing was successful, Home Assistant should automatically discover the shaver and list it under **Discovered**.
3.  Click **Configure** on the discovered device card and confirm the setup by clicking **Submit**.

#### Method 2: Manual Setup

1.  If the shaver is not automatically discovered, click **+ Add Integration**.
2.  Search for "**Philips Shaver**" and select the integration.
3.  Enter the **MAC Address** (e.g., `AA:BB:CC:11:22:33`) you used in Step 1.
4.  Click **Submit**.

---

## Troubleshooting & Caveats

* **Availability:** The integration relies on a local Bluetooth connection. If the shaver is taken out of range, it will become `Unavailable`. It should automatically reconnect once it is back in range (e.g., placed on the charger).
* **Stability:** Connection stability is highly dependent on Bluetooth signal strength. Consider using an **ESPHome Bluetooth Proxy** closer to the shaver for improved reliability.
* **Not Discovered:** Ensure the shaver is **active** (powered on or charging) during the configuration process, as a completely off device may not advertise its presence.