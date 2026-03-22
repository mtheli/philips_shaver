# Advanced Usage

This guide covers service actions for debugging and advanced use cases.

## Service Actions

The integration provides service actions accessible via **Developer Tools > Actions** in Home Assistant.

| Action | Description |
| :--- | :--- |
| [`philips_shaver.read_characteristic`](#read-characteristic-parsed) | Read characteristics and return parsed values |
| [`philips_shaver.read_characteristic_raw`](#read-characteristic-raw) | Read characteristics and return raw hex values |
| [`philips_shaver.fetch_history`](#fetch-shaving-history) | Fetch shaving session history from the device |
| [`philips_shaver.acknowledge_notification`](#acknowledge-notification) | Clear a specific system notification |
| [`philips_shaver.write_characteristic`](#write-characteristic) | Write a hex value to a characteristic |

### Read Characteristic (Parsed)

Reads one or more BLE GATT characteristics and returns both the raw hex value and the parsed representation used internally by the integration.

**Action:** `philips_shaver.read_characteristic`

```yaml
action: philips_shaver.read_characteristic
data:
  characteristic_uuid: "0x0319"
```

**Multiple characteristics:**

```yaml
action: philips_shaver.read_characteristic
data:
  characteristic_uuid:
    - "0x0319"
    - "0x010A"
    - "0x0103"
```

**Example response:**

```yaml
status: ok
results:
  8d560319-3cb9-4387-a7e8-b79d826a7025:
    value: "3f000000"
    bytes: 4
  8d56010a-3cb9-4387-a7e8-b79d826a7025:
    value: "01"
    bytes: 1
  8d560103-3cb9-4387-a7e8-b79d826a7025:
    value: "44"
    bytes: 1
parsed:
  lightring_enabled: true
  device_state: "off"
  battery: 68
```

The `parsed` field contains only the data keys affected by the requested characteristics, using the same key names as the integration's internal data dictionary.

---

### Read Characteristic (Raw)

Same as above, but returns only the raw hex values without parsing.

**Action:** `philips_shaver.read_characteristic_raw`

```yaml
action: philips_shaver.read_characteristic_raw
data:
  characteristic_uuid: "0x010A"
```

**Example response:**

```yaml
status: ok
results:
  8d56010a-3cb9-4387-a7e8-b79d826a7025:
    value: "01"
    bytes: 1
```

---

### Fetch Shaving History

Reads the shaving session history stored on the device.

**Action:** `philips_shaver.fetch_history`

```yaml
action: philips_shaver.fetch_history
data: {}
```

---

### Acknowledge Notification

Clears a specific system notification on the shaver by clearing the corresponding bit in the notification register (`0x0110`) via read-modify-write.

**Action:** `philips_shaver.acknowledge_notification`

```yaml
action: philips_shaver.acknowledge_notification
data:
  notification: notification_clean_reminder
```

**Available notification values:**

| Value | Description |
| :--- | :--- |
| `notification_motor_blocked` | Motor blocked |
| `notification_clean_reminder` | Cleaning required |
| `notification_head_replacement` | Replace shaving head |
| `notification_battery_overheated` | Battery overheated |
| `notification_unplug_required` | Unplug before use |

---

### Write Characteristic

Writes a hex value to a BLE GATT characteristic. Use with caution — writing incorrect values can change device settings.

**Action:** `philips_shaver.write_characteristic`

```yaml
action: philips_shaver.write_characteristic
data:
  characteristic_uuid: "0x0110"
  value: "00000000"
```

**Example:** Clear all system notifications:

```yaml
action: philips_shaver.write_characteristic
data:
  characteristic_uuid: "0x0110"
  value: "00000000"
```

---

## Characteristic UUID Format

All characteristics use the Philips UUID template:

```
8d56XXXX-3cb9-4387-a7e8-b79d826a7025
```

You can use the **short form** (e.g. `0x0319` or `0319`) — the integration automatically expands it to the full UUID.

## Common Characteristics

| Short UUID | Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `0x2A19` | Battery Level | uint8 | Battery percentage (0–100). Standard GATT (service 0x180F) |
| `0x0102` | Motor Current | uint16 LE | Motor current in mA |
| `0x0104` | Motor RPM | uint16 LE | Raw value (÷ 3.036 = actual RPM) |
| `0x010A` | Device State | uint8 | 1=off, 2=shaving, 3=charging |
| `0x010C` | Travel Lock | uint8 | 0=unlocked, 1=locked |
| `0x010F` | Shaving Time | uint16 LE | Last session duration (seconds) |
| `0x0110` | System Notifications | uint32 LE | Bitfield: bit 0=motor blocked, 1=clean reminder, 2=head replacement, 3=battery overheated, 4=unplug required |
| `0x0302` | Capabilities | uint32 LE | Capability bitfield |
| `0x0305` | Motion Type | uint8 | 0=none, 1=small circle, 4=large stroke |
| `0x030C` | Pressure | uint16 LE | Current pressure value |
| `0x0319` | App Handle Settings | uint32 LE | Bitfield (bit 4 = light ring on/off) |
| `0x0322` | Handle Load Type | uint16 LE | Attached head type |
| `0x0702` | Groomer Capabilities | uint8 | OneBlade capability bitfield |
| `0x0703` | Speed | uint16 LE | OneBlade grooming speed (0–225) |
| `0x0705` | Speed Zone Thresholds | 7 bytes | Three uint16 LE zone boundaries + post-feedback % |
| `0x0706` | Speed Verdict | uint8 | 0=optimal, 1=too fast, 2=none |

For a full protocol reference, see [PROTOCOL.md](PROTOCOL.md).

## Response Status Values

| Status | Meaning |
| :--- | :--- |
| `ok` | Connected, reads were executed |
| `not_connected` | Shaver is not connected via BLE |
| `no_device` | No Philips Shaver configured in HA |

Individual characteristics that fail to read return `value: null`. If the ESP bridge reports a specific error (e.g. characteristic not found), the result includes an `error` field:

```yaml
results:
  8d56ffff-3cb9-4387-a7e8-b79d826a7025:
    value: null
    bytes: 0
    error: "Characteristic not found"
```

## Optional: `entry_id`

If you have multiple shavers configured, you can specify which one to use:

```yaml
action: philips_shaver.read_characteristic
data:
  characteristic_uuid: "0x010A"
  entry_id: "your_config_entry_id_here"
```

If omitted, the first available device is used.
