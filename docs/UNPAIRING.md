# Unpairing Guide

The shaver can only be paired with **one device at a time**. Before connecting it to
Home Assistant (via Direct Bluetooth or ESP32 Bridge), you must remove all existing
pairings. This is a **two-step process** — both steps are required.

## Step 1: Unpair from your phone

Remove the shaver from your phone's Bluetooth settings **and** from the Philips app:
- **S7000 / S9000 shavers** → [GroomTribe app](https://www.philips.at/c-w/malegrooming/products/groomtribe-app.html)
- **OneBlade models** → [OneBlade app](https://www.philips.com/c-w/country-selectorpage/myoneblade.html)

How to remove a Bluetooth device:
- [Android / Samsung](https://www.samsung.com/ca/support/mobile-devices/unpair-a-bluetooth-device-from-your-samsung-galaxy/) — Settings → Connections → Bluetooth → tap the gear icon next to the shaver → Unpair
- [iPhone / iPad](https://support.apple.com/en-us/105108) — Settings → Bluetooth → tap the ⓘ next to the shaver → Forget This Device

## Step 2: Unpair on the device itself

The shaver stores its own pairing bond. App-only unpairing is **not enough** — you must
also reset the pairing on the device:

- **S7000 series**: Press and hold the on/off button for at least **10 seconds** until the
  notification symbol lights up 4 times briefly. Note: ~5 seconds activates travel mode —
  keep holding.
  ([Manual, p. 57](https://www.documents.philips.com/assets/20230524/321aee78595d447cb224b00c008c2dda.pdf))
- **i9000 / S-series shavers**: Press the menu button until you reach the Bluetooth menu,
  hold it until a cross and checkmark appear, then press again to select the checkmark.
  ([Manual](https://www.manualslib.com/guide/4036443/philips-i9000-prestige-xp9205-05-xp9204-30-xp9203-32-xp9202-20-manual.html#unpair-the-shaver-and-smartphone))
- **OneBlade 360**: Hold the power button for **10 seconds** until the light ring starts
  flashing blue.
  ([Philips Support](https://www.usa.philips.com/c-t/XC000020493/my-oneblade-360-connected-is-not-pairing-with-my-phone))

## Optional: Unpair from the HA host

If you are switching from Direct Bluetooth to the ESP32 Bridge, also remove the pairing
from the HA host:

```bash
bluetoothctl remove <SHAVER_MAC>
```

After completing all steps, the shaver is ready to pair with Home Assistant or the ESP32
bridge.
