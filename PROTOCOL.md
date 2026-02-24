# Philips Shaver – BLE Protocol Reference

This document describes the Bluetooth Low Energy (BLE) protocol used by Philips Bluetooth-enabled shavers (tested with the i9000 / XP9201 series). All communication is fully local — no cloud service or Philips account required.

The protocol was reverse-engineered from the shaver's BLE interface.

## Overview

The Philips Shaver uses a **simple GATT read/notify pattern** — each data point has its own dedicated characteristic. Unlike command-based protocols, there is no packet assembly or state machine. Data is retrieved by reading individual characteristics, and live updates are received via GATT notifications.

The shaver requires **OS-level Bluetooth pairing** before GATT access is possible. It supports only one active connection at a time.

## Connection Model

The integration uses a dual-connection approach:

1. **Live Connection** — A persistent BLE connection with GATT notifications for real-time updates (motor RPM, pressure, device state). Active while the shaver is in range and turned on.
2. **Poll Fallback** — A periodic connect/read/disconnect cycle (default: 60 s) that runs when the live connection is unavailable (e.g. shaver in standby).

The two modes are mutually exclusive — polling is skipped while a live connection is active.

## BLE Services

### Philips Custom Services

| Service UUID | Purpose |
|-------------|---------|
| `8d560100-3cb9-4387-a7e8-b79d826a7025` | Device Properties — model, serial number, motor, battery cycles |
| `8d560200-3cb9-4387-a7e8-b79d826a7025` | Unknown Service — battery raw data, firmware, device age |
| `8d560300-3cb9-4387-a7e8-b79d826a7025` | Control Service — shaving mode, light ring, pressure |
| `8d560600-3cb9-4387-a7e8-b79d826a7025` | Cleaning Service — cleaning progress and cycles |

### Standard Bluetooth Services

| Service UUID | Purpose |
|-------------|---------|
| `0000180f-0000-1000-8000-00805f9b34fb` | Battery Service (0x180F) |
| `0000180a-0000-1000-8000-00805f9b34fb` | Device Information Service (0x180A) |

## Characteristics Reference

### Device Information (Standard GATT — Service 0x180A)

| Characteristic | UUID | Properties | Data Type | Description |
|---------------|------|------------|-----------|-------------|
| Model Number | `00002a24-0000-1000-8000-00805f9b34fb` | READ | UTF-8 string | e.g. `XP9201` |
| Serial Number | `00002a25-0000-1000-8000-00805f9b34fb` | READ | UTF-8 string | Device serial number |
| Firmware Revision | `00002a26-0000-1000-8000-00805f9b34fb` | READ | UTF-8 string | Firmware version string |

### Battery (Standard GATT — Service 0x180F)

| Characteristic | UUID | Properties | Data Type | Description |
|---------------|------|------------|-----------|-------------|
| Battery Level | `00002a19-0000-1000-8000-00805f9b34fb` | NOTIFY, READ | uint8 | Battery percentage (0–100%) |

### Device Properties (Service 8d5601xx)

| Characteristic | UUID | Properties | Format | Description |
|---------------|------|------------|--------|-------------|
| Motor Current | `8d560102-...7025` | NOTIFY, READ | uint16 LE | Current motor power draw (mA) |
| Motor Current Max | `8d560103-...7025` | READ | uint16 LE | Maximum motor current rating (mA). Example: `0x07D0` = 2000 mA |
| Motor RPM | `8d560104-...7025` | NOTIFY, READ | uint16 LE | Raw motor speed. Divide by 3.036 for RPM (e.g. ~2200 RPM) |
| Total Age | `8d560106-...7025` | NOTIFY, READ, WRITE | uint32 LE | Total device operating time (seconds) |
| Operational Turns | `8d560107-...7025` | NOTIFY, READ | uint16 LE | Number of times the shaver was turned on |
| Days Since Last Used | `8d560108-...7025` | NOTIFY, READ | uint16 LE | Days elapsed since the last use |
| Amount of Charges | `8d560109-...7025` | NOTIFY, READ | uint16 LE | Total number of charge cycles |
| Device State | `8d56010a-...7025` | NOTIFY, READ | uint8 | 1=off, 2=shaving, 3=charging |
| Travel Lock | `8d56010c-...7025` | NOTIFY, READ | uint8 | 0=unlocked, 1=locked |
| Shaving Time | `8d56010f-...7025` | NOTIFY, READ | uint16 LE | Last session duration (seconds) |
| System Notifications | `8d560110-...7025` | NOTIFY, READ, WRITE | 4 bytes | System notification flags. Example: `12 00 00 00` |
| Head Remaining | `8d560117-...7025` | NOTIFY, READ | uint8 | Shaver head remaining life (0–100%) |
| Head Remaining Minutes | `8d560118-...7025` | NOTIFY, READ | uint16 LE | Shaver head remaining life (minutes) |

### Cleaning (Service 8d5601xx / 8d5603xx)

| Characteristic | UUID | Properties | Format | Description |
|---------------|------|------------|--------|-------------|
| Cleaning Progress | `8d56011a-...7025` | NOTIFY, READ | uint8 | Cleaning cycle progress (0–100%) |
| Cleaning Cycles | `8d56031a-...7025` | NOTIFY, READ, WRITE | uint16 LE | Number of cleaning cycles performed |

### Control Service (Service 8d5603xx)

| Characteristic | UUID | Properties | Format | Description |
|---------------|------|------------|--------|-------------|
| Capabilities | `8d560302-...7025` | READ | uint32 LE | Device capability bitfield (see below) |
| Pressure | `8d56030c-...7025` | NOTIFY, READ | uint16 LE | Live pressure sensor value |
| Light Ring Low | `8d560311-...7025` | READ, WRITE | 4 bytes RGBA | LED color for low pressure state |
| Light Ring OK | `8d560312-...7025` | READ, WRITE | 4 bytes RGBA | LED color for optimal pressure state |
| Light Ring High | `8d560313-...7025` | READ, WRITE | 4 bytes RGBA | LED color for high pressure state |
| Light Ring Motion | `8d56031c-...7025` | READ, WRITE | 4 bytes RGBA | LED color for motion feedback |
| Light Ring Brightness | `8d560331-...7025` | READ, WRITE | uint8 | LED ring brightness (0–255) |
| Shaving Mode | `8d56032a-...7025` | NOTIFY, READ, WRITE | uint8 | Current shaving mode (see below) |
| Custom Mode Settings | `8d560330-...7025` | READ, WRITE | 10 bytes | Settings for custom mode (see below) |
| Mode Settings | `8d560332-...7025` | NOTIFY, READ | 10 bytes | Current active mode settings (see below) |

## Data Formats

### Device State (0x8d56010a)

| Value | State |
|-------|-------|
| 1 | Off |
| 2 | Shaving |
| 3 | Charging |

### Shaving Modes (0x8d56032a)

| Value | Mode |
|-------|------|
| 0 | Sensitive |
| 1 | Regular |
| 2 | Intense |
| 3 | Custom |
| 4 | Foam |
| 5 | Battery Saving |

### Motor RPM Conversion

The motor RPM characteristic reports a raw uint16 value. To convert to actual RPM:

```
rpm = raw_value / 3.036
```

Example: Raw value `0x07D0` (2000) = 2000 / 3.036 = ~659 RPM.

This conversion factor also applies to the motor RPM field within the shaving mode settings.

### Light Ring Colors (0x8d560311–0x8d56031c)

Each color characteristic stores 4 bytes in RGBA format:

```
Byte 0: Red   (0x00–0xFF)
Byte 1: Green (0x00–0xFF)
Byte 2: Blue  (0x00–0xFF)
Byte 3: Alpha (0x00–0xFF) — ignored by integration
```

Example: `00 8F FF FF` = RGB(0, 143, 255) — light blue.

Colors are writable, allowing customization of the LED ring for each pressure feedback state (low, optimal, high, motion).

### Shaving Mode Settings (0x8d560332 / 0x8d560330)

Both the active mode settings and the custom mode settings share the same 10-byte format. The data is structured as 5 consecutive uint16 little-endian values:

```
Bytes 0–1:  Motor RPM Raw     (uint16 LE) — divide by 3.036 for RPM
Bytes 2–3:  Pressure Base     (uint16 LE) — zero/baseline pressure value
Bytes 4–5:  Pressure Low      (uint16 LE) — lower threshold of green zone
Bytes 6–7:  Pressure High     (uint16 LE) — upper threshold of green zone
Bytes 8–9:  Feedback Window   (uint16 LE) — analysis/verdict window
```

Example: `BD 18 F4 01 DC 05 A0 0F 3C 00`
- Motor RPM Raw = `0x18BD` (6333) → 6333 / 3.036 = ~2086 RPM
- Pressure Base = `0x01F4` (500)
- Pressure Low = `0x05DC` (1500)
- Pressure High = `0x0FA0` (4000)
- Feedback Window = `0x003C` (60)

The characteristic at `0x8d560330` (Custom Mode Settings) is writable, allowing users to define their own motor speed and pressure thresholds for the "Custom" shaving mode. The characteristic at `0x8d560332` (Mode Settings) is read-only and reflects the currently active mode's parameters.

## Capability Flags (0x8d560302)

The capabilities characteristic is a uint32 bitfield read during initial setup. It determines which features the shaver hardware supports:

| Bit | Flag | Description |
|-----|------|-------------|
| 0 | Motion | Motion detection support |
| 1 | Brush | Brush head attachment |
| 2 | Motion Speed | Speed-based motion tracking |
| 3 | Pressure | Pressure sensor |
| 4 | Unit Cleaning | Cleaning unit/station support |
| 5 | Cleaning Mode | Cleaning mode available |
| 6 | Light Ring | LED ring for pressure feedback |

Example: `0x69` (binary `01101001`) = Motion + Pressure + Unit Cleaning + Light Ring.

The integration reads this value during config flow and uses it to conditionally register only the relevant entities for the connected device.

## Notification-Capable Characteristics

The following characteristics support GATT notifications (indicated by the CCCD descriptor 0x2902). The integration subscribes to all of them during a live connection for real-time updates:

- Device State, Travel Lock, Battery Level
- Operational Turns, Amount of Charges
- Cleaning Progress, Cleaning Cycles
- Motor RPM, Motor Current, Pressure
- Head Remaining, Head Remaining Minutes
- Shaving Time, Mode Settings, Total Age

## Known Quirks

| Issue | Behavior | Workaround |
|-------|----------|------------|
| Exclusive connection | Shaver allows only one BLE connection at a time | Unpair from phone/GroomTribe app before connecting HA |
| OS-level pairing required | GATT characteristics are inaccessible without prior pairing | Pair via `bluetoothctl` before adding the integration |
| No ESPHome proxy support | Requires direct active BLE connection for notifications | Use a local Bluetooth adapter on the HA host |
| Motor RPM raw values | RPM characteristic reports raw sensor values | Divide by 3.036 for actual RPM |
| Device state mapping | State byte uses 1/2/3 instead of 0/1/2 | Map 1=off, 2=shaving, 3=charging |

## Source References

The protocol was reverse-engineered from the shaver's BLE interface.
