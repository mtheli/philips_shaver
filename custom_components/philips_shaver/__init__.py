# custom_components/philips_shaver/__init__.py
from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CHAR_BATTERY_LEVEL,
    CHAR_FIRMWARE_REVISION,
    CHAR_HEAD_REMAINING,
    CHAR_DAYS_SINCE_LAST_USED,
    CHAR_MODEL_NUMBER,
    CHAR_SERIAL_NUMBER,
    CHAR_SHAVING_TIME,
    CHAR_DEVICE_STATE,
    CHAR_TRAVEL_LOCK,
    CHAR_CLEANING_PROGRESS,
    CHAR_MOTOR_RPM,
    CHAR_MOTOR_CURRENT,
    POLL_INTERVAL,
    POLL_READ_CHARS,
    LIVE_READ_CHARS,
)
from . import bluetooth as shaver_bluetooth

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


def _process_values(hass: HomeAssistant, entry: ConfigEntry, results: dict):
    """Zentrale Verarbeitung aller GATT-Werte – genutzt von Poll & Live."""
    data_store = hass.data[DOMAIN][entry.entry_id]["data"]
    address = entry.data["address"]

    battery = (
        results.get(CHAR_BATTERY_LEVEL)[0] if results.get(CHAR_BATTERY_LEVEL) else None
    )
    firmware = (
        results.get(CHAR_FIRMWARE_REVISION).decode("utf-8", "ignore").strip()
        if results.get(CHAR_FIRMWARE_REVISION)
        else None
    )
    head_remaining = (
        results.get(CHAR_HEAD_REMAINING)[0]
        if results.get(CHAR_HEAD_REMAINING)
        else None
    )
    days_since_last_used = (
        int.from_bytes(results.get(CHAR_DAYS_SINCE_LAST_USED), "little")
        if results.get(CHAR_DAYS_SINCE_LAST_USED)
        else None
    )
    model_number = (
        results.get(CHAR_MODEL_NUMBER).decode("utf-8", "ignore").strip()
        if results.get(CHAR_MODEL_NUMBER)
        else None
    )
    serial_number = (
        results.get(CHAR_SERIAL_NUMBER).decode("utf-8", "ignore").strip()
        if results.get(CHAR_SERIAL_NUMBER)
        else None
    )
    shaving_time = (
        int.from_bytes(results.get(CHAR_SHAVING_TIME), "little")
        if results.get(CHAR_SHAVING_TIME)
        else None
    )

    state = "unknown"
    if results.get(CHAR_DEVICE_STATE) and len(results[CHAR_DEVICE_STATE]) >= 1:
        state_byte = results[CHAR_DEVICE_STATE][0]
        state = {1: "off", 2: "shaving", 3: "charging"}.get(state_byte, "unknown")

    is_locked = (
        results.get(CHAR_TRAVEL_LOCK)
        and len(results[CHAR_TRAVEL_LOCK]) >= 1
        and results[CHAR_TRAVEL_LOCK][0] == 1
    )

    cleaning_progress = (
        results.get(CHAR_CLEANING_PROGRESS)[0]
        if results.get(CHAR_CLEANING_PROGRESS)
        and len(results[CHAR_CLEANING_PROGRESS]) >= 1
        else None
    )

    motor_current_raw = results.get(CHAR_MOTOR_CURRENT)
    motor_current_ma = (
        int.from_bytes(motor_current_raw, "little")
        if motor_current_raw and len(motor_current_raw) >= 2
        else None
    )

    motor_rpm_raw = results.get(CHAR_MOTOR_RPM)
    motor_rpm = (
        int.from_bytes(motor_rpm_raw, "little")
        if motor_rpm_raw and len(motor_rpm_raw) >= 2
        else None
    )

    data_store.update(
        {
            "battery": battery,
            "firmware": firmware,
            "head_remaining": head_remaining,
            "days_since_last_used": days_since_last_used,
            "model_number": model_number,
            "serial_number": serial_number,
            "shaving_time": shaving_time,
            "device_state": state,
            "in_use": state == "shaving",
            "travel_lock": is_locked,
            "cleaning_progress": cleaning_progress,
            "motor_rpm": motor_rpm,
            "motor_current_ma": motor_current_ma,
        }
    )

    if firmware:
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, address)})
        if device and device.sw_version != firmware:
            device_registry.async_update_device(device.id, sw_version=firmware)

    # hass.data[DOMAIN][entry.entry_id]["last_seen"] = datetime.now()
    async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Philips Shaver from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    address = entry.data["address"]

    hass.data[DOMAIN][entry.entry_id] = {
        "address": address,
        "data": {
            "device_state": "unknown",
            "in_use": False,
            "travel_lock": False,
            "battery": None,
            "firmware": None,
            "head_remaining": None,
            "days_since_last_used": None,
            "model_number": None,
            "serial_number": None,
            "shaving_time": None,
            "cleaning_progress": None,
            "motor_rpm": None,
            "motor_current_ma": None,
        },
        "live_client": None,
        "live_task": None,
        "unsub_poll": None,
        "last_seen": None,
        "connection_lock": asyncio.Lock(),
    }

    device_registry = dr.async_get(hass)
    data = hass.data[DOMAIN][entry.entry_id]["data"]
    firmware = data.get("firmware")
    model_number = data.get("model_number") or "i9000 / XP9201"

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, address)},
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        manufacturer="Philips",
        name="Philips Shaver",
        model=model_number,
        sw_version=firmware,
    )

    # === 1. Poll (Fallback) ===
    async def _poll_update(now=None):
        store = hass.data[DOMAIN][entry.entry_id]
        if store.get("live_client") and store["live_client"].is_connected:
            _LOGGER.debug("Live client connected – skipping poll")
            return

        last_seen = store.get("last_seen")
        if last_seen and (datetime.now() - last_seen).total_seconds() < 120:
            _LOGGER.debug("Recent live data – skipping poll")
            return

        _LOGGER.debug("Poll update (fallback) for %s", address)

        async with store["connection_lock"]:
            try:
                results = await shaver_bluetooth.connect_and_read(
                    hass,
                    address,
                    POLL_READ_CHARS,
                    connect_timeout=15.0,
                )
                _process_values(hass, entry, results)
            except Exception as e:
                _LOGGER.warning("Poll failed: %s", e)

    unsub_poll = async_track_time_interval(
        hass, _poll_update, timedelta(seconds=POLL_INTERVAL)
    )
    hass.data[DOMAIN][entry.entry_id]["unsub_poll"] = unsub_poll

    # === 2. Live-Verbindung ===
    async def live_monitor_loop():
        backoff = 5
        max_backoff = 300
        store = hass.data[DOMAIN][entry.entry_id]

        while True:
            async with store["connection_lock"]:
                client = None
                try:
                    service_info = async_last_service_info(hass, address)
                    if not service_info:
                        _LOGGER.debug(
                            "Device %s not in range, retrying in %ds...",
                            address,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, max_backoff)
                        continue

                    # Disconnected-Callback
                    def _on_disconnect(client):
                        _LOGGER.info("Live connection disconnected by shaver")
                        store["live_client"] = None

                    _LOGGER.info("Connecting to %s for live monitoring...", address)
                    client = await shaver_bluetooth.establish_connection(
                        shaver_bluetooth.BleakClient,
                        service_info.device,
                        "philips_shaver",
                        disconnected_callback=_on_disconnect,
                        timeout=25.0,
                        cached_services=False,  # ← Das löst dein Problem!
                    )
                    if not client or not client.is_connected:
                        raise Exception("Connection failed")

                    backoff = 5

                    results = {}
                    for uuid in LIVE_READ_CHARS:
                        try:
                            value = await client.read_gatt_char(uuid)
                            if value:
                                _LOGGER.debug("Live read %s: %s", uuid, value.hex())
                                results[uuid] = bytes(value)
                        except Exception as e:
                            _LOGGER.warning("Live read failed for %s: %s", uuid, e)

                    _process_values(hass, entry, results)

                    await client.start_notify(CHAR_DEVICE_STATE, _state_callback)
                    await client.start_notify(CHAR_TRAVEL_LOCK, _lock_callback)
                    await client.start_notify(CHAR_BATTERY_LEVEL, _battery_callback)
                    await client.start_notify(
                        CHAR_CLEANING_PROGRESS, _cleaning_progress_callback
                    )
                    await client.start_notify(CHAR_MOTOR_RPM, _motor_rpm_callback)
                    await client.start_notify(
                        CHAR_MOTOR_CURRENT, _motor_current_callback
                    )
                    _LOGGER.info("Live monitoring active – notifications enabled")

                    store["live_client"] = client

                    # Keep-Alive: alle 8–10 Sekunden Battery lesen → verhindert Timeout
                    keepalive = 0
                    while client.is_connected:
                        await asyncio.sleep(1)
                        keepalive += 1
                        if keepalive % 9 == 0:
                            try:
                                await client.read_gatt_char(CHAR_BATTERY_LEVEL)
                            except:
                                break

                    _LOGGER.warning(
                        "Live connection lost – retrying in %ds...", backoff
                    )

                except asyncio.CancelledError:
                    _LOGGER.info("Live monitoring cancelled")
                    break
                except Exception as e:
                    _LOGGER.error(
                        "Live monitoring error: %s – retrying in %ds...", e, backoff
                    )
                    if client and client.is_connected:
                        try:
                            await client.disconnect()
                        except:
                            pass
                finally:
                    store["live_client"] = None

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    # === Notify Callbacks ===
    @callback
    def _state_callback(sender, data):
        if not data or len(data) < 1:
            return
        state_byte = data[0]
        new_state = {1: "off", 2: "shaving", 3: "charging"}.get(state_byte, "unknown")
        current = hass.data[DOMAIN][entry.entry_id]["data"]["device_state"]
        if new_state != current:
            _LOGGER.info("Live: State → %s", new_state)
            hass.data[DOMAIN][entry.entry_id]["data"].update(
                {"device_state": new_state, "in_use": new_state == "shaving"}
            )
            hass.data[DOMAIN][entry.entry_id]["last_seen"] = datetime.now()
            async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")

    @callback
    def _lock_callback(sender, data):
        if not data or len(data) < 1:
            return
        is_locked = data[0] == 1
        current = hass.data[DOMAIN][entry.entry_id]["data"]["travel_lock"]
        if is_locked != current:
            _LOGGER.info(
                "Live: Travel Lock → %s", "locked" if is_locked else "unlocked"
            )
            hass.data[DOMAIN][entry.entry_id]["data"]["travel_lock"] = is_locked
            hass.data[DOMAIN][entry.entry_id]["last_seen"] = datetime.now()
            async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")

    @callback
    def _battery_callback(sender, data):
        if not data or len(data) < 1:
            return

        # Das erste Byte ist der Prozentwert (0-100)
        new_level = data[0]
        current_level = hass.data[DOMAIN][entry.entry_id]["data"]["battery"]

        # Update nur senden, wenn sich der Wert wirklich geändert hat
        if new_level != current_level:
            _LOGGER.debug("Live: Battery Level → %s%%", new_level)
            hass.data[DOMAIN][entry.entry_id]["data"]["battery"] = new_level
            hass.data[DOMAIN][entry.entry_id]["last_seen"] = datetime.now()
            async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")

    @callback
    def _cleaning_progress_callback(sender, data):
        if not data or len(data) < 1:
            return

        progress = data[0]  # 0–100
        current = hass.data[DOMAIN][entry.entry_id]["data"].get("cleaning_progress")

        if progress != current:
            _LOGGER.info("Live: Cleaning Progress → %s%%", progress)
            hass.data[DOMAIN][entry.entry_id]["data"]["cleaning_progress"] = progress
            hass.data[DOMAIN][entry.entry_id]["last_seen"] = datetime.now()
            async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")

    @callback
    def _motor_rpm_callback(sender, data):
        if not data or len(data) < 2:
            return

        rpm = int.from_bytes(data, "little")
        current = hass.data[DOMAIN][entry.entry_id]["data"].get("motor_rpm")
        if rpm != current:
            _LOGGER.info("Live: Motor RPM → %s", rpm)
            hass.data[DOMAIN][entry.entry_id]["data"]["motor_rpm"] = rpm
            hass.data[DOMAIN][entry.entry_id]["last_seen"] = datetime.now()
            async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")

    @callback
    def _motor_current_callback(sender, data):
        if not data or len(data) < 2:
            return
        ma = int.from_bytes(data, "little")

        current = hass.data[DOMAIN][entry.entry_id]["data"].get("motor_current_ma")
        if ma != current:
            _LOGGER.debug("Live: Motor Current → %s mA", ma)
            hass.data[DOMAIN][entry.entry_id]["data"]["motor_current_ma"] = ma
            hass.data[DOMAIN][entry.entry_id]["last_seen"] = datetime.now()
            async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}")

    # === Live-Task starten ===
    task = hass.loop.create_task(live_monitor_loop())
    hass.data[DOMAIN][entry.entry_id]["live_task"] = task

    # === Erster Poll nach HA-Start (nur wenn Gerät bekannt) ===
    def _schedule_first_poll(_):
        if async_last_service_info(hass, address):
            _LOGGER.debug("HA started – device known → trigger first poll")
            hass.create_task(_poll_update())
        else:
            _LOGGER.debug("HA started – device not seen yet → poll via interval")

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _schedule_first_poll)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Philips Shaver integration loaded – address: %s", address)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id)

    if unsub := data.get("unsub_poll"):
        unsub()

    if task := data.get("live_task"):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    client = data.get("live_client")
    if client and client.is_connected:
        try:
            await client.stop_notify(CHAR_DEVICE_STATE)
            await client.stop_notify(CHAR_TRAVEL_LOCK)
            await client.stop_notify(CHAR_BATTERY_LEVEL)
            await client.stop_notify(CHAR_CLEANING_PROGRESS)
            await client.stop_notify(CHAR_MOTOR_RPM)
            await client.stop_notify(CHAR_MOTOR_CURRENT)
            await client.disconnect()
            _LOGGER.info("Live connection cleanly disconnected")
        except Exception as e:
            _LOGGER.warning("Error during disconnect: %s", e)

    return True
