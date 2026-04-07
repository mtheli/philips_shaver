# custom_components/philips_shaver/__init__.py
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_ADDRESS,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_ESP_BRIDGE,
    CONF_ESP_DEVICE_NAME,
    CONF_ESP_BRIDGE_ID,
    CONF_ESP_DEVICE_ID_LEGACY,
    CHAR_SYSTEM_NOTIFICATIONS,
)
from .coordinator import PhilipsShaverCoordinator
from .transport import BleakTransport, EspBridgeTransport

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.LIGHT, Platform.SELECT, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SWITCH]

SERVICE_FETCH_HISTORY = "fetch_history"
SERVICE_READ_CHARACTERISTIC = "read_characteristic"
SERVICE_READ_CHARACTERISTIC_RAW = "read_characteristic_raw"
SERVICE_WRITE_CHARACTERISTIC = "write_characteristic"
SERVICE_ACKNOWLEDGE_NOTIFICATION = "acknowledge_notification"

NOTIFICATION_BIT_MAP = {
    "notification_motor_blocked": 0x01,
    "notification_clean_reminder": 0x02,
    "notification_head_replacement": 0x04,
    "notification_battery_overheated": 0x08,
    "notification_unplug_required": 0x10,
}

UUID_TEMPLATE_PHILIPS = "8d56%s-3cb9-4387-a7e8-b79d826a7025"
UUID_TEMPLATE_BLE_STANDARD = "0000%s-0000-1000-8000-00805f9b34fb"


def _expand_char_uuid(raw_uuid: str) -> str:
    """Expand short form (0x0319 or 0319) to full UUID.

    Philips-specific chars live in 0x0100–0x07FF range.
    Standard BLE chars (0x2A00+) use the Bluetooth Base UUID.
    """
    short = raw_uuid.strip().lower().replace("0x", "")
    if len(short) == 4 and "-" not in raw_uuid:
        code = int(short, 16)
        if code >= 0x2000:
            return UUID_TEMPLATE_BLE_STANDARD % short
        return UUID_TEMPLATE_PHILIPS % short
    return raw_uuid.strip().lower()


def _get_coordinator(hass: HomeAssistant, entry_id: str | None):
    """Resolve coordinator from entry_id or use first available."""
    if entry_id and entry_id in hass.data[DOMAIN]:
        return hass.data[DOMAIN][entry_id]["coordinator"]
    first = next(iter(hass.data[DOMAIN].values()), None)
    return first["coordinator"] if first else None


def _async_link_via_esp_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Link the shaver device to its ESP32 bridge in the device registry."""
    esp_device_name = entry.data[CONF_ESP_DEVICE_NAME]
    dev_reg = dr.async_get(hass)

    # Find the ESPHome config entry matching our bridge device name
    # ESPHome uses hyphens (atom-lite), we store underscores (atom_lite)
    esp_mac: str | None = None
    normalized = esp_device_name.replace("_", "-")
    for esphome_entry in hass.config_entries.async_entries("esphome"):
        entry_name = esphome_entry.data.get("device_name", "")
        if entry_name == esp_device_name or entry_name == normalized:
            esp_mac = esphome_entry.unique_id
            break

    if not esp_mac:
        _LOGGER.debug("ESPHome config entry for '%s' not found", esp_device_name)
        return

    # ESPHome registers devices by network MAC connection
    esp_device = dev_reg.async_get_device(
        connections={(dr.CONNECTION_NETWORK_MAC, esp_mac)}
    )
    if not esp_device:
        _LOGGER.debug("ESPHome device for '%s' not in registry", esp_device_name)
        return

    # Find our shaver device and set via_device
    # Device identifier is shaver MAC (preferred) or esp_device_name (fallback)
    shaver_mac = entry.data.get(CONF_ADDRESS)
    device_id = shaver_mac if shaver_mac else esp_device_name
    shaver_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, device_id)}
    )
    if shaver_device:
        dev_reg.async_update_device(shaver_device.id, via_device_id=esp_device.id)
        _LOGGER.info("Linked shaver device to ESP bridge '%s'", esp_device_name)

    # Also link the bridge sub-device to the ESPHome device
    bridge_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"{device_id}_bridge")}
    )
    if bridge_device:
        dev_reg.async_update_device(bridge_device.id, via_device_id=esp_device.id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to current version."""
    if entry.version == 1 and entry.minor_version < 3:
        # v1.2 → v1.3: rename esp_device_id → esp_bridge_id
        new_data = {**entry.data}
        if CONF_ESP_DEVICE_ID_LEGACY in new_data:
            new_data[CONF_ESP_BRIDGE_ID] = new_data.pop(CONF_ESP_DEVICE_ID_LEGACY)
            hass.config_entries.async_update_entry(
                entry, data=new_data, minor_version=3,
            )
            _LOGGER.info(
                "Migrated config entry %s: esp_device_id → esp_bridge_id",
                entry.entry_id,
            )
        else:
            hass.config_entries.async_update_entry(entry, minor_version=3)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Philips Shaver from a config entry."""
    # Create transport based on config
    transport_type = entry.data.get(CONF_TRANSPORT_TYPE)
    if transport_type == TRANSPORT_ESP_BRIDGE:
        esp_device_name = entry.data[CONF_ESP_DEVICE_NAME]
        esp_bridge_id = entry.data.get(CONF_ESP_BRIDGE_ID, "")
        address = entry.data.get(CONF_ADDRESS, "")
        transport = EspBridgeTransport(hass, address, esp_device_name, esp_bridge_id)
    else:
        address = entry.data["address"]
        transport = BleakTransport(hass, address)

    coordinator = PhilipsShaverCoordinator(hass, entry, transport)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Non-blocking: shaver sleeps most of the time, don't block HA startup.
    # Sensors will show "Unknown" briefly until the device wakes up.
    coordinator.async_set_updated_data(coordinator.data or {})

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Link shaver device to ESP bridge device via device registry
    if transport_type == TRANSPORT_ESP_BRIDGE:
        _async_link_via_esp_device(hass, entry)

    # Start event-driven live monitoring after platforms are registered
    await coordinator.async_start()

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_FETCH_HISTORY):
        async def handle_fetch_history(call: ServiceCall) -> ServiceResponse:
            """Handle the fetch_history service call."""
            # Find the coordinator for the requested device (or use first one)
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                coord = hass.data[DOMAIN][entry_id]["coordinator"]
            else:
                # Use first available coordinator
                first = next(iter(hass.data[DOMAIN].values()), None)
                if not first:
                    _LOGGER.error("No Philips Shaver devices configured")
                    return {"sessions": []}
                coord = first["coordinator"]

            sessions = await coord.async_fetch_history()
            return {"sessions": sessions}

        hass.services.async_register(
            DOMAIN,
            SERVICE_FETCH_HISTORY,
            handle_fetch_history,
            schema=vol.Schema({
                vol.Optional("entry_id"): str,
            }),
            supports_response=SupportsResponse.ONLY,
        )

    # Register read_characteristic debug services (only once)
    _char_schema = vol.Schema({
        vol.Required("characteristic_uuid"): vol.Any(str, [str]),
        vol.Optional("entry_id"): str,
    })

    async def _read_uuids(coord, raw_input) -> tuple[str, dict[str, dict]]:
        """Read one or more characteristics. Returns (global_status, {uuid: {value, bytes, _raw}})."""
        if isinstance(raw_input, list):
            uuids = [_expand_char_uuid(u) for u in raw_input]
        else:
            uuids = [_expand_char_uuid(u) for u in raw_input.split(",")]

        if not coord.transport.is_connected:
            return "not_connected", {u: {"value": None, "bytes": 0} for u in uuids}

        results = {}
        for char_uuid in uuids:
            try:
                raw = await coord.transport.read_char(char_uuid)
            except Exception as e:
                _LOGGER.error("Failed to read characteristic %s: %s", char_uuid, e)
                results[char_uuid] = {"value": None, "bytes": 0, "error": str(e)}
                continue
            if raw is None:
                entry: dict[str, Any] = {"value": None, "bytes": 0}
                error = getattr(coord.transport, "pop_read_error", lambda u: None)(char_uuid)
                if error:
                    entry["error"] = error
                results[char_uuid] = entry
            else:
                results[char_uuid] = {"value": raw.hex(), "bytes": len(raw), "_raw": raw}
        has_errors = any("error" in r for r in results.values())
        has_data = any(r.get("value") is not None for r in results.values())
        if has_errors:
            status = "partial" if has_data else "error"
        else:
            status = "ok"
        return status, results

    if not hass.services.has_service(DOMAIN, SERVICE_READ_CHARACTERISTIC_RAW):
        async def handle_read_characteristic_raw(call: ServiceCall) -> ServiceResponse:
            """Read GATT characteristics by UUID and return raw hex values."""
            coord = _get_coordinator(hass, call.data.get("entry_id"))
            if not coord:
                return {"status": "no_device", "results": {}}

            status, results = await _read_uuids(coord, call.data["characteristic_uuid"])

            clean = {uuid: {k: v for k, v in r.items() if k != "_raw"} for uuid, r in results.items()}
            return {"status": status, "results": clean}

        hass.services.async_register(
            DOMAIN, SERVICE_READ_CHARACTERISTIC_RAW, handle_read_characteristic_raw,
            schema=_char_schema, supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_READ_CHARACTERISTIC):
        async def handle_read_characteristic(call: ServiceCall) -> ServiceResponse:
            """Read GATT characteristics and return parsed values (same as internal data dict)."""
            coord = _get_coordinator(hass, call.data.get("entry_id"))
            if not coord:
                return {"status": "no_device", "results": {}, "parsed": {}}

            status, results = await _read_uuids(coord, call.data["characteristic_uuid"])

            # Parse requested characteristics in isolation (empty base)
            to_parse = {uuid: r["_raw"] for uuid, r in results.items() if "_raw" in r}
            parsed = {}
            if to_parse:
                saved_data = coord.data
                try:
                    coord.data = {}
                    parsed_data = coord._process_results(to_parse)
                finally:
                    coord.data = saved_data
                for key, val in parsed_data.items():
                    if key == "last_seen" or key.endswith("_raw"):
                        continue
                    parsed[key] = val

            clean = {uuid: {k: v for k, v in r.items() if k != "_raw"} for uuid, r in results.items()}
            return {"status": status, "results": clean, "parsed": parsed}

        hass.services.async_register(
            DOMAIN, SERVICE_READ_CHARACTERISTIC, handle_read_characteristic,
            schema=_char_schema, supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_WRITE_CHARACTERISTIC):
        async def handle_write_characteristic(call: ServiceCall) -> ServiceResponse:
            """Write a hex value to a BLE GATT characteristic."""
            coord = _get_coordinator(hass, call.data.get("entry_id"))
            if not coord:
                return {"status": "no_device"}

            raw_uuid = call.data["characteristic_uuid"]
            char_uuid = _expand_char_uuid(raw_uuid)
            hex_value = call.data["value"].replace(" ", "")

            if not coord.transport.is_connected:
                return {"status": "not_connected", "characteristic": char_uuid}

            try:
                payload = bytes.fromhex(hex_value)
            except ValueError:
                return {"status": "error", "error": f"Invalid hex value: {hex_value}"}

            try:
                await coord.transport.write_char(char_uuid, payload)
            except Exception as e:
                _LOGGER.error("Failed to write characteristic %s: %s", char_uuid, e)
                return {"status": "error", "characteristic": char_uuid, "error": str(e)}

            return {
                "status": "ok",
                "characteristic": char_uuid,
                "written": hex_value,
                "bytes": len(payload),
            }

        hass.services.async_register(
            DOMAIN, SERVICE_WRITE_CHARACTERISTIC, handle_write_characteristic,
            schema=vol.Schema({
                vol.Required("characteristic_uuid"): str,
                vol.Required("value"): str,
                vol.Optional("entry_id"): str,
            }),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_ACKNOWLEDGE_NOTIFICATION):
        async def handle_acknowledge_notification(call: ServiceCall) -> None:
            """Clear a specific notification bit via read-modify-write on 0x0110."""
            coord = _get_coordinator(hass, call.data.get("entry_id"))
            if not coord:
                _LOGGER.warning("acknowledge_notification: no coordinator found")
                return

            notification = call.data["notification"]
            bit_mask = NOTIFICATION_BIT_MAP.get(notification)
            if bit_mask is None:
                _LOGGER.error("Unknown notification key: %s", notification)
                return

            if not coord.transport.is_connected:
                _LOGGER.warning("Shaver not connected – cannot acknowledge notification")
                return

            try:
                raw = await coord.transport.read_char(CHAR_SYSTEM_NOTIFICATIONS)
                if raw is None:
                    _LOGGER.warning("Could not read system notifications")
                    return
                current = int.from_bytes(raw, "little")
                updated = current & ~bit_mask
                await coord.transport.write_char(
                    CHAR_SYSTEM_NOTIFICATIONS, updated.to_bytes(4, "little")
                )
                _LOGGER.info(
                    "Notification %s cleared (0x%08X → 0x%08X)",
                    notification, current, updated,
                )
            except Exception as e:
                _LOGGER.error("Failed to acknowledge notification %s: %s", notification, e)
                return

            # Re-read to confirm and update state
            try:
                raw = await coord.transport.read_char(CHAR_SYSTEM_NOTIFICATIONS)
                if raw is not None:
                    updated = int.from_bytes(raw, "little")
            except Exception:
                pass

            new_data = coord.data.copy()
            new_data["system_notifications"] = updated
            coord.async_set_updated_data(new_data)

        hass.services.async_register(
            DOMAIN, SERVICE_ACKNOWLEDGE_NOTIFICATION, handle_acknowledge_notification,
            schema=vol.Schema({
                vol.Required("notification"): vol.In(list(NOTIFICATION_BIT_MAP.keys())),
                vol.Optional("entry_id"): str,
            }),
        )

    device_id = entry.data.get("address") or entry.data.get(CONF_ESP_DEVICE_NAME)
    _LOGGER.info("Philips Shaver integration loaded – device: %s", device_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("Unloading philips shaver integration started")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    coordinator = hass.data[DOMAIN].pop(entry.entry_id)["coordinator"]
    await coordinator.async_shutdown()

    # Remove services if no more entries
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_FETCH_HISTORY)
        hass.services.async_remove(DOMAIN, SERVICE_READ_CHARACTERISTIC)
        hass.services.async_remove(DOMAIN, SERVICE_READ_CHARACTERISTIC_RAW)
        hass.services.async_remove(DOMAIN, SERVICE_WRITE_CHARACTERISTIC)
        hass.services.async_remove(DOMAIN, SERVICE_ACKNOWLEDGE_NOTIFICATION)

    _LOGGER.info("Unloading philips shaver integration finished")
    return True
