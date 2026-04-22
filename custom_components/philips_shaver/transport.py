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
from datetime import datetime, timedelta, timezone
from typing import Callable

from bleak import BleakClient
from bleak_retry_connector import establish_connection as bleak_establish

from homeassistant.components.bluetooth import (
    async_last_service_info,
    async_scanner_by_source,
    async_scanner_devices_by_address,
)
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


def _scanner_name_by_source(hass: HomeAssistant, source: str) -> str | None:
    """Look up a scanner by source MAC — works for ESPHome proxies."""
    try:
        scanner = async_scanner_by_source(hass, source)
        if scanner is not None:
            return getattr(scanner, "name", None)
    except Exception:  # noqa: BLE001
        return None
    return None


def _host_scanner_name_by_adapter(
    hass: HomeAssistant, address: str, adapter_id: str
) -> str | None:
    """Find the HA Host scanner bound to a BlueZ adapter (e.g. "hci0").

    The HA scanner registry keys Host scanners by their BT-MAC, not by the
    adapter name, so we look the scanner up indirectly via the devices it can
    see and match on the `adapter` attribute.
    """
    try:
        for sd in async_scanner_devices_by_address(hass, address, connectable=True):
            if getattr(sd.scanner, "adapter", None) == adapter_id:
                return getattr(sd.scanner, "name", None)
    except Exception:  # noqa: BLE001
        return None
    return None


def describe_connection_path(
    hass: HomeAssistant, client: BleakClient, device
) -> str:
    """Return the adapter label used for a BleakClient connection.

    Matches the name shown in Settings -> Devices -> Bluetooth. Uses private
    Bleak attributes to identify the backend; any upstream rename falls back
    to a best-effort label instead of breaking the connect flow.
    """
    try:
        # Primary: habluetooth's HaBleakClientWrapper sets _connected_scanner
        # on the client after a successful connect. This is the scanner that
        # actually carried the connection — more reliable than backend
        # introspection, and works for both host (BlueZ) and remote (ESPHome)
        # scanners without branching on backend type.
        connected_scanner = getattr(client, "_connected_scanner", None)
        if connected_scanner is not None:
            name = getattr(connected_scanner, "name", None)
            if name:
                return name
            source = getattr(connected_scanner, "source", None)
            if source:
                return source

        backend = getattr(client, "_backend", None)
        if backend is None:
            return "unknown"
        mod = type(backend).__module__ or ""
        address = getattr(device, "address", None) or "?"

        if "bluezdbus" in mod:
            adapter_id = "?"
            try:
                info = getattr(backend, "_device_info", None)
                if info and "Adapter" in info:
                    adapter_id = info["Adapter"].rsplit("/", 1)[-1]
            except Exception:  # noqa: BLE001
                pass
            if adapter_id == "?":
                try:
                    details = getattr(device, "details", None)
                    path = details.get("path") if isinstance(details, dict) else None
                    if isinstance(path, str) and path.startswith("/org/bluez/"):
                        adapter_id = path.split("/")[3]
                except Exception:  # noqa: BLE001
                    pass
            if adapter_id == "?":
                try:
                    adapter_attr = getattr(backend, "_adapter", None)
                    if isinstance(adapter_attr, str) and adapter_attr:
                        adapter_id = adapter_attr
                except Exception:  # noqa: BLE001
                    pass
            name = _host_scanner_name_by_adapter(hass, address, adapter_id)
            return name or adapter_id

        if "esphome" in mod:
            source = "?"
            try:
                details = getattr(device, "details", None)
                if isinstance(details, dict):
                    source = details.get("source") or "?"
            except Exception:  # noqa: BLE001
                pass
            name = _scanner_name_by_source(hass, source) if source != "?" else None
            return name or source

        return type(backend).__name__
    except Exception as err:  # noqa: BLE001
        return f"unknown ({err})"


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

    @property
    def connection_path(self) -> str | None:
        """Label of the adapter/bridge currently carrying the connection."""
        return None

    @property
    def connection_rssi(self) -> int | None:
        """RSSI seen by the scanner currently carrying the connection.

        Distinct from ``async_last_service_info`` which returns the RSSI from
        whichever scanner has the freshest advertisement — that scanner may
        differ from the one serving the active link when multiple scanners
        see the device with different RSSI.
        """
        return None

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
        self._connection_path: str | None = None
        self._connected_scanner = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def connection_path(self) -> str | None:
        return self._connection_path if self.is_connected else None

    @property
    def connection_rssi(self) -> int | None:
        if not self.is_connected or self._connected_scanner is None:
            return None
        try:
            result = self._connected_scanner.get_discovered_device_advertisement_data(
                self._address
            )
        except Exception:  # noqa: BLE001
            return None
        if not result:
            return None
        _device, adv = result
        rssi = getattr(adv, "rssi", None)
        if rssi is None or rssi <= -127:
            return None
        return int(rssi)

    async def connect(self) -> None:
        service_info = async_last_service_info(self._hass, self._address)
        if not service_info:
            raise TransportError(f"Device {self._address} not in range")

        def _on_disconnect(_client):
            _LOGGER.info("%s: connection lost", self._address)
            self._client = None
            self._connection_path = None
            self._connected_scanner = None
            if self._disconnect_cb:
                self._disconnect_cb()

        self._client = await bleak_establish(
            BleakClient,
            service_info.device,
            "philips_shaver",
            disconnected_callback=_on_disconnect,
            timeout=15.0,
        )
        self._connected_scanner = getattr(self._client, "_connected_scanner", None)
        self._connection_path = describe_connection_path(
            self._hass, self._client, service_info.device
        )
        _LOGGER.info("%s: connected via %s", self._address, self._connection_path)

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
            _LOGGER.debug("BLE poll error (device likely sleeping): %s", err)
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
        esp_bridge_id: str = "",
    ) -> None:
        self._hass = hass
        self._address = address
        self._device_name = esphome_device_name  # e.g. "atom_lite"
        self._esp_bridge_id = esp_bridge_id  # e.g. "shaver" — suffix for multi-device ESP
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
        # Pre-set MAC filter from config to prevent cross-device event mixing
        self._detected_mac: str | None = address if ":" in address else None
        self._bridge_version: str | None = None
        self._pending_info: asyncio.Future[dict[str, str]] | None = None
        self._needs_resubscribe = False
        self._ready_event = asyncio.Event()
        self._last_uptime: int | None = None
        self._boot_time: datetime | None = None

    def _svc_name(self, action: str) -> str:
        """Full ESPHome service name, e.g. 'atom_lite_ble_read_char_shaver'."""
        base = f"{self._device_name}_{action}"
        if self._esp_bridge_id:
            return f"{base}_{self._esp_bridge_id}"
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
    def bridge_boot_time(self) -> datetime | None:
        """Return the ESP bridge boot timestamp.

        Computed from uptime on first sighting and refreshed only on
        detected restart (uptime regression) — stable during runtime.
        """
        return self._boot_time

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
    def connection_path(self) -> str | None:
        return self._device_name if self._esp_alive else None

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
            # Re-wait for bridge if it went offline and came back
            if not self._esp_alive:
                await self._wait_for_bridge()
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
            was_alive = self._esp_alive
            was_connected = self._shaver_connected

            if not self._esp_alive:
                self._esp_alive = True

            # Detect ESP restart via uptime regression.  After reboot the
            # bridge loses all BLE subscriptions, but HA's notify_callbacks
            # still hold stale entries.  Clear them so the "ready" handler
            # below flags a resubscribe.  Fires on info/heartbeat/ready
            # events (all include uptime_s).
            uptime_str = event.data.get("uptime_s")
            if uptime_str is not None:
                try:
                    new_uptime = int(uptime_str)
                    is_restart = (
                        self._last_uptime is not None
                        and new_uptime < self._last_uptime
                    )
                    if is_restart:
                        _LOGGER.info(
                            "ESP bridge restarted (uptime %ds → %ds) — "
                            "clearing stale subscriptions",
                            self._last_uptime, new_uptime,
                        )
                        self._notify_callbacks.clear()
                        self._needs_resubscribe = True
                    # Set boot_time on first sighting and on every restart —
                    # keeps the timestamp stable during normal runtime.
                    if is_restart or self._boot_time is None:
                        self._boot_time = datetime.now(timezone.utc) - timedelta(
                            seconds=new_uptime
                        )
                    self._last_uptime = new_uptime
                except ValueError:
                    pass

            if status == "info":
                # Filter by bridge_id if present (multi-device ESP)
                event_bridge_id = event.data.get("bridge_id", "")
                if event_bridge_id and self._esp_bridge_id and event_bridge_id != self._esp_bridge_id:
                    return
                # Only set _detected_mac from info events (bridge_id filtered)
                if mac and not self._detected_mac:
                    self._detected_mac = mac
                paired = event.data.get("paired")
                if paired is not None:
                    self._ble_paired = paired
                ble_connected = event.data.get("ble_connected")
                if ble_connected is not None:
                    self._shaver_connected = ble_connected == "true"
                if self._pending_info and not self._pending_info.done():
                    self._pending_info.set_result(dict(event.data))
            elif status == "heartbeat":
                ble_connected = event.data.get("ble_connected") == "true"
                self._shaver_connected = ble_connected
                if not ble_connected:
                    self._cancel_pending_reads()
            elif status == "ready":
                self._shaver_connected = True
                self._ready_event.set()
                if not self._notify_callbacks:
                    self._needs_resubscribe = True
            elif status == "connected":
                pass  # GATT discovery still in progress
            elif status == "disconnected":
                self._shaver_connected = False
                self._cancel_pending_reads()

            # Fire callback when any component of state changed
            if self._disconnect_cb and (
                was_alive != self._esp_alive
                or was_connected != self._shaver_connected
            ):
                self._disconnect_cb()

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

        # Wait for bridge to report alive and device connected
        await self._wait_for_bridge()

    async def _wait_for_bridge(self) -> None:
        """Wait until the ESP bridge reports alive and BLE device connected."""
        if self.is_connected:
            return
        self._ready_event.clear()
        _LOGGER.debug("%s: Waiting for ESP bridge ready event...", self._address)
        # Trigger immediate info event instead of waiting for next heartbeat
        try:
            await self._hass.services.async_call(
                "esphome", self._svc_name("ble_get_info"), {}, blocking=True,
            )
        except Exception:
            pass
        # Wait up to 10s for ESP to report alive
        for _ in range(10):
            await asyncio.sleep(1)
            if self._esp_alive:
                break
        if not self._esp_alive:
            raise TransportError("ESP bridge did not respond within 10s")
        if self.is_connected:
            _LOGGER.info(
                "ESP bridge ready (mac=%s, version=%s)",
                self._detected_mac,
                self._bridge_version,
            )
            return
        # ESP alive but device not connected — wait for "ready" event
        _LOGGER.debug(
            "%s: ESP bridge alive, waiting for BLE device to connect...",
            self._address,
        )
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            if self.is_connected:
                _LOGGER.info("ESP bridge ready after timeout (mac=%s)", self._detected_mac)
                return
            _LOGGER.debug("ESP bridge alive but BLE device not connected (yet)")
            return
        _LOGGER.info(
            "ESP bridge ready (mac=%s, version=%s)",
            self._detected_mac,
            self._bridge_version,
        )

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
        self._ready_event.clear()
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
            self._pending_reads.pop(char_uuid, None)
            _LOGGER.debug("Read timeout for %s (other reads continue)", char_uuid)
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
        if not self._setup_done or not self._shaver_connected:
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
        if not self._shaver_connected:
            # Device already gone — just clear local callbacks
            self._notify_callbacks.clear()
            return
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
