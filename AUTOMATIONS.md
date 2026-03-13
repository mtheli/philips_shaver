# Example Automations

Ready-to-use automation examples for the Philips Shaver integration. Replace `philips_shaver` with your device's entity prefix.

---

## Low Battery Alert

Get notified when the shaver battery drops below 20%.

```yaml
automation:
  - alias: "Shaver — Low battery alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.philips_shaver_battery
        below: 20
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Shaver Battery Low"
          message: "Battery is at {{ states('sensor.philips_shaver_battery') }}%"
```

---

## Smart Plug Charging

Automatically turn on a smart plug when battery is low, turn off when fully charged.

```yaml
automation:
  - alias: "Shaver — Start charging"
    trigger:
      - platform: numeric_state
        entity_id: sensor.philips_shaver_battery
        below: 10
    condition:
      - condition: state
        entity_id: binary_sensor.philips_shaver_charging
        state: "off"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.shaver_charger_plug

  - alias: "Shaver — Stop charging"
    trigger:
      - platform: numeric_state
        entity_id: sensor.philips_shaver_battery
        above: 90
    condition:
      - condition: state
        entity_id: binary_sensor.philips_shaver_charging
        state: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.shaver_charger_plug
```

---

## Usage Reminder

Get a daily reminder if the shaver hasn't been used for 3 or more days.

```yaml
automation:
  - alias: "Shaver — Usage reminder"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.philips_shaver_days_last_used
        above: 2
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Shaver Reminder"
          message: >
            You haven't shaved in
            {{ states('sensor.philips_shaver_days_last_used') }} days.
```

---

## Head Replacement Reminder

Get notified when the shaver head is worn out.

```yaml
automation:
  - alias: "Shaver — Head replacement reminder"
    trigger:
      - platform: numeric_state
        entity_id: sensor.philips_shaver_head_remaining
        below: 10
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Replace Shaver Head"
          message: >
            Shaver head is at
            {{ states('sensor.philips_shaver_head_remaining') }}%
            remaining. Time to replace it.
```

---

## Cleaning Cartridge Reminder

Get notified when the cleaning cartridge is running low.

```yaml
automation:
  - alias: "Shaver — Cleaning cartridge low"
    trigger:
      - platform: numeric_state
        entity_id: sensor.philips_shaver_cleaning_cartridge_remaining
        below: 3
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Cleaning Cartridge Low"
          message: >
            Only {{ states('sensor.philips_shaver_cleaning_cartridge_remaining') }}
            cleaning cycles remaining. Consider replacing the cartridge.
```
