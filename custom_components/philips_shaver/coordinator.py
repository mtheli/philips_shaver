# custom_components/philips_shaver/coordinator.py
from __future__ import annotations

import asyncio
import struct
from datetime import timedelta, datetime
import logging
from typing import Any

from bleak import BleakClient

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

from . import (
    bluetooth as shaver_bluetooth,
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_last_service_info,
    async_register_callback,
)
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
    CHAR_LIGHTRING_COLOR_HIGH,
    CHAR_LIGHTRING_COLOR_LOW,
    CHAR_LIGHTRING_COLOR_MOTION,
    CHAR_LIGHTRING_COLOR_OK,
    CHAR_MODEL_NUMBER,
    CHAR_MOTOR_CURRENT,
    CHAR_MOTOR_CURRENT_MAX,
    CHAR_MOTOR_RPM,
    CHAR_PRESSURE,
    CHAR_SERIAL_NUMBER,
    CHAR_SHAVING_TIME,
    CHAR_TOTAL_AGE,
    CHAR_TRAVEL_LOCK,
    CHAR_SHAVING_MODE,
    CHAR_SHAVING_MODE_SETTINGS,
    CHAR_CUSTOM_SHAVING_MODE_SETTINGS,
    CONF_CAPABILITIES,
    CONF_POLL_INTERVAL,
    CONF_ENABLE_LIVE_UPDATES,
    DEFAULT_ENABLE_LIVE_UPDATES,
    DEFAULT_POLL_INTERVAL,
    POLL_READ_CHARS,
    LIVE_READ_CHARS,
    SHAVING_MODES,
)
from .utils import (
    parse_color,
    parse_shaving_settings_to_dict,
    parse_capabilities,
    ShaverCapabilities,
)

_LOGGER = logging.getLogger(__name__)


class PhilipsShaverCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for Philips Shaver."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.address = entry.data["address"]

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

        self.live_client: BleakClient | None = None
        self._connection_lock = asyncio.Lock()
        self._live_task: asyncio.Task | None = None

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

        # Initialer leerer Datensatz
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

        # Erster Refresh sofort starten
        self.hass.async_create_task(self.async_refresh())

        # Live nur starten, wenn gewünscht
        if self.enable_live_updates:
            self._live_task = self.hass.loop.create_task(self._start_live_monitoring())
        else:
            _LOGGER.info("Live-Updates deaktiviert – nur Polling")

    async def _async_start_advertisement_logging(self) -> None:
        """Loggt jedes Advertisement des Rasierers (super hilfreich beim Debuggen)."""

        @callback
        def _advertisement_debug_callback(service_info, change):
            adv = service_info.advertisement
            _LOGGER.debug(  # debug statt warning → nicht so laut
                "ADVERTISEMENT %s | Name: %s | RSSI: %s dBm | "
                "Mfr: %s | SvcData: %s | SvcUUIDs: %s",
                service_info.address,
                service_info.name or "unbekannt",
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

        # Nur für dieses eine Gerät loggen
        self._unsub_adv_debug = async_register_callback(
            self.hass,
            _advertisement_debug_callback,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.ACTIVE,
        )

    # ------------------------------------------------------------------
    # Wird vom Coordinator automatisch aufgerufen (Polling)
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data via polling fallback."""

        # 1. Live-Verbindung aktiv → sofort überspringen
        if self.live_client and self.live_client.is_connected:
            _LOGGER.debug("Live connection active – polling skipped")
            return self.data or {}

        # if data is null
        if self.data is None:
            # Fallback initialisieren, falls self.data None ist
            self.data = {}

        # 2. Wir hatten vor weniger als 2 Minuten Live-Daten → auch überspringen!
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
                results = await shaver_bluetooth.connect_and_read(
                    self.hass,
                    self.address,
                    POLL_READ_CHARS,
                )
                return self._process_results(results)
            except Exception as err:
                raise UpdateFailed(f"Error communicating with device: {err}") from err

    # ------------------------------------------------------------------
    # Gemeinsame Verarbeitung für Poll + Live
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

        # === Philips-spezifische Characteristics ===
        if raw := results.get(CHAR_HEAD_REMAINING):
            new_data["head_remaining"] = raw[0]

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

        if raw := results.get(CHAR_AMOUNT_OF_CHARGES):
            new_data["amount_of_charges"] = int.from_bytes(raw, "little")

        if raw := results.get(CHAR_AMOUNT_OF_OPERATIONAL_TURNS):
            new_data["amount_of_operational_turns"] = int.from_bytes(raw, "little")

        # === Farben – mit Konstanten aus const.py ===
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

        # Immer aktualisieren – wichtig für "available"
        new_data["last_seen"] = datetime.now()
        return new_data

    async def _start_live_monitoring(self) -> None:
        """Dauerhafte Live-Verbindung mit Notifications – exklusiv und intelligent."""
        backoff = 5
        max_backoff = 300

        while True:
            # Nur versuchen, wenn gerade niemand verbunden ist
            async with self._connection_lock:
                try:
                    service_info = async_last_service_info(self.hass, self.address)
                    if not service_info:
                        _LOGGER.debug(
                            "Device %s not in range – retrying in %ds",
                            self.address,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, max_backoff)
                        continue

                    # Reset backoff bei Sichtkontakt
                    backoff = 5

                    if self.live_client and self.live_client.is_connected:
                        # Sollte nie passieren – aber sicher
                        await asyncio.sleep(5)
                        continue

                    def _on_disconnect(_client):
                        _LOGGER.info("Live connection lost (remote disconnect)")
                        self.live_client = None
                        self.hass.async_create_task(self._stop_all_notifications())

                    _LOGGER.info("Establishing live connection to %s...", self.address)
                    client = await shaver_bluetooth.establish_connection(
                        BleakClient,
                        service_info.device,
                        "philips_shaver",
                        disconnected_callback=_on_disconnect,
                        timeout=15.0,
                    )

                    self.live_client = client

                    # Initial alle LIVE-Chars lesen
                    results = {}
                    for uuid in LIVE_READ_CHARS:
                        try:
                            value = await client.read_gatt_char(uuid)
                            results[uuid] = bytes(value) if value else None
                        except Exception as e:
                            _LOGGER.debug(
                                "Live initial read failed for %s: %s", uuid, e
                            )

                    new_data = self._process_results(results)
                    self.async_set_updated_data(new_data)

                    # === Notifications starten ===
                    await self._start_all_notifications()
                    _LOGGER.info("Live monitoring active – polling paused")

                except Exception as err:
                    _LOGGER.error(
                        "Live monitoring error: %s – retrying in %ds", err, backoff
                    )
                    if self.live_client and self.live_client.is_connected:
                        try:
                            await self.live_client.disconnect()
                        except:
                            pass
                    self.live_client = None
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
                    continue

            # Außerhalb des Locks: warten bis disconnect
            try:
                while self.live_client and self.live_client.is_connected:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                _LOGGER.error("Live connection was cancelled")
                raise  # the task was cancelled from outside
            except Exception as err:
                _LOGGER.error("Unexpected error in live monitoring: %s", err)
            finally:
                await self._stop_all_notifications()
                self.live_client = None
                _LOGGER.info("Live connection ended – polling will resume")
                await asyncio.sleep(5)  # kurze Pause vor reconnect

    def _make_live_callback(self, key: str):
        """Erzeugt einen Live-Callback, der exakt wie _process_results() arbeitet."""

        @callback
        def _callback(_sender, data):
            if not data:
                return

            # Wir simulieren ein results-Dict mit nur dieser einen Characteristic
            fake_results = {self._key_to_uuid(key): data}

            # _process_results() macht alles: Typkonvertierung, Mapping, etc.
            new_data = self._process_results(fake_results)

            if new_data == self.data:
                return  # nichts geändert

            self.async_set_updated_data(new_data)

        return _callback

    def _key_to_uuid(self, key: str) -> str:
        """Mapps data-key → GATT-UUID (for fake results dict)."""
        mapping = {
            "device_state": CHAR_DEVICE_STATE,
            "travel_lock": CHAR_TRAVEL_LOCK,
            "battery": CHAR_BATTERY_LEVEL,
            "amount_of_charges": CHAR_AMOUNT_OF_CHARGES,
            "amount_of_operational_turns": CHAR_AMOUNT_OF_OPERATIONAL_TURNS,
            "cleaning_progress": CHAR_CLEANING_PROGRESS,
            "cleaning_cycles": CHAR_CLEANING_CYCLES,
            "motor_rpm": CHAR_MOTOR_RPM,
            "motor_current_ma": CHAR_MOTOR_CURRENT,
            "pressure": CHAR_PRESSURE,
            "head_remaining": CHAR_HEAD_REMAINING,
            "shaving_time": CHAR_SHAVING_TIME,
            "shaving_settings": CHAR_SHAVING_MODE_SETTINGS,
            "total_age": CHAR_TOTAL_AGE,
        }
        return mapping.get(key, "")

    async def _start_all_notifications(self) -> None:
        """Starts all GATT-Notifications for Live-Updates."""
        if not self.live_client or not self.live_client.is_connected:
            return

        notifications = [
            (CHAR_DEVICE_STATE, "device_state"),
            (CHAR_TRAVEL_LOCK, "travel_lock"),
            (CHAR_BATTERY_LEVEL, "battery"),
            (CHAR_AMOUNT_OF_CHARGES, "amount_of_charges"),
            (CHAR_AMOUNT_OF_OPERATIONAL_TURNS, "amount_of_operational_turns"),
            (CHAR_CLEANING_PROGRESS, "cleaning_progress"),
            (CHAR_CLEANING_CYCLES, "cleaning_cycles"),
            (CHAR_MOTOR_RPM, "motor_rpm"),
            (CHAR_MOTOR_CURRENT, "motor_current_ma"),
            (CHAR_PRESSURE, "pressure"),
            (CHAR_HEAD_REMAINING, "head_remaining"),
            (CHAR_SHAVING_TIME, "shaving_time"),
            (CHAR_SHAVING_MODE_SETTINGS, "shaving_settings"),
            (CHAR_TOTAL_AGE, "total_age"),
        ]

        for char_uuid, key in notifications:
            try:
                await self.live_client.start_notify(
                    char_uuid, self._make_live_callback(key)
                )
                _LOGGER.debug("Started notifications for %s", key)
            except Exception as e:
                _LOGGER.warning("Failed to start notify %s: %s", key, e)

    async def _stop_all_notifications(self) -> None:
        """Stops all GATT-Notifications."""
        if not self.live_client or not self.live_client.is_connected:
            return

        char_uuids = [
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
            CHAR_SHAVING_TIME,
            CHAR_SHAVING_MODE_SETTINGS,
            CHAR_TOTAL_AGE,
        ]

        for char_uuid in char_uuids:
            try:
                await self.live_client.stop_notify(char_uuid)
                _LOGGER.debug("Stopped notifications for %s", char_uuid)
            except Exception:
                pass  # ignore – wird eh disconnected

    async def async_shutdown(self) -> None:
        """Wird beim Unload aufgerufen – räumt alles sauber auf."""
        await self._stop_all_notifications()

        if hasattr(self, "_unsub_adv_debug") and self._unsub_adv_debug:
            self._unsub_adv_debug()
            self._unsub_adv_debug = None

        if self._live_task:
            self._live_task.cancel()
            try:
                await self._live_task
            except asyncio.CancelledError:
                pass

        if self.live_client and self.live_client.is_connected:
            try:
                await self.live_client.disconnect()
            except:
                pass
