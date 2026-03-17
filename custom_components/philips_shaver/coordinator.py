# custom_components/philips_shaver/coordinator.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_register_callback,
)

from .transport import BleakTransport, EspBridgeTransport, ShaverTransport
from .exceptions import TransportError
from .const import (
    DOMAIN,
    MIN_BRIDGE_VERSION,
    CHAR_AMOUNT_OF_CHARGES,
    CHAR_AMOUNT_OF_OPERATIONAL_TURNS,
    CHAR_APP_HANDLE_SETTINGS,
    APP_SETTINGS_FULL_COACHING,
    APP_SETTINGS_MAX_PRESSURE,
    CHAR_BATTERY_LEVEL,
    CHAR_CLEANING_CYCLES,
    CHAR_CLEANING_PROGRESS,
    CHAR_DAYS_SINCE_LAST_USED,
    CHAR_DEVICE_STATE,
    CHAR_FIRMWARE_REVISION,
    CHAR_SOFTWARE_REVISION,
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
    CHAR_SPEED,
    CHAR_SPEED_ZONE_THRESHOLD,
    CHAR_SYSTEM_NOTIFICATIONS,
    CONF_ADDRESS,
    CONF_CAPABILITIES,
    CONF_SERVICES,
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
    CHAR_SERVICE_MAP,
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
    CHAR_APP_HANDLE_SETTINGS,
    CHAR_SPEED,
    CHAR_SYSTEM_NOTIFICATIONS,
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

        # Filter characteristics by available services (avoids "not found" for
        # devices that lack certain services, e.g. OneBlade without SVC_CONTROL)
        self.available_services = {
            s.lower() for s in entry.data.get(CONF_SERVICES, [])
        }
        if self.available_services:
            def _svc_available(char: str) -> bool:
                return CHAR_SERVICE_MAP.get(char, "").lower() in self.available_services

            self._poll_chars = [c for c in POLL_READ_CHARS if _svc_available(c)]
            self._live_chars = [c for c in LIVE_READ_CHARS if _svc_available(c)]
            self._notify_chars = [c for c in NOTIFICATION_CHARS if _svc_available(c)]
        else:
            # No service info stored (legacy entries) — read everything
            self._poll_chars = list(POLL_READ_CHARS)
            self._live_chars = list(LIVE_READ_CHARS)
            self._notify_chars = list(NOTIFICATION_CHARS)

        self._connection_lock = asyncio.Lock()
        self._live_task: asyncio.Task | None = None
        self._live_setup_done = False
        self._wake_event = asyncio.Event()
        self._unsub_advertisement = None

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
            "lightring_enabled": None,
            "app_handle_settings_raw": None,
            "speed": None,
            "speed_threshold_high": None,
            "speed_verdict": None,
            "system_notifications": 0,
            "last_seen": None,
        }

    async def async_start(self) -> None:
        """Start live monitoring. Call after setup is complete."""
        if self.enable_live_updates:
            self._live_task = self.entry.async_create_background_task(
                self.hass, self._start_live_monitoring(), "philips_shaver_monitoring"
            )
        else:
            _LOGGER.info("Live updates disabled – polling only")

    def _start_advertisement_callback(self) -> None:
        """Register BLE advertisement callback to wake monitoring loop and log."""

        @callback
        def _advertisement_callback(service_info, change):
            self._wake_event.set()

            if not _LOGGER.isEnabledFor(logging.DEBUG):
                return

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

        self._unsub_advertisement = async_register_callback(
            self.hass,
            _advertisement_callback,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.PASSIVE,
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
            data["last_seen"] = datetime.now(timezone.utc)
            return data

        # 2. Live updates enabled + device seen → let live thread handle reconnect
        if self.enable_live_updates and self._wake_event.is_set():
            _LOGGER.debug("ADV received, live thread will handle reconnect – polling skipped")
            return self.data or {}

        if self.data is None:
            self.data = {}

        # 3. Recent data within poll interval → skip
        last_seen = self.data.get("last_seen")
        if last_seen:
            age = (datetime.now(timezone.utc) - last_seen).total_seconds()

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
        elif raw := results.get(CHAR_SOFTWARE_REVISION):
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

        # Speed (0x0703) — OneBlade movement speed (uint16 LE)
        if raw := results.get(CHAR_SPEED):
            new_data["speed"] = int.from_bytes(raw, "little")

        # Speed Zone Thresholds (0x0705) — 7 bytes: 3× uint16 LE + 1× uint8
        if raw := results.get(CHAR_SPEED_ZONE_THRESHOLD):
            if len(raw) >= 6:
                new_data["speed_threshold_high"] = int.from_bytes(raw[4:6], "little")

        # Speed Verdict — computed locally (app ignores device 0x0706)
        speed = new_data.get("speed")
        threshold_high = new_data.get("speed_threshold_high")
        if speed is not None and threshold_high is not None:
            if speed >= threshold_high:
                new_data["speed_verdict"] = "too_fast"
            elif speed > 0:
                new_data["speed_verdict"] = "optimal"
            else:
                new_data["speed_verdict"] = "none"

        # System Notifications (0x0110) — uint32 LE bitfield
        if raw := results.get(CHAR_SYSTEM_NOTIFICATIONS):
            new_data["system_notifications"] = int.from_bytes(raw, "little")

        # App Handle Settings (0x0319) — coaching/feedback bitfield
        if raw := results.get(CHAR_APP_HANDLE_SETTINGS):
            val = int.from_bytes(raw, "little")
            new_data["lightring_enabled"] = bool(val & APP_SETTINGS_FULL_COACHING)
            new_data["app_handle_settings_raw"] = raw

        # Change detection: only update last_seen when data actually changed
        # or every 30s as heartbeat for availability tracking
        old = self.data or {}
        changed = any(
            new_data.get(k) != old.get(k)
            for k in new_data
            if k != "last_seen"
        )

        now = datetime.now(timezone.utc)
        last = old.get("last_seen")
        if changed or last is None or (now - last).total_seconds() >= 30:
            new_data["last_seen"] = now
        else:
            new_data["last_seen"] = last

        # Device registry: only update when model or firmware actually changed
        model = new_data.get("model_number")
        firmware = new_data.get("firmware")
        if changed and (model or firmware):
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(
                identifiers={(DOMAIN, self.address)}
            )
            if device and (device.model != model or device.sw_version != firmware):
                dev_reg.async_update_device(
                    device.id,
                    model=model or "Philips Shaver",
                    sw_version=firmware,
                )

        return new_data

    async def _start_live_monitoring(self) -> None:
        """Persistent live connection with notifications – exclusive and intelligent."""
        backoff = 5
        max_backoff = 300

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
                        self._wake_event.set()

                    self.transport.set_disconnect_callback(_on_state_change)

                    _LOGGER.info("Establishing live connection to %s...", self.address)
                    await self.transport.connect()

                    # Send configured throttle to ESP bridge
                    throttle_ms = self.entry.options.get(
                        CONF_NOTIFY_THROTTLE, DEFAULT_NOTIFY_THROTTLE
                    )
                    await self.transport.set_notify_throttle(throttle_ms)

                    # Subscribe FIRST to keep connection alive
                    await self._start_all_notifications()
                    self._live_setup_done = True
                    if isinstance(self.transport, EspBridgeTransport):
                        self.transport.acknowledge_resubscribe()
                        self._check_bridge_version()
                    _LOGGER.info("Live monitoring active – polling paused")

                    # Reset backoff after successful subscribe
                    backoff = 5

                    # Then read all characteristics
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

                    if any(v is not None for v in results.values()):
                        new_data = self._process_results(results)
                        self.async_set_updated_data(new_data)

                except TransportError as err:
                    _LOGGER.debug(
                        "Transport error: %s – retrying in %ds", err, backoff
                    )
                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=backoff)
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
                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=backoff)
                        backoff = 5
                    except asyncio.TimeoutError:
                        backoff = min(backoff * 2, max_backoff)
                    continue

            # Outside the lock: wait until disconnect (or ESP reboot)
            try:
                while self.transport.is_connected:
                    if (
                        isinstance(self.transport, EspBridgeTransport)
                        and self.transport.needs_resubscribe
                    ):
                        self.transport.acknowledge_resubscribe()
                        _LOGGER.info("ESP bridge rebooted — forcing re-setup")
                        break
                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass

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
        for char_uuid in self._notify_chars:
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

        Flow:
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

    def _check_bridge_version(self) -> None:
        """Create or clear a HA repair issue if the ESP bridge firmware is outdated."""
        assert isinstance(self.transport, EspBridgeTransport)
        version = self.transport.bridge_version
        if not version:
            return
        from packaging.version import Version
        try:
            outdated = Version(version) < Version(MIN_BRIDGE_VERSION)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Cannot parse bridge version '%s'", version)
            return
        if outdated:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                "esp_bridge_outdated",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="esp_bridge_outdated",
                translation_placeholders={
                    "version": version,
                    "min_version": MIN_BRIDGE_VERSION,
                },
            )
            _LOGGER.warning(
                "ESP bridge v%s is outdated (minimum: v%s) — "
                "rebuild and flash your ESPHome device",
                version,
                MIN_BRIDGE_VERSION,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, "esp_bridge_outdated")

        # Update sw_version on the bridge sub-device
        device_id = self.entry.data.get(CONF_ESP_DEVICE_NAME, "")
        dev_reg = dr.async_get(self.hass)
        bridge_device = dev_reg.async_get_device(
            identifiers={(DOMAIN, f"{device_id}_bridge")}
        )
        if bridge_device:
            dev_reg.async_update_device(bridge_device.id, sw_version=version)

    async def async_shutdown(self) -> None:
        """Called on unload – clean up everything."""
        await self.transport.unsubscribe_all()

        if self._unsub_advertisement:
            self._unsub_advertisement()
            self._unsub_advertisement = None

        if self._live_task:
            self._live_task.cancel()
            try:
                await self._live_task
            except asyncio.CancelledError:
                pass

        await self.transport.disconnect()
