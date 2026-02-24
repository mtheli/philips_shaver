# custom_components/philips_shaver/bluetooth.py
from __future__ import annotations

import logging

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def connect_and_read(
    hass: HomeAssistant,
    address: str,
    read_uuids: list[str],
    connect_timeout: float = 15.0,
) -> dict[str, bytes | None]:
    """Verbinde, lese und trenne – nur für Poll (Fallback)."""
    data: dict[str, bytes | None] = {uuid: None for uuid in read_uuids}
    client: BleakClient | None = None

    service_info = async_last_service_info(hass, address)
    if not service_info:
        _LOGGER.warning("Device %s not in range", address)
        return data

    try:
        _LOGGER.info("Connecting to %s...", address)
        client = await establish_connection(
            BleakClient, service_info.device, "philips_shaver", timeout=connect_timeout
        )

        if not client or not client.is_connected:
            _LOGGER.warning("Failed to connect to %s", address)
            return data

        _LOGGER.info("Connected to %s – reading characteristics", address)

        for uuid in read_uuids:
            try:
                value = await client.read_gatt_char(uuid)
                if value:
                    _LOGGER.info("Read %s: %s (hex: %s)", uuid, value[0], value.hex())
                    data[uuid] = bytes(value)
                else:
                    _LOGGER.warning("Empty value for %s", uuid)
            except Exception as e:
                _LOGGER.warning("Read failed for %s: %s", uuid, e)

    except BleakError as err:
        _LOGGER.error("BLE error: %s", err)
    except Exception as err:
        _LOGGER.exception("Unexpected error: %s", err)
    finally:
        if client and client.is_connected:
            try:
                await client.disconnect()
                _LOGGER.debug("Disconnected from %s (poll)", address)
            except Exception:
                pass

    return data
