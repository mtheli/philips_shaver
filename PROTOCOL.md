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
| `8d560100-3cb9-4387-a7e8-b79d826a7025` | [Platform Service](#platform-service-service-8d5601xx) — device state, motor, battery cycles, cleaning |
| `8d560200-3cb9-4387-a7e8-b79d826a7025` | [History Service](#history-service-service-8d5602xx) — shaving session history (timestamp, duration, RPM) |
| `8d560300-3cb9-4387-a7e8-b79d826a7025` | [Smart Shaver Handle Service](#smart-shaver-handle-service-service-8d5603xx) — shaving mode, light ring, pressure, coaching |
| `8d560600-3cb9-4387-a7e8-b79d826a7025` | Serial/Diagnostic Service — present on newer models (XP9400), purpose not yet fully known |

### Standard Bluetooth Services

| Service UUID | Purpose |
|-------------|---------|
| `0000180f-0000-1000-8000-00805f9b34fb` | [Battery Service](#battery-standard-gatt--service-0x180f) (0x180F) |
| `0000180a-0000-1000-8000-00805f9b34fb` | [Device Information Service](#device-information-standard-gatt--service-0x180a) (0x180A) |

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

### Platform Service (Service 8d5601xx)

| Characteristic | Short UUID | Properties | Format | Description |
|---------------|------------|------------|--------|-------------|
| Motor Current | `0x0102` | NOTIFY, READ | uint16 LE | Current motor power draw (mA) |
| Motor Current Max | `0x0103` | READ | uint16 LE | Maximum motor current rating (mA) |
| Motor RPM | `0x0104` | NOTIFY, READ | uint16 LE | Raw motor speed. [Divide by 3.036](#motor-rpm-conversion) for RPM |
| Motor RPM Max | `0x0105` | READ | uint16 LE | Maximum motor RPM (raw, ÷ 3.036) |
| Total Age | `0x0106` | NOTIFY, READ, WRITE | uint32 LE | Total device operating time (seconds) |
| Operational Turns | `0x0107` | NOTIFY, READ | uint16 LE | Number of times the shaver was turned on |
| Days Since Last Used | `0x0108` | NOTIFY, READ | uint16 LE | Days elapsed since the last use |
| Amount of Charges | `0x0109` | NOTIFY, READ | uint16 LE | Total number of charge cycles |
| Device State | `0x010A` | NOTIFY, READ | uint8 | [1=off, 2=shaving, 3=charging](#device-state-0x8d56010a) |
| Motor RPM Min | `0x011B` | READ | uint16 LE | Minimum motor RPM (raw, ÷ 3.036) |
| Travel Lock | `0x010C` | NOTIFY, READ | uint8 | 0=unlocked, 1=locked |
| Blade Replacement | `0x010E` | READ | uint8 | Blade replacement trigger |
| Shaving Time | `0x010F` | NOTIFY, READ | uint16 LE | Last session duration (seconds) |
| System Notifications | `0x0110` | NOTIFY, READ, WRITE | 4 bytes | System notification flags |
| Head Remaining | `0x0117` | NOTIFY, READ | uint8 | Shaver head remaining life (0–100%) |
| Head Remaining Minutes | `0x0118` | NOTIFY, READ | uint16 LE | Shaver head remaining life (minutes) |
| Cleaning Progress | `0x011A` | NOTIFY, READ | uint8 | Cleaning cycle progress (0–100%) |

### History Service (Service 8d5602xx)

| Characteristic | Short UUID | Properties | Format | Description |
|---------------|------------|------------|--------|-------------|
| History Timestamp | `0x0202` | READ | uint32 LE | Session timestamp (Unix epoch) |
| History Avg Current | `0x0206` | READ | uint16 LE | Average motor current during session (mA) |
| History Duration | `0x0207` | READ | uint16 LE | Session duration (seconds) |
| History RPM | `0x0208` | READ | uint16 LE | Average motor RPM during session (raw, ÷ 3.036) |
| History Sync Status | `0x0209` | READ, WRITE | uint8 | Controls [history playback](#shaving-history-service-0x0200) |

### Smart Shaver Handle Service (Service 8d5603xx)

| Characteristic | Short UUID | Properties | Format | Description |
|---------------|------------|------------|--------|-------------|
| Capabilities | `0x0302` | READ | uint32 LE | [Device capability bitfield](#capability-flags-0x8d560302) |
| Motion Type | `0x0305` | NOTIFY, READ | uint8 | 0=none, 1=small circle, 4=large stroke |
| Pressure | `0x030C` | NOTIFY, READ | uint16 LE | Live pressure sensor value |
| Light Ring Low | `0x0311` | READ, WRITE | [4 bytes RGBA](#light-ring-colors-0x8d5603110x8d56031c) | LED color for low pressure state |
| Light Ring OK | `0x0312` | READ, WRITE | 4 bytes RGBA | LED color for optimal pressure state |
| Light Ring High | `0x0313` | READ, WRITE | 4 bytes RGBA | LED color for high pressure state |
| App Handle Settings | `0x0319` | NOTIFY, READ, WRITE | uint32 LE | [Coaching/feedback bitfield](#app-handle-settings-0x0319) (bit 4 = light ring on/off) |
| Cleaning Cycles | `0x031A` | NOTIFY, READ, WRITE | uint16 LE | Number of cleaning cycles performed |
| Light Ring Motion | `0x031C` | READ, WRITE | 4 bytes RGBA | LED color for motion feedback |
| Handle Load Type | `0x0322` | NOTIFY, READ | uint16 LE | [Attached head type](#handle-load-type-0x0322) |
| Shaving Mode | `0x032A` | NOTIFY, READ, WRITE | uint16 LE | [Current shaving mode](#shaving-modes-0x032a--uint16-le) |
| Custom Mode Settings | `0x0330` | READ, WRITE | 10 bytes | [Settings for custom mode](#shaving-mode-settings-0x8d560332--0x8d560330) |
| Light Ring Brightness | `0x0331` | READ, WRITE | uint8 | LED ring brightness (0–255) |
| Mode Settings | `0x0332` | NOTIFY, READ | 10 bytes | [Current active mode settings](#shaving-mode-settings-0x8d560332--0x8d560330) |

## Data Formats

### Device State (0x8d56010a)

| Value | State |
|-------|-------|
| 1 | Off |
| 2 | Shaving |
| 3 | Charging |

### App Handle Settings (0x0319)

A uint32 little-endian bitfield controlling coaching and feedback features. The integration uses bit 4 to toggle the light ring:

| Bit | Flag | Description |
|-----|------|-------------|
| 4 | fullCoachingMode | Light ring on/off during shaving |
| 5 | maxPressureCoachingMode | Pressure-only coaching |

Toggle behavior: ON = set bit 4 + clear bit 5, OFF = clear bit 4 + clear bit 5. All other bits are preserved (read-modify-write).

### Handle Load Type (0x0322)

| Value | Attachment |
|-------|-----------|
| 3 | Trimmer |
| 4 | Shaving Heads |
| 5 | Styler |
| 6 | Brush |
| 7 | Precision Trimmer |
| 8 | Beardstyler |

### Shaving Modes (0x032A) — uint16 LE

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

## Shaving History (Service 0x0200)

The history service stores past shaving sessions on the device. Playback is controlled via the Sync Status characteristic (`0x0209`):

1. Write `0x01` to `0x0209` to start playback
2. Read `0x0202` (timestamp), `0x0207` (duration), `0x0206` (avg current), `0x0208` (RPM)
3. Write `0x02` to `0x0209` to advance to the next session
4. Repeat until `0x0209` reads `0x00` (no more sessions)
5. Write `0x00` to `0x0209` to reset

Each session provides: Unix timestamp, duration in seconds, average motor current (mA), and average motor RPM (raw, ÷ 3.036).

## Known Quirks

| Issue | Behavior | Workaround |
|-------|----------|------------|
| Exclusive connection | Shaver allows only one BLE connection at a time | Unpair from phone/GroomTribe app before connecting HA |
| OS-level pairing required | GATT characteristics are inaccessible without prior pairing | Pair via `bluetoothctl` before adding the integration |
| No standard ESPHome proxy | Standard BLE proxy cannot handle LE Secure Connections pairing | Use the dedicated [ESP32 BLE Bridge](ESP_BRIDGE_SETUP.md) or a local Bluetooth adapter |
| Motor RPM raw values | RPM characteristic reports raw sensor values | Divide by 3.036 for actual RPM |
| Device state mapping | State byte uses 1/2/3 instead of 0/1/2 | Map 1=off, 2=shaving, 3=charging |

## Source References

The protocol was reverse-engineered from the shaver's BLE interface.
