# custom_components/philips_shaver/coordinator.py
from __future__ import annotations

import asyncio
from datetime import timedelta, datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_register_callback,
)

from .transport import ShaverTransport
from .exceptions import TransportError
from .const import (
    CHAR_AMOUNT_OF_CHARGES,
    CHAR_AMOUNT_OF_OPERATIONAL_TURNS,
    CHAR_BATTERY_LEVEL,
    CHAR_CLEANING_CYCLES,
    CHAR_CLEANING_PROGRESS,
    CHAR_DAYS_SINCE_LAST_USED,
    CHAR_DEVICE_STATE,
    CHAR_FIRMWARE_REVISION,
    CHAR_HEAD_REMAINING,
    CHAR_HEAD_REMAINING_MINUTES,
    CHAR_HISTORY_AVG_CURRENT,
    CHAR_HISTORY_DURATION,
    CHAR_HISTORY_RPM,
    CHAR_HISTORY_SYNC_STATUS,
    CHAR_HISTORY_TIMESTAMP,
    CHAR_LIGHTRING_COLOR_BRIGHTNESS,
    CHAR_LIGHTRING_COLOR_HIGH,
    CHAR_LIGHTRING_COLOR_LOW,
    CHAR_LIGHTRING_COLOR_MOTION,
    CHAR_LIGHTRING_COLOR_OK,
    LIGHTRING_BRIGHTNESS_MODES,
    CHAR_MODEL_NUMBER,
    CHAR_MOTOR_CURRENT,
    CHAR_MOTOR_CURRENT_MAX,
    CHAR_MOTOR_RPM,
    CHAR_MOTOR_RPM_MAX,
    CHAR_MOTOR_RPM_MIN,
    CHAR_HANDLE_LOAD_TYPE,
    HANDLE_LOAD_TYPES,
    CHAR_MOTION_TYPE,
    CHAR_PRESSURE,
    CHAR_SERIAL_NUMBER,
    CHAR_SHAVING_TIME,
    CHAR_TOTAL_AGE,
    CHAR_TRAVEL_LOCK,
    CHAR_SHAVING_MODE,
    CHAR_SHAVING_MODE_SETTINGS,
    CHAR_CUSTOM_SHAVING_MODE_SETTINGS,
    CONF_ADDRESS,
    CONF_CAPABILITIES,
    CONF_ESP_DEVICE_NAME,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_ESP_BRIDGE,
    CONF_POLL_INTERVAL,
    CONF_ENABLE_LIVE_UPDATES,
    CONF_NOTIFY_THROTTLE,
    DEFAULT_ENABLE_LIVE_UPDATES,
    DEFAULT_NOTIFY_THROTTLE,
    DEFAULT_POLL_INTERVAL,
    POLL_READ_CHARS,
    LIVE_READ_CHARS,
    SHAVING_MODES,
)
from .utils import (
    parse_color,
    parse_shaving_settings_to_dict,
    parse_capabilities,
)

_LOGGER = logging.getLogger(__name__)

# Characteristics to subscribe for live notifications
NOTIFICATION_CHARS = [
    CHAR_DEVICE_STATE,
    CHAR_TRAVEL_LOCK,
    CHAR_BATTERY_LEVEL,
    CHAR_AMOUNT_OF_CHARGES,
    CHAR_AMOUNT_OF_OPERATIONAL_TURNS,
    CHAR_CLEANING_PROGRESS,
    CHAR_CLEANING_CYCLES,
    CHAR_MOTOR_RPM,
    CHAR_MOTOR_CURRENT,
    CHAR_PRESSURE,
    CHAR_HEAD_REMAINING,
    CHAR_HEAD_REMAINING_MINUTES,
    CHAR_SHAVING_TIME,
    CHAR_SHAVING_MODE_SETTINGS,
    CHAR_TOTAL_AGE,
    CHAR_HANDLE_LOAD_TYPE,
    CHAR_MOTION_TYPE,
]


class PhilipsShaverCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for Philips Shaver."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        transport: ShaverTransport,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.address = entry.data.get("address") or entry.data.get(CONF_ESP_DEVICE_NAME, "unknown")
        self.transport = transport

        # reading capabilities
        cap_int = entry.data.get(CONF_CAPABILITIES, 0)
        self.capabilities = parse_capabilities(cap_int)

        # read options
        options = entry.options
        poll_interval = options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        self.poll_interval_seconds = poll_interval
        self.enable_live_updates = options.get(
            CONF_ENABLE_LIVE_UPDATES, DEFAULT_ENABLE_LIVE_UPDATES
        )

        self._poll_chars = list(POLL_READ_CHARS)
        self._live_chars = list(LIVE_READ_CHARS)

        self._connection_lock = asyncio.Lock()
        self._live_task: asyncio.Task | None = None
        self._live_setup_done = False
        self._unsub_adv_debug = None

        _LOGGER.debug(
            "Initializing coordinator for %s with poll interval %s seconds (live updates: %s)",
            self.address,
            self.poll_interval_seconds,
            self.enable_live_updates,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"Philips Shaver {self.address}",
            update_interval=timedelta(seconds=self.poll_interval_seconds),
        )

        # Initial empty dataset
        self.data = {
            "battery": None,
            "firmware": None,
            "model_number": None,
            "serial_number": None,
            "head_remaining": None,
            "days_since_last_used": None,
            "shaving_time": None,
            "device_state": None,
            "travel_lock": None,
            "cleaning_progress": 100,
            "cleaning_cycles": None,
            "motor_rpm": 0,
            "motor_current_ma": 0,
            "motor_current_max_ma": None,
            "motor_rpm_max": None,
            "motor_rpm_min": None,
            "handle_load_type": None,
            "handle_load_type_value": None,
            "motion_type_value": None,
            "amount_of_charges": None,
            "amount_of_operational_turns": None,
            "shaving_mode": None,
            "shaving_mode_value": None,
            "shaving_settings": None,
            "custom_shaving_settings": None,
            "pressure": 0,
            "pressure_state": None,
            "color_low": (255, 0, 0),
            "color_ok": (255, 0, 0),
            "color_high": (255, 0, 0),
            "color_motion": (255, 0, 0),
            "last_seen": None,
        }

    async def async_start(self) -> None:
        """Start initial refresh and live monitoring. Call after setup is complete."""
        self.hass.async_create_task(self.async_refresh())

        if self.enable_live_updates:
            self._live_task = self.hass.loop.create_task(self._start_live_monitoring())
        else:
            _LOGGER.info("Live updates disabled – polling only")

    async def _async_start_advertisement_logging(self) -> None:
        """Log every advertisement from the shaver (useful for debugging)."""

        @callback
        def _advertisement_debug_callback(service_info, change):
            adv = service_info.advertisement
            _LOGGER.debug(
                "ADVERTISEMENT %s | Name: %s | RSSI: %s dBm | "
                "Mfr: %s | SvcData: %s | SvcUUIDs: %s",
                service_info.address,
                service_info.name or "unknown",
                service_info.rssi,
                (
                    {k: v.hex() for k, v in adv.manufacturer_data.items()}
                    if adv.manufacturer_data
                    else "none"
                ),
                (
                    {str(u): d.hex() for u, d in adv.service_data.items()}
                    if adv.service_data
                    else "none"
                ),
                adv.service_uuids or "none",
            )

        self._unsub_adv_debug = async_register_callback(
            self.hass,
            _advertisement_debug_callback,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.ACTIVE,
        )

    # ------------------------------------------------------------------
    # Called automatically by the coordinator (polling)
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data via polling fallback."""

        # 1. Live connection active → skip polling but keep last_seen fresh
        if self.transport.is_connected:
            _LOGGER.debug("Live connection active – polling skipped")
            data = self.data or {}
            data["last_seen"] = datetime.now()
            return data

        if self.data is None:
            self.data = {}

        # 2. Recent data within poll interval → skip
        last_seen = self.data.get("last_seen")
        if last_seen:
            age = (datetime.now() - last_seen).total_seconds()

            if age < self.poll_interval_seconds:
                _LOGGER.debug(
                    "Recent data (%ss < poll interval %ss) – polling skipped",
                    age,
                    self.poll_interval_seconds,
                )
                return self.data or {}

        async with self._connection_lock:
            try:
                results = await self.transport.read_chars(self._poll_chars)
                return self._process_results(results)
            except Exception as err:
                raise UpdateFailed(f"Error communicating with device: {err}") from err

    # ------------------------------------------------------------------
    # Shared processing for poll + live
    # ------------------------------------------------------------------
    def _process_results(self, results: dict[str, bytes | None]) -> dict[str, Any]:
        """Process raw GATT values into coordinator data – using proper constants."""
        if not any(v is not None for v in results.values()):
            return self.data

        new_data = self.data.copy() if self.data else {}

        # === Standard GATT Characteristics ===
        if raw := results.get(CHAR_BATTERY_LEVEL):
            new_data["battery"] = raw[0]

        if raw := results.get(CHAR_FIRMWARE_REVISION):
            new_data["firmware"] = raw.decode("utf-8", "ignore").strip()

        if raw := results.get(CHAR_MODEL_NUMBER):
            new_data["model_number"] = raw.decode("utf-8", "ignore").strip()

        if raw := results.get(CHAR_SERIAL_NUMBER):
            new_data["serial_number"] = raw.decode("utf-8", "ignore").strip()

        # === Philips-specific Characteristics ===
        if raw := results.get(CHAR_HEAD_REMAINING):
            new_data["head_remaining"] = raw[0]

        if raw := results.get(CHAR_HEAD_REMAINING_MINUTES):
            new_data["head_remaining_minutes"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_DAYS_SINCE_LAST_USED):
            new_data["days_since_last_used"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_SHAVING_TIME):
            new_data["shaving_time"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_DEVICE_STATE):
            state_byte = raw[0]
            new_data["device_state"] = {1: "off", 2: "shaving", 3: "charging"}.get(
                state_byte, "unknown"
            )

        if raw := results.get(CHAR_TRAVEL_LOCK):
            new_data["travel_lock"] = raw[0] == 1

        if raw := results.get(CHAR_CLEANING_PROGRESS):
            new_data["cleaning_progress"] = raw[0]

        if raw := results.get(CHAR_CLEANING_CYCLES):
            new_data["cleaning_cycles"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_MOTOR_CURRENT):
            new_data["motor_current_ma"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_MOTOR_CURRENT_MAX):
            new_data["motor_current_max_ma"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_MOTOR_RPM):
            # reading raw value as int
            raw_val = int.from_bytes(raw, "little")

            # calculate normalized RPM: Raw / 3.036
            # rounding to int value
            new_data["motor_rpm"] = int(round(raw_val / 3.036))

        if raw := results.get(CHAR_MOTOR_RPM_MAX):
            new_data["motor_rpm_max"] = int(round(int.from_bytes(raw, "little") / 3.036))

        if raw := results.get(CHAR_MOTOR_RPM_MIN):
            new_data["motor_rpm_min"] = int(round(int.from_bytes(raw, "little") / 3.036))

        if raw := results.get(CHAR_AMOUNT_OF_CHARGES):
            new_data["amount_of_charges"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_AMOUNT_OF_OPERATIONAL_TURNS):
            new_data["amount_of_operational_turns"] = int.from_bytes(raw, "little")

        # === Colors ===
        color_map = {
            CHAR_LIGHTRING_COLOR_LOW: "color_low",
            CHAR_LIGHTRING_COLOR_OK: "color_ok",
            CHAR_LIGHTRING_COLOR_HIGH: "color_high",
            CHAR_LIGHTRING_COLOR_MOTION: "color_motion",
        }

        for char_uuid, key in color_map.items():
            if raw := results.get(char_uuid):
                if color := parse_color(raw):
                    new_data[key] = color

        # Light ring brightness
        if raw := results.get(CHAR_LIGHTRING_COLOR_BRIGHTNESS):
            val = raw[0]
            new_data["lightring_brightness_value"] = val
            new_data["lightring_brightness"] = LIGHTRING_BRIGHTNESS_MODES.get(val, "high")

        # Shaving mode
        if raw := results.get(CHAR_SHAVING_MODE):
            mode_value = int.from_bytes(raw, "little")
            new_data["shaving_mode_value"] = mode_value
            new_data["shaving_mode"] = SHAVING_MODES.get(mode_value, "unknown")

        # Shaving mode settings
        if raw := results.get(CHAR_SHAVING_MODE_SETTINGS):
            new_data["shaving_settings"] = parse_shaving_settings_to_dict(raw)

        # Custom shaving mode settings
        if raw := results.get(CHAR_CUSTOM_SHAVING_MODE_SETTINGS):
            new_data["custom_shaving_settings"] = parse_shaving_settings_to_dict(raw)

        # Pressure
        if raw := results.get(CHAR_PRESSURE):
            pressure_value = int.from_bytes(raw, "little")
            new_data["pressure"] = pressure_value

        # Total Age
        if raw := results.get(CHAR_TOTAL_AGE):
            total_age_value = int.from_bytes(raw, "little")
            new_data["total_age"] = total_age_value

        # Handle Load Type
        if raw := results.get(CHAR_HANDLE_LOAD_TYPE):
            load_value = int.from_bytes(raw, "little")
            new_data["handle_load_type_value"] = load_value
            new_data["handle_load_type"] = HANDLE_LOAD_TYPES.get(load_value, "unknown")

        # Motion Type (uint8 – single byte, as per app FORMAT_UINT8)
        if raw := results.get(CHAR_MOTION_TYPE):
            new_data["motion_type_value"] = raw[0]

        # Always update – important for "available"
        new_data["last_seen"] = datetime.now()

        return new_data

    async def _start_live_monitoring(self) -> None:
        """Persistent live connection with notifications – exclusive and intelligent."""
        backoff = 5
        max_backoff = 300
        esp_ready = asyncio.Event()

        while True:
            async with self._connection_lock:
                try:
                    if self.transport.is_connected and self._live_setup_done:
                        await asyncio.sleep(5)
                        continue

                    def _on_state_change():
                        if self.transport.is_connected:
                            _LOGGER.info("Transport state: connected")
                        else:
                            _LOGGER.info("Transport state: disconnected")
                        self.async_set_updated_data(self.data)
                        esp_ready.set()  # wake up backoff sleep

                    self.transport.set_disconnect_callback(_on_state_change)

                    _LOGGER.info("Establishing live connection to %s...", self.address)
                    await self.transport.connect()

                    # Initial read of all live chars
                    results = {}
                    for uuid in self._live_chars:
                        if not self.transport.is_connected:
                            break
                        try:
                            value = await self.transport.read_char(uuid)
                            results[uuid] = value
                        except Exception as e:
                            _LOGGER.debug(
                                "Live initial read failed for %s: %s", uuid, e
                            )

                    # If ALL reads failed, the bridge is not ready
                    if not any(v is not None for v in results.values()):
                        raise TransportError(
                            "No characteristics could be read – bridge may not be ready"
                        )

                    # Reset backoff only after successful reads
                    backoff = 5

                    # Send configured throttle to ESP bridge (only after confirmed working)
                    throttle_ms = self.entry.options.get(
                        CONF_NOTIFY_THROTTLE, DEFAULT_NOTIFY_THROTTLE
                    )
                    await self.transport.set_notify_throttle(throttle_ms)

                    new_data = self._process_results(results)
                    self.async_set_updated_data(new_data)

                    # === Start notifications ===
                    await self._start_all_notifications()
                    self._live_setup_done = True
                    _LOGGER.info("Live monitoring active – polling paused")

                except TransportError as err:
                    _LOGGER.debug(
                        "Transport error: %s – retrying in %ds", err, backoff
                    )
                    esp_ready.clear()
                    try:
                        await asyncio.wait_for(esp_ready.wait(), timeout=backoff)
                        backoff = 5  # ESP came online — reset backoff
                    except asyncio.TimeoutError:
                        backoff = min(backoff * 2, max_backoff)
                    continue

                except Exception as err:
                    _LOGGER.error(
                        "Live monitoring error: %s – retrying in %ds", err, backoff
                    )
                    try:
                        await self.transport.disconnect()
                    except Exception:
                        pass
                    esp_ready.clear()
                    try:
                        await asyncio.wait_for(esp_ready.wait(), timeout=backoff)
                        backoff = 5
                    except asyncio.TimeoutError:
                        backoff = min(backoff * 2, max_backoff)
                    continue

            # Outside the lock: wait until disconnect
            try:
                while self.transport.is_connected:
                    await asyncio.sleep(5)

            except asyncio.CancelledError:
                _LOGGER.error("Live connection was cancelled")
                raise  # the task was cancelled from outside
            except Exception as err:
                _LOGGER.error("Unexpected error in live monitoring: %s", err)
            finally:
                self._live_setup_done = False
                await self.transport.unsubscribe_all()
                _LOGGER.info("Live connection ended – polling will resume")
                await asyncio.sleep(5)

    def _make_live_callback(self):
        """Create a single notification callback for all subscribed characteristics."""

        @callback
        def _callback(char_uuid: str, data: bytes):
            if not data:
                return

            new_data = self._process_results({char_uuid: data})

            if new_data == self.data:
                return  # nothing changed

            self.async_set_updated_data(new_data)

        return _callback

    async def _start_all_notifications(self) -> None:
        """Start GATT notifications for live updates."""
        if not self.transport.is_connected:
            return

        cb = self._make_live_callback()
        for char_uuid in NOTIFICATION_CHARS:
            try:
                await self.transport.subscribe(char_uuid, cb)
                _LOGGER.debug("Subscribed to %s", char_uuid)
            except Exception as e:
                _LOGGER.warning("Failed to subscribe %s: %s", char_uuid, e)

    async def _stop_all_notifications(self) -> None:
        """Stop all GATT notifications."""
        await self.transport.unsubscribe_all()

    # ------------------------------------------------------------------
    # History retrieval
    # ------------------------------------------------------------------
    async def async_fetch_history(self) -> list[dict[str, Any]]:
        """Fetch shaving session history from the device.

        Flow (as per decompiled GroomTribe app):
        1. Read sync status → number of available sessions
        2. For each session:
           a. Read timestamp (UINT32)
           b. Read duration  (UINT16)
           c. Read avg current (UINT16)
           d. Read RPM (UINT16)
           e. Write 0 to sync status → advance to next record
        """
        sessions: list[dict[str, Any]] = []

        async with self._connection_lock:
            was_connected = self.transport.is_connected

            try:
                if not was_connected:
                    await self.transport.connect()

                # Step 1: Read sync status → number of sessions available
                raw = await self.transport.read_char(CHAR_HISTORY_SYNC_STATUS)
                session_count = raw[0] if raw else 0
                _LOGGER.info("History: %d sessions available", session_count)

                if session_count == 0:
                    return sessions

                # Step 2: Read each session
                for i in range(session_count):
                    session: dict[str, Any] = {"index": i}

                    # Timestamp (UINT32, little-endian)
                    try:
                        raw = await self.transport.read_char(CHAR_HISTORY_TIMESTAMP)
                        if raw:
                            timestamp = int.from_bytes(raw[:4], "little")
                            session["timestamp"] = timestamp
                            session["date"] = datetime.fromtimestamp(timestamp).isoformat()
                    except Exception as e:
                        _LOGGER.debug("History: failed to read timestamp for session %d: %s", i, e)

                    # Duration (UINT16, little-endian) in seconds
                    try:
                        raw = await self.transport.read_char(CHAR_HISTORY_DURATION)
                        if raw:
                            session["duration_seconds"] = int.from_bytes(raw[:2], "little")
                    except Exception as e:
                        _LOGGER.debug("History: failed to read duration for session %d: %s", i, e)

                    # Average current (UINT16, little-endian) in mA
                    try:
                        raw = await self.transport.read_char(CHAR_HISTORY_AVG_CURRENT)
                        if raw:
                            session["avg_current_ma"] = int.from_bytes(raw[:2], "little")
                    except Exception as e:
                        _LOGGER.debug("History: failed to read avg current for session %d: %s", i, e)

                    # RPM (UINT16, little-endian)
                    try:
                        raw = await self.transport.read_char(CHAR_HISTORY_RPM)
                        if raw:
                            raw_rpm = int.from_bytes(raw[:2], "little")
                            session["avg_rpm"] = int(round(raw_rpm / 3.036))
                    except Exception as e:
                        _LOGGER.debug("History: failed to read RPM for session %d: %s", i, e)

                    sessions.append(session)
                    _LOGGER.info("History session %d: %s", i, session)

                    # Advance to next record by writing 0
                    try:
                        await self.transport.write_char(
                            CHAR_HISTORY_SYNC_STATUS, bytes([0])
                        )
                    except Exception as e:
                        _LOGGER.warning("History: failed to advance sync for session %d: %s", i, e)
                        break

            except Exception as err:
                _LOGGER.error("History fetch error: %s", err)
            finally:
                if not was_connected:
                    try:
                        await self.transport.disconnect()
                    except Exception:
                        pass

        # Store in coordinator data for access by sensors/frontend
        self.data["history_sessions"] = sessions
        self.async_set_updated_data(self.data)

        return sessions

    async def async_shutdown(self) -> None:
        """Called on unload – clean up everything."""
        await self.transport.unsubscribe_all()

        if self._unsub_adv_debug:
            self._unsub_adv_debug()
            self._unsub_adv_debug = None

        if self._live_task:
            self._live_task.cancel()
            try:
                await self._live_task
            except asyncio.CancelledError:
                pass

        await self.transport.disconnect()
