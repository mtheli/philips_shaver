# ESP bridge known issues

Issues with the ESP32 bridge, ESPHome and ESP-IDF. Issues with Bluetooth adapters on the Home Assistant host and with the shavers themselves are in the [general known issues](../docs/KNOWN_ISSUES.md).

## Contents

| Issue | Affects | Known since | Status |
| :--- | :--- | :--- | :--- |
| [ESP bridge loses pairings with ESP-IDF 5.5.6](#esp-bridge-loses-pairings-with-esp-idf-556) | ESPHome 2026.10.0 (ESP-IDF 5.5.6) | 2026-10-25 | ⚠️ Workaround: ESP-IDF 5.5.5 |
| [Standard ESPHome Bluetooth proxies cannot pair a shaver](#standard-esphome-bluetooth-proxies-cannot-pair-a-shaver) | Standard ESPHome Bluetooth proxies | 2026-07-22 | ℹ️ By design, use the bridge |

---

## ESP bridge loses pairings with ESP-IDF 5.5.6

**Known since:** 2026-10-25

**Status:** Bug in ESP-IDF 5.5.6 ([espressif/esp-idf#19286](https://github.com/espressif/esp-idf/issues/19286)), not fixed in any release yet. Workaround: build the bridge with ESP-IDF 5.5.5.

ESPHome 2026.10.0 builds with ESP-IDF 5.5.6 by default. In that version, the Bluetooth stack drops the stored pairing from memory when a paired shaver reconnects, and deletes the device record when the connection ends. On the next connection attempt the bridge has no key anymore and starts a new pairing, which the shaver refuses because it is still paired.

### Symptoms

- The shaver stays connected for hours, but after the first disconnect it does not reconnect anymore.
- The bridge log shows `Deleting unpaired device` when the connection ends, and then `auth fail reason=82` on the next attempts.
- After three failed attempts the bridge deletes its copy of the pairing. From then on only unpairing on the shaver and pairing again helps.
- Home Assistant shows a repair issue "Philips Shaver: ESP bridge … loses pairings (ESP-IDF v5.5.6)". The bridge reports its ESP-IDF version, and the integration raises the issue whenever it is 5.5.6.

### Fix

Pin ESP-IDF 5.5.5 in the bridge's YAML, then rebuild and flash it:

```yaml
esp32:
  framework:
    type: esp-idf
    version: 5.5.5
```

ESPHome prints a warning that this is not the recommended framework version; that is expected. A working pairing stays valid. If the bridge is already in the `reason=82` loop, unpair on the shaver and pair again once.

Remove the line again once an ESPHome release ships an ESP-IDF version with the fix.

---

## Standard ESPHome Bluetooth proxies cannot pair a shaver

**Known since:** 2026-07-22

**Status:** By design (proxy firmware limitation), use the dedicated bridge instead

Philips shavers pair via **LE Secure Connections with numeric comparison**.
A standard ESPHome `bluetooth_proxy` runs with `io_capability: none`, which
can only produce Just Works pairings — the proxy-side stack does not even
attempt the handshake, and every encrypted read fails with
`status=5` (insufficient authentication). Verified at the protocol level:
the proxy holds the connection, both probe reads fail, no SMP traffic
appears.

The config flow detects a proxy-carried connection and shows a dedicated
dialog with the working alternatives instead of running pairing tools that
cannot reach the proxy's bond store:

1. Set the shaver up via a **local Bluetooth adapter** on the Home
   Assistant host.
2. Use the dedicated **[ESP32 BLE Bridge](ESP_BRIDGE_SETUP.md)** — its
   firmware ships display-capable IO (DisplayYesNo) with auto-confirm, so
   the numeric-comparison pairing completes on the ESP32.

A proxy is still useful *alongside* the bridge for other BLE devices — the
bridge component and a `bluetooth_proxy` can share one ESP32.
