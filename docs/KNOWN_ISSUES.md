# Known issues

Limitations that sit outside the integration — in the host adapter, the Bluetooth stack or the shaver firmware — collected here so they are easy to rule in or out when setup misbehaves.

> **Using an ESP32 bridge or an ESPHome Bluetooth proxy?** Issues with the bridge, ESPHome and ESP-IDF are in the [ESP bridge known issues](../esphome/KNOWN_ISSUES.md).

## Contents

| Issue | Affects | Known since | Status |
| :--- | :--- | :--- | :--- |
| [Some USB dongles cannot complete SMP bonding](#some-usb-dongles-cannot-complete-smp-bonding) | Some USB Bluetooth dongles | 2026-07-22 | ❌ Adapter limitation |
| [Realtek RTL8852BE: shaver drops the connection after ~30 s](#realtek-rtl8852be-shaver-drops-the-connection-after-30-s) | Realtek RTL8852BE Wi-Fi/Bluetooth cards | 2026-10-31 | ❌ Adapter limitation |

---

## Some USB dongles cannot complete SMP bonding

**Known since:** 2026-07-22

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

## Realtek RTL8852BE: shaver drops the connection after ~30 s

**Known since:** 2026-10-31

**Status:** Adapter limitation, no integration-side fix

With the Bluetooth part of a **Realtek RTL8852BE** Wi-Fi/Bluetooth card as the host adapter, the connection itself works: the shaver pairs, all reads succeed and live monitoring starts. About 30 seconds after every connect, though, the shaver closes the link. Because it keeps advertising, the integration reconnects right away, and the cycle repeats every ~35 s around the clock.

### Symptoms

- The log shows `connection lost` roughly 30 s after each `connected via hci…`, with very little variation between cycles.
- `Wake via ADV` follows a few seconds later, and the loop starts over.
- Signal strength, pairing and a phone in range are not the cause; the same shaver stays connected on a different adapter.

### Confirmed affected adapter

- **Realtek RTL8852BE**, the built-in Wi-Fi/Bluetooth card of a Firebat R3 mini PC (also sold as CDW-C9852BE-00), with an S7887 over Direct Bluetooth. Moving to a different adapter ended the loop ([#27](https://github.com/mtheli/philips_shaver/issues/27)).

### Mitigations

1. **Use a different adapter.** See the list under [Some USB dongles cannot complete SMP bonding](#mitigations).
2. **Use the [ESP32 BLE Bridge](ESP_BRIDGE_SETUP.md)**, which takes the host adapter out of the equation.
3. If neither is possible right now, disable the config entry to spare the shaver's battery.

---

## Moved sections

These sections now live in the [ESP bridge known issues](../esphome/KNOWN_ISSUES.md). The headings stay here so that older links keep working.

### ESP bridge loses pairings with ESP-IDF 5.5.6

Moved to the [ESP bridge known issues](../esphome/KNOWN_ISSUES.md#esp-bridge-loses-pairings-with-esp-idf-556).

### Standard ESPHome Bluetooth proxies cannot pair a shaver

Moved to the [ESP bridge known issues](../esphome/KNOWN_ISSUES.md#standard-esphome-bluetooth-proxies-cannot-pair-a-shaver).
