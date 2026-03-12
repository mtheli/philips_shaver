"""BLE transport abstraction for Philips Shaver.

Two implementations:
- BleakTransport: Direct BLE via bleak (existing behavior)
- EspBridgeTransport: Via ESP32 ESPHome bridge (service calls + events)
"""
from __future__ import annotations

import abc
import asyncio
import logging
import time
from datetime import timedelta
from typing import Callable

from bleak import BleakClient
from bleak_retry_connector import establish_connection as bleak_establish

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval

from .const import CHAR_SERVICE_MAP
from .exceptions import TransportError

_LOGGER = logging.getLogger(__name__)
TRACE = 5  # below DEBUG(10), for per-event tracing

# ESPHome event names fired by the ESP32 bridge component
ESP_EVENT_NAME = "esphome.philips_shaver_ble_data"
ESP_STATUS_EVENT_NAME = "esphome.philips_shaver_ble_status"
ESP_READ_TIMEOUT = 5.0
# Heartbeat timeout: if no heartbeat received within this time, ESP is considered offline
ESP_HEARTBEAT_TIMEOUT = 45.0  # 3x heartbeat interval (15s)


class ShaverTransport(abc.ABC):
    """Abstract BLE transport for Philips Shaver."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish persistent connection for live monitoring."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Disconnect and clean up."""

    @property
    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Return True if the transport has an active connection."""

    @property
    def is_bridge_alive(self) -> bool:
        """Return True if the bridge (ESP) is reachable. Same as is_connected for direct BLE."""
        return self.is_connected

    @property
    def is_shaver_connected(self) -> bool:
        """Return True if the shaver BLE link is active. Same as is_connected for direct BLE."""
        return self.is_connected

    @abc.abstractmethod
    async def read_char(self, char_uuid: str) -> bytes | None:
        """Read a single GATT characteristic."""

    @abc.abstractmethod
    async def read_chars(self, char_uuids: list[str]) -> dict[str, bytes | None]:
        """Read multiple GATT characteristics (polling pattern)."""

    @abc.abstractmethod
    async def write_char(self, char_uuid: str, data: bytes) -> None:
        """Write data to a GATT characteristic."""

    @abc.abstractmethod
    async def subscribe(
        self, char_uuid: str, cb: Callable[[str, bytes], None]
    ) -> None:
        """Subscribe to notifications on a characteristic."""

    @abc.abstractmethod
    async def unsubscribe(self, char_uuid: str) -> None:
        """Unsubscribe from notifications on a characteristic."""

    @abc.abstractmethod
    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all active notification subscriptions."""

    async def set_notify_throttle(self, ms: int) -> None:
        """Set the notification throttle on the bridge (no-op for direct BLE)."""

    @abc.abstractmethod
    def set_disconnect_callback(self, cb: Callable[[], None]) -> None:
        """Register a callback invoked when the connection drops."""


# ---------------------------------------------------------------------------
# BleakTransport — wraps existing direct BLE code
# ---------------------------------------------------------------------------

class BleakTransport(ShaverTransport):
    """Direct BLE transport using bleak."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._hass = hass
        self._address = address
        self._client: BleakClient | None = None
        self._disconnect_cb: Callable[[], None] | None = None
        self._last_read_errors: dict[str, str] = {}

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        service_info = async_last_service_info(self._hass, self._address)
        if not service_info:
            raise TransportError(f"Device {self._address} not in range")

        def _on_disconnect(_client):
            _LOGGER.info("BleakTransport: connection lost")
            self._client = None
            if self._disconnect_cb:
                self._disconnect_cb()

        self._client = await bleak_establish(
            BleakClient,
            service_info.device,
            "philips_shaver",
            disconnected_callback=_on_disconnect,
            timeout=15.0,
        )

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._client = None

    def pop_read_error(self, char_uuid: str) -> str | None:
        """Return and clear the last read error for a characteristic, if any."""
        return self._last_read_errors.pop(char_uuid, None)

    async def read_char(self, char_uuid: str) -> bytes | None:
        if not self.is_connected:
            return None
        try:
            value = await self._client.read_gatt_char(char_uuid)
            return bytes(value) if value else None
        except Exception as e:
            _LOGGER.debug("Read failed for %s: %s", char_uuid, e)
            self._last_read_errors[char_uuid] = str(e)
            return None

    async def read_chars(self, char_uuids: list[str]) -> dict[str, bytes | None]:
        """Connect-read-disconnect pattern for polling."""
        results: dict[str, bytes | None] = {u: None for u in char_uuids}
        service_info = async_last_service_info(self._hass, self._address)
        if not service_info:
            _LOGGER.warning("Device %s not in range", self._address)
            return results

        client: BleakClient | None = None
        try:
            client = await bleak_establish(
                BleakClient, service_info.device, "philips_shaver", timeout=15.0
            )
            if not client or not client.is_connected:
                return results

            for uuid in char_uuids:
                try:
                    value = await client.read_gatt_char(uuid)
                    if value:
                        results[uuid] = bytes(value)
                except Exception as e:
                    _LOGGER.debug("Read failed for %s: %s", uuid, e)
        except Exception as err:
            _LOGGER.error("BLE poll error: %s", err)
        finally:
            if client and client.is_connected:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        return results

    async def write_char(self, char_uuid: str, data: bytes) -> None:
        if not self.is_connected:
            raise TransportError("Not connected")
        await self._client.write_gatt_char(char_uuid, data)

    async def subscribe(
        self, char_uuid: str, cb: Callable[[str, bytes], None]
    ) -> None:
        if not self.is_connected:
            raise TransportError("Not connected")

        def _bleak_cb(_sender, data):
            cb(char_uuid, data)

        await self._client.start_notify(char_uuid, _bleak_cb)

    async def unsubscribe(self, char_uuid: str) -> None:
        if not self.is_connected:
            return
        try:
            await self._client.stop_notify(char_uuid)
        except Exception:
            pass

    async def unsubscribe_all(self) -> None:
        pass  # bleak handles cleanup on disconnect

    def set_disconnect_callback(self, cb: Callable[[], None]) -> None:
        self._disconnect_cb = cb


# ---------------------------------------------------------------------------
# EspBridgeTransport — via ESP32 ESPHome bridge
# ---------------------------------------------------------------------------


class EspBridgeTransport(ShaverTransport):
    """BLE transport via ESP32 ESPHome bridge.

    Outbound: HA service calls (ble_read_char, ble_write_char, etc.)
    Inbound: HA events (esphome.philips_shaver_ble_data) with uuid + payload.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        esphome_device_name: str,
        esp_device_id: str = "",
    ) -> None:
        self._hass = hass
        self._address = address
        self._device_name = esphome_device_name  # e.g. "atom_lite"
        self._esp_device_id = esp_device_id  # e.g. "shaver" — suffix for multi-device ESP
        self._setup_done = False  # event listeners registered
        self._shaver_connected = False  # ESP↔Shaver BLE link active
        self._esp_alive = False  # heartbeat received from ESP
        self._last_heartbeat: float = 0.0
        self._disconnect_cb: Callable[[], None] | None = None
        self._event_unsub: Callable | None = None
        self._status_unsub: Callable | None = None
        self._heartbeat_check_unsub: Callable | None = None
        self._pending_reads: dict[str, asyncio.Future[bytes | None]] = {}
        self._last_read_errors: dict[str, str] = {}
        self._notify_callbacks: dict[str, Callable[[str, bytes], None]] = {}
        self._detected_mac: str | None = None
        self._bridge_version: str | None = None
        self._pending_info: asyncio.Future[dict[str, str]] | None = None
        self._needs_resubscribe = False

    def _svc_name(self, action: str) -> str:
        """Full ESPHome service name, e.g. 'atom_lite_ble_read_char_shaver'."""
        base = f"{self._device_name}_{action}"
        if self._esp_device_id:
            return f"{base}_{self._esp_device_id}"
        return base

    @staticmethod
    def _get_service_uuid(char_uuid: str) -> str:
        """Look up the parent service UUID for a characteristic UUID."""
        svc = CHAR_SERVICE_MAP.get(char_uuid)
        if not svc:
            raise TransportError(
                f"No service UUID mapping for characteristic {char_uuid}"
            )
        return svc

    def _cancel_pending_reads(self) -> None:
        """Cancel all pending read futures (e.g. after ESP API disconnect)."""
        if not self._pending_reads:
            return
        count = len(self._pending_reads)
        for uuid, future in self._pending_reads.items():
            if not future.done():
                future.set_result(None)
        self._pending_reads.clear()
        _LOGGER.debug("Cancelled %d pending reads", count)

    @property
    def detected_mac(self) -> str | None:
        """Return the shaver's BLE MAC address detected from events."""
        return self._detected_mac

    @property
    def bridge_version(self) -> str | None:
        """Return the ESP bridge component version (from status events)."""
        return self._bridge_version

    @property
    def is_bridge_alive(self) -> bool:
        """Return True if the ESP bridge is reachable (heartbeat within timeout)."""
        if not self._setup_done:
            return False
        if not self._hass.services.has_service("esphome", self._svc_name("ble_read_char")):
            return False
        return self._esp_alive

    @property
    def is_shaver_connected(self) -> bool:
        """Return True if the ESP↔Shaver BLE link is active."""
        return self._shaver_connected

    @property
    def is_connected(self) -> bool:
        return self.is_bridge_alive and self._shaver_connected

    @property
    def needs_resubscribe(self) -> bool:
        """True when the ESP bridge rebooted and subscriptions need re-setup."""
        return self._needs_resubscribe

    def acknowledge_resubscribe(self) -> None:
        """Clear the resubscribe flag after coordinator has re-established subscriptions."""
        self._needs_resubscribe = False

    async def connect(self) -> None:
        """Start listening for ESP32 bridge events."""
        # Check if ESPHome service is available (device connected and registered)
        svc = self._svc_name("ble_read_char")
        if not self._hass.services.has_service("esphome", svc):
            raise TransportError(
                f"ESPHome service esphome.{svc} not available yet"
            )

        if self._event_unsub:
            self._setup_done = True
            return

        @callback
        def _handle_event(event: Event) -> None:
            data = event.data
            _LOGGER.log(TRACE, "BLE data event: uuid=%s, pending=%s",
                        data.get("uuid", "?"), list(self._pending_reads.keys()))

            mac = data.get("mac", "")

            # Filter: only process events from our shaver (once MAC is known)
            if mac and self._detected_mac and mac.upper() != self._detected_mac.upper():
                return

            uuid = data.get("uuid", "")
            payload_hex = data.get("payload", "")
            error = data.get("error", "")

            # Handle error events from ESP (not_found, not_connected, gatt_err_*)
            if error and uuid and uuid in self._pending_reads:
                self._last_read_errors[uuid] = error
                future = self._pending_reads.pop(uuid)
                if not future.done():
                    future.set_result(None)
                _LOGGER.debug("ESP read error for %s: %s", uuid, error)
                return

            if not uuid or not payload_hex:
                return

            if mac and not self._detected_mac:
                self._detected_mac = mac
                _LOGGER.debug("Detected shaver MAC: %s", mac)

            try:
                payload = bytes.fromhex(payload_hex)
            except ValueError:
                _LOGGER.warning("Invalid hex payload: %s", payload_hex)
                return

            # Resolve pending read
            if uuid in self._pending_reads:
                future = self._pending_reads.pop(uuid)
                if not future.done():
                    future.set_result(payload)
                    _LOGGER.log(TRACE, "Resolved pending read for %s", uuid)
                else:
                    _LOGGER.debug("Future already done for %s", uuid)
            else:
                _LOGGER.log(TRACE, "No pending read for %s", uuid)

            # Fire notification callback
            if uuid in self._notify_callbacks:
                self._notify_callbacks[uuid](uuid, payload)

        self._event_unsub = self._hass.bus.async_listen(
            ESP_EVENT_NAME, _handle_event
        )

        # Listen for ESP↔Shaver BLE status events (connected/disconnected/ready/heartbeat)
        @callback
        def _handle_status_event(event: Event) -> None:
            mac = event.data.get("mac", "")

            # Filter: only process status events from our shaver (once MAC is known)
            if mac and self._detected_mac and mac.upper() != self._detected_mac.upper():
                return

            status = event.data.get("status", "")

            # Store bridge component version if present
            version = event.data.get("version")
            if version:
                self._bridge_version = version

            # Every status event (including heartbeat) proves ESP is alive
            self._last_heartbeat = time.monotonic()
            if not self._esp_alive:
                self._esp_alive = True
                _LOGGER.info("ESP bridge alive (status: %s)", status)
                if self._disconnect_cb:
                    self._disconnect_cb()  # trigger entity update

            if status == "heartbeat":
                # Update shaver BLE state from heartbeat payload
                ble_connected = event.data.get("ble_connected") == "true"
                if ble_connected != self._shaver_connected:
                    self._shaver_connected = ble_connected
                    _LOGGER.info(
                        "ESP↔Shaver BLE: %s (via heartbeat)",
                        "connected" if ble_connected else "disconnected",
                    )
                    if not ble_connected:
                        self._cancel_pending_reads()
                    if self._disconnect_cb:
                        self._disconnect_cb()  # trigger entity update
            elif status in ("connected", "ready"):
                if not self._shaver_connected:
                    self._shaver_connected = True
                    _LOGGER.info("ESP↔Shaver BLE: %s", status)
                if status == "ready":
                    self._needs_resubscribe = True
                    _LOGGER.info("ESP ready — subscriptions need (re-)setup")
                if self._disconnect_cb:
                    self._disconnect_cb()  # trigger entity update
            elif status == "disconnected":
                if self._shaver_connected:
                    self._shaver_connected = False
                    _LOGGER.warning("ESP↔Shaver BLE: disconnected")
                    self._cancel_pending_reads()
                    if self._disconnect_cb:
                        self._disconnect_cb()
            elif status == "info":
                if self._pending_info and not self._pending_info.done():
                    self._pending_info.set_result(dict(event.data))

        self._status_unsub = self._hass.bus.async_listen(
            ESP_STATUS_EVENT_NAME, _handle_status_event
        )

        # Periodic heartbeat timeout check
        @callback
        def _check_heartbeat(now=None) -> None:
            if not self._setup_done:
                return
            if self._last_heartbeat == 0:
                return  # no heartbeat received yet
            elapsed = time.monotonic() - self._last_heartbeat
            if elapsed > ESP_HEARTBEAT_TIMEOUT and self._esp_alive:
                self._esp_alive = False
                _LOGGER.warning(
                    "ESP heartbeat timeout (%.0fs) — bridge offline", elapsed
                )
                self._cancel_pending_reads()
                if self._disconnect_cb:
                    self._disconnect_cb()

        self._heartbeat_check_unsub = async_track_time_interval(
            self._hass, _check_heartbeat, timedelta(seconds=15)
        )

        self._setup_done = True
        # Start pessimistic — first heartbeat or status event confirms ESP is alive
        _LOGGER.info("EspBridgeTransport: event listeners registered, waiting for ESP heartbeat")
        if self._disconnect_cb:
            self._disconnect_cb()  # force entity update with initial (pessimistic) state

    async def disconnect(self) -> None:
        if self._event_unsub:
            self._event_unsub()
            self._event_unsub = None
        if self._status_unsub:
            self._status_unsub()
            self._status_unsub = None
        if self._heartbeat_check_unsub:
            self._heartbeat_check_unsub()
            self._heartbeat_check_unsub = None
        self._setup_done = False
        self._shaver_connected = False
        self._esp_alive = False
        self._pending_reads.clear()
        self._notify_callbacks.clear()

    def pop_read_error(self, char_uuid: str) -> str | None:
        """Return and clear the last read error for a characteristic, if any."""
        return self._last_read_errors.pop(char_uuid, None)

    async def read_char(self, char_uuid: str) -> bytes | None:
        if not self._setup_done:
            return None

        service_uuid = self._get_service_uuid(char_uuid)
        self._last_read_errors.pop(char_uuid, None)

        future: asyncio.Future[bytes | None] = self._hass.loop.create_future()
        self._pending_reads[char_uuid] = future

        try:
            await self._hass.services.async_call(
                "esphome",
                self._svc_name("ble_read_char"),
                {"service_uuid": service_uuid, "char_uuid": char_uuid},
                blocking=True,
            )
        except HomeAssistantError as err:
            self._pending_reads.pop(char_uuid, None)
            _LOGGER.debug("ESP read_char failed for %s: %s", char_uuid, err)
            # Mark bridge as not alive so read_chars skips remaining reads
            self._esp_alive = False
            return None

        try:
            return await asyncio.wait_for(future, timeout=ESP_READ_TIMEOUT)
        except asyncio.TimeoutError:
            _LOGGER.warning("ESP read timeout for %s — bridge not responding", char_uuid)
            self._pending_reads.pop(char_uuid, None)
            self._cancel_pending_reads()
            self._esp_alive = False
            self._shaver_connected = False
            if self._disconnect_cb:
                self._disconnect_cb()
            return None

    async def read_chars(self, char_uuids: list[str]) -> dict[str, bytes | None]:
        """Read multiple characteristics sequentially (ESP32 handles one at a time)."""
        if not self._setup_done:
            await self.connect()
        results: dict[str, bytes | None] = {}
        for uuid in char_uuids:
            if not self.is_connected:
                results[uuid] = None
                continue
            results[uuid] = await self.read_char(uuid)
        return results

    async def write_char(self, char_uuid: str, data: bytes) -> None:
        if not self._setup_done:
            raise TransportError("Not connected")

        service_uuid = self._get_service_uuid(char_uuid)

        try:
            await self._hass.services.async_call(
                "esphome",
                self._svc_name("ble_write_char"),
                {
                    "service_uuid": service_uuid,
                    "char_uuid": char_uuid,
                    "data": data.hex(),
                },
                blocking=True,
            )
        except HomeAssistantError as err:
            raise TransportError(f"ESP write_char failed: {err}") from err

    async def subscribe(
        self, char_uuid: str, cb: Callable[[str, bytes], None]
    ) -> None:
        if not self._setup_done:
            raise TransportError("Not connected")

        service_uuid = self._get_service_uuid(char_uuid)
        self._notify_callbacks[char_uuid] = cb

        try:
            await self._hass.services.async_call(
                "esphome",
                self._svc_name("ble_subscribe"),
                {"service_uuid": service_uuid, "char_uuid": char_uuid},
                blocking=True,
            )
        except HomeAssistantError as err:
            self._notify_callbacks.pop(char_uuid, None)
            raise TransportError(f"ESP subscribe failed: {err}") from err

    async def unsubscribe(self, char_uuid: str) -> None:
        self._notify_callbacks.pop(char_uuid, None)
        if not self._setup_done:
            return

        service_uuid = self._get_service_uuid(char_uuid)
        try:
            await self._hass.services.async_call(
                "esphome",
                self._svc_name("ble_unsubscribe"),
                {"service_uuid": service_uuid, "char_uuid": char_uuid},
                blocking=True,
            )
        except Exception:
            pass

    async def unsubscribe_all(self) -> None:
        for char_uuid in list(self._notify_callbacks.keys()):
            await self.unsubscribe(char_uuid)

    async def set_notify_throttle(self, ms: int) -> None:
        """Send throttle setting to ESP32 bridge."""
        if not self.is_connected:
            return
        try:
            await self._hass.services.async_call(
                "esphome",
                self._svc_name("ble_set_throttle"),
                {"throttle_ms": str(ms)},
                blocking=True,
            )
            _LOGGER.info("Notification throttle set to %d ms on ESP bridge", ms)
        except HomeAssistantError as err:
            _LOGGER.debug("Failed to set throttle on ESP bridge: %s", err)

    async def get_bridge_info(self) -> dict[str, str] | None:
        """Request diagnostic info from ESP bridge via ble_get_info service."""
        if not self._setup_done:
            return None

        self._pending_info = self._hass.loop.create_future()

        try:
            await self._hass.services.async_call(
                "esphome",
                self._svc_name("ble_get_info"),
                {},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("ESP get_bridge_info failed: %s", err)
            self._pending_info = None
            return None

        try:
            return await asyncio.wait_for(self._pending_info, timeout=5.0)
        except asyncio.TimeoutError:
            _LOGGER.warning("ESP get_bridge_info timeout")
            self._pending_info = None
            return None

    def set_disconnect_callback(self, cb: Callable[[], None]) -> None:
        self._disconnect_cb = cb
