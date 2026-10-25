# Known Issues

Limitations that sit outside the integration — in the host adapter, the
Bluetooth stack or the shaver firmware — collected here so they are easy to
rule in or out when setup misbehaves.

---

## ESP bridge loses pairings with ESP-IDF 5.5.6

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

## Some USB dongles cannot complete SMP bonding

**Status:** Hardware limitation of the adapter's SMP implementation, no integration-side fix

Every supported shaver requires a successful **SMP bonding handshake**
during setup — and Philips shavers use **LE Secure Connections** with
numeric comparison, which is more demanding than legacy pairing. Some cheap
USB Bluetooth dongles connect fine but never complete that handshake — the
pairing runs into a timeout or auth error on every attempt, while the very
same shaver bonds immediately on a different adapter on the same host.

### Symptoms

- The pairing step fails repeatably (`pairing_failed`) — the connection
  itself is established and held, it is the pairing that never finishes.
- Manual `bluetoothctl` pairing fails with
  `org.bluez.Error.AuthenticationCanceled` or `AuthenticationFailed`.
- Moving the *same* setup to another adapter (e.g. the Raspberry Pi's
  built-in radio) bonds within one or two attempts.

### Confirmed affected adapter

- Generic "100 m long-range" BT 5.3 USB dongle with an **Actions**
  chipset (Bluetooth company ID `0x03E0`), sold under UGREEN and many
  other brand names — reported against the sibling Sonicare integration in
  [philips_sonicare_ble#27](https://github.com/mtheli/philips_sonicare_ble/issues/27).
  The Pi's built-in Cypress radio bonded the same device on the second try.
  The shaver's LESC requirement makes it at least as sensitive to these
  dongles as the bonding-required toothbrush models.

Not every pairing failure is the adapter, though. The most common cause is
a leftover bond: the shaver must be unpaired from **both** your phone's
Bluetooth settings **and** the device itself (see the
[Unpairing Guide](UNPAIRING.md)). Only when the handshake times out
consistently on one adapter and succeeds on another is the dongle the
culprit.

### Mitigations

1. **Use a bonding-capable adapter** — the Raspberry Pi's built-in radio,
   Intel AX200/AX210-class M.2 combos, or a genuine CSR8510A10 dongle.
2. **Use the [ESP32 BLE Bridge](ESP_BRIDGE_SETUP.md)** — it performs the
   bonding on the ESP32 itself, taking the host adapter out of the
   equation entirely.

---

## Standard ESPHome Bluetooth proxies cannot pair a shaver

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
