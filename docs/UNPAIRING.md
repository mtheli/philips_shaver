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

## Last resort: Factory reset (30 seconds)

If the shaver still refuses **every** pairing attempt after both steps above — it does
not react to pairing requests from Home Assistant, the ESP32 bridge, *or* the official
Philips app — the device may be stuck on a stale internal pairing state. A factory
reset clears it ([Philips Support](https://www.philips.sa/en/c-f/XC000019877/i-cannot-connect-my-philips-shaver-to-the-groomtribe-app)):

- Press and hold the on/off button for about **30 seconds**. This is different from the
  10-second hold in Step 2, which only resets the Bluetooth pairing — keep holding well
  past that point.
- **OneBlade**: release the button **as soon as the light turns red** — do not keep
  holding until the red light goes out again. The indicator then cycles
  red → blue → red → white; once the cycle finishes, the reset is complete.

After the factory reset the shaver accepts pairing requests again. Note that it may
take a couple of minutes for the first connection to establish.

## Optional: Unpair from the HA host

If you are switching from Direct Bluetooth to the ESP32 Bridge, also remove the pairing
from the HA host:

```bash
bluetoothctl remove <SHAVER_MAC>
```

After completing all steps, the shaver is ready to pair with Home Assistant or the ESP32
bridge.
