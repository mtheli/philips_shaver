from __future__ import annotations

from collections.abc import Callable
from typing import Any

import asyncio
import time
import voluptuous as vol
import logging

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
)

try:  # HA ≥ 2025.8
    from homeassistant.config_entries import OptionsFlowWithReload
except ImportError:  # pragma: no cover — older cores + the pinned CI
    # test stack (pytest-homeassistant-custom-component ships HA 2025.1).
    # Fallback loses only the automatic entry reload on options save.
    from homeassistant.config_entries import OptionsFlow as OptionsFlowWithReload
from homeassistant.core import Event, callback

try:  # HA ≥ 2025.2
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # pragma: no cover — pinned CI test stack (HA 2025.1)
    from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_discovered_service_info,
    async_last_service_info,
)
from homeassistant.data_entry_flow import AbortFlow
from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakAbortedError,
    BleakConnectionError,
    BleakNotFoundError,
    BleakOutOfConnectionSlotsError,
    establish_connection,
)

from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict,
)
from .const import (
    DOMAIN,
    PHILIPS_SERVICE_UUIDS,
    CHAR_CAPABILITIES,
    CHAR_BATTERY_LEVEL,
    CHAR_MODEL_NUMBER,
    CHAR_FIRMWARE_REVISION,
    CHAR_SOFTWARE_REVISION,
    CHAR_DEVICE_TYPE,
    CHAR_GROOMER_CAPABILITIES,
    CHAR_DEVICE_STATE,
    CHAR_HANDLE_LOAD_TYPE,
    CHAR_HISTORY_SYNC_STATUS,
    SVC_BATTERY,
    SVC_DEVICE_INFO,
    SVC_PLATFORM,
    SVC_HISTORY,
    SVC_CONTROL,
    SVC_SERIAL,
    SVC_GROOMER,
    CONF_ADDRESS,
    CONF_CAPABILITIES,
    CONF_SERVICES,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_NAME,
    CONF_AREA,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_BLEAK,
    TRANSPORT_ESP_BRIDGE,
    CONF_ESP_DEVICE_NAME,
    CONF_ESP_BRIDGE_ID,
    CONF_NOTIFY_THROTTLE,
    CONF_PIPELINED_READS,
    DEFAULT_NOTIFY_THROTTLE,
    DEFAULT_PIPELINED_READS,
    MIN_NOTIFY_THROTTLE,
    MAX_NOTIFY_THROTTLE,
)
from .transport import (
    UNPAIR_FAILED,
    UNPAIR_OK,
    UNPAIR_UNAVAILABLE,
    EspBridgeTransport,
    async_unpair_bridge_slot,
    describe_available_paths,
    describe_connection_path,
    is_local_bluez_connection,
)
from .exceptions import (
    DeviceAsleepException,
    DeviceNotFoundException,
    CannotConnectException,
    NotPairedException,
    TransportError,
)

def _is_hassio(hass) -> bool:
    """Check if Home Assistant is running on HAOS / Supervised."""
    return "hassio" in hass.config.components

_LOGGER = logging.getLogger(__name__)

# Max age of the last *connectable* advertisement before we treat the shaver as
# asleep. habluetooth keeps returning a connectable BLEDevice for up to ~195 s
# after the last advertisement, so a fresh BLEDevice reference alone does not
# prove the device is reachable; the device advertises every ~1-2 s while awake,
# so a stricter window cleanly separates "awake now" from "asleep".
_STALE_ADV_MAX_SECONDS = 15.0

# Sentinel option in the Direct-BLE picker that switches to free-text entry.
# Picked when the user wants to type a MAC that isn't currently advertising.
_MANUAL_ADDRESS = "__manual__"

# Proprietary service UUIDs shavers carry in their advertisements — the same
# set the bluetooth manifest matches on; used to filter the discovered-device
# picker (standard Battery/DeviceInfo UUIDs would match half the room).
_SHAVER_ADV_UUIDS = {
    u.lower() for u in PHILIPS_SERVICE_UUIDS if u.lower().startswith("8d560")
}


class PhilipsShaverOptionsFlow(OptionsFlowWithReload):
    """Options flow for Philips Shaver."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        is_esp = (
            self.config_entry.data.get(CONF_TRANSPORT_TYPE) == TRANSPORT_ESP_BRIDGE
        )

        if user_input is not None:
            entry_data = {}
            if is_esp and CONF_NOTIFY_THROTTLE in user_input:
                entry_data[CONF_NOTIFY_THROTTLE] = int(
                    user_input[CONF_NOTIFY_THROTTLE]
                )
            if is_esp and CONF_PIPELINED_READS in user_input:
                entry_data[CONF_PIPELINED_READS] = bool(
                    user_input[CONF_PIPELINED_READS]
                )
            return self.async_create_entry(data=entry_data)

        schema_fields: dict = {}

        if is_esp:
            schema_fields[vol.Required(CONF_NOTIFY_THROTTLE)] = NumberSelector(
                NumberSelectorConfig(
                    min=MIN_NOTIFY_THROTTLE,
                    max=MAX_NOTIFY_THROTTLE,
                    step=50,
                    unit_of_measurement="ms",
                    mode=NumberSelectorMode.BOX,
                )
            )
            schema_fields[vol.Required(CONF_PIPELINED_READS)] = BooleanSelector()

        if not schema_fields:
            # Direct BLE: no configurable options currently
            return self.async_create_entry(data={})

        data_schema = vol.Schema(schema_fields)

        suggested_values = {}
        if is_esp:
            suggested_values[CONF_NOTIFY_THROTTLE] = self.config_entry.options.get(
                CONF_NOTIFY_THROTTLE,
                DEFAULT_NOTIFY_THROTTLE,
            )
            suggested_values[CONF_PIPELINED_READS] = self.config_entry.options.get(
                CONF_PIPELINED_READS,
                DEFAULT_PIPELINED_READS,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                data_schema, suggested_values
            ),
            errors=errors,
        )


class PhilipsShaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Philips Shaver."""

    VERSION = 1
    MINOR_VERSION = 3

    discovery_info: BluetoothServiceInfoBleak | None = None

    # Intermediate data storage between steps
    fetched_data: dict[str, Any] | None = None
    fetched_address: str | None = None
    fetched_name: str | None = None
    fetched_transport_type: str | None = None
    fetched_esp_device_name: str | None = None
    fetched_esp_bridge_id: str = ""
    fetched_bridge_info: dict[str, str] | None = None
    _pair_address: str | None = None  # MAC for D-Bus pairing step

    # Transport of the last probe that actually connected. None until a
    # probe establishes a connection; deliberately NOT reset on failed
    # connects so a retry that never reaches the device keeps showing
    # the pairing dialog that matches the last known transport.
    _probe_via_proxy: bool | None = None
    _probe_proxy_name: str | None = None
    # One-shot marker: wait_pair just bonded the bridge, so the next
    # esp_bridge_status render acknowledges the success.
    _just_paired: bool = False
    # Set once the user picked an action for a bonded-but-unconfigured
    # slot, so re-entering the health check doesn't re-show the menu.
    _slot_action_chosen: bool = False
    # One-shot marker: reset_bridge just cleared the bond, so the next
    # request_pair render confirms the slot is free.
    _just_unpaired: bool = False
    # The ESP auto-route out of bluetooth_confirm probes bridge slots for
    # seconds — run it once per flow, not on every re-render.
    _esp_redirect_checked: bool = False
    # Progress state: unpair (reset_bridge) and ESP capabilities read.
    _unpair_task: asyncio.Task | None = None
    _unpair_outcome: str = ""
    _esp_caps_task: asyncio.Task | None = None
    _esp_caps_result: dict[str, Any] | None = None
    _esp_read_error: str = ""
    # Pair-mode progress state (async_show_progress two-phase flow).
    _pair_arm_task: asyncio.Task | None = None
    _pair_scan_task: asyncio.Task | None = None
    _pair_future: asyncio.Future | None = None
    _pair_unsub: Callable[[], None] | None = None
    _pair_svc_name: str = ""
    _pair_result: dict[str, str] | None = None
    # Direct-BLE probe progress state, shared by bluetooth_confirm,
    # user_bleak and the D-Bus pair step; ble_probe_finish routes the
    # outcome back to whichever step started the probe.
    _ble_probe_task: asyncio.Task | None = None
    _ble_probe_result: dict[str, Any] | None = None
    _ble_probe_origin: str = ""
    _ble_probe_address: str = ""
    # One-shot <ha-alert> for the next bluetooth_confirm render
    # (errors[] doesn't render on that schema-less step).
    _confirm_status: str = ""
    # One-shot errors["base"] for the next user_bleak / pair render.
    _manual_error: str = ""
    _pair_error: str = ""
    # user_bleak: user picked the "enter manually" sentinel — render the
    # free-text field instead of the discovered-device picker.
    _manual_address_entry: bool = False
    # ESP dropdown values whose node answered no probe (⚪) — the sole-ESP
    # auto-select must not skip the picker for one of these.
    _offline_esp_values: frozenset = frozenset()

    def _abort_if_already_configured(self) -> None:
        """Abort with a detailed message when this unique_id already exists.

        Names the transport and status (active/disabled) of the existing
        entry — a plain "already configured" regularly sends users hunting
        for a duplicate they can't find because the entry is disabled or
        lives on the other transport.
        """
        for entry in self._async_current_entries():
            if entry.unique_id and entry.unique_id == self.unique_id:
                transport = entry.data.get(CONF_TRANSPORT_TYPE)
                transport_label = (
                    "ESP32 Bridge" if transport == TRANSPORT_ESP_BRIDGE
                    else "Direct Bluetooth"
                )
                status = "disabled" if entry.disabled_by is not None else "active"
                raise AbortFlow(
                    "already_configured_detail",
                    description_placeholders={
                        "transport": transport_label,
                        "status": status,
                    },
                )

    @staticmethod
    async def _read_with_auth_retry(
        client: BleakClient,
        char_uuid: str,
        timeout: float = 10.0,
    ) -> bytes | None:
        """Read a GATT characteristic, retrying once after a short delay
        on authentication errors.

        ESPHome bluetooth_proxy negotiates SMP in the background on the
        first read of a protected characteristic. That first read returns
        status=0x05; auth finishes ~500-1000 ms later. A single retry
        with a 2s grace period turns the transient failure into a
        success without false-positive "not paired" errors.
        """
        try:
            return await asyncio.wait_for(
                client.read_gatt_char(char_uuid), timeout=timeout
            )
        except (BleakError, TimeoutError) as err:
            err_msg = str(err).lower()
            auth_error = any(
                hint in err_msg
                for hint in (
                    "0x05",
                    "0x0e",
                    "0x0f",
                    "unlikely error",
                    "insufficient auth",
                    "insufficient enc",
                    "authentication",
                )
            )
            if not auth_error or not client.is_connected:
                raise
            _LOGGER.info(
                "Read on %s returned auth error — waiting for SMP to complete",
                char_uuid,
            )
            await asyncio.sleep(2.0)
            return await asyncio.wait_for(
                client.read_gatt_char(char_uuid), timeout=timeout
            )

    def _bump_progress(self, value: float) -> None:
        """Advance the determinate progress bar, if this core supports it.

        ``async_update_progress`` arrived in HA 2025.5 — on older cores the
        progress step simply keeps its indeterminate spinner. Calls made
        while no progress step is showing fire an update event nothing
        listens to; harmless.
        """
        update = getattr(self, "async_update_progress", None)
        if update is not None:
            update(min(1.0, max(0.0, value)))

    async def _creep_progress(
        self, start: float, end: float, duration: float
    ) -> None:
        """Creep the bar on wall-clock time while a long single await runs.

        ``establish_connection`` retries internally for up to ~90 s
        against an unreachable device or a stale bond without any
        callback we could hook — without this the bar sits frozen at the
        pre-connect milestone the whole time. The caller cancels the
        task the moment the await returns; real milestones then overwrite
        whatever the creep reached.
        """
        loop = self.hass.loop
        t0 = loop.time()
        while True:
            await asyncio.sleep(2.0)
            frac = min(1.0, (loop.time() - t0) / duration)
            self._bump_progress(start + (end - start) * frac)
            if frac >= 1.0:
                return

    async def _async_fetch_capabilities(
        self,
        address,
    ) -> dict[str, Any]:
        """Connect to the BLE device and read its capabilities."""
        capabilities: dict[str, Any] = {}

        # Gate on the age of the last *connectable* advertisement. Within the
        # ~195 s habluetooth fallback window async_ble_device_from_address still
        # hands back a stale BLEDevice whose connect just drops mid-handshake.
        # The history timestamp is updated on every received advertisement
        # (including deduplicated identical ones — dedup only suppresses callback
        # dispatch, not the history write), so an awake shaver is never misread.
        last = async_last_service_info(self.hass, address, connectable=True)
        # A BlueZ RSSI-invalidation event (RSSI -127) also bumps the history
        # timestamp without a packet on the air — treat it as "not seen", or
        # the sentinel keeps the entry fresh and a stale BLEDevice slips past
        # the gate (seen after an adapter power-cycle, where the doomed
        # connects were then misread as a stale bond).
        stale_rssi = (
            last is not None and last.rssi is not None and last.rssi <= -127
        )
        age = None if last is None else (time.monotonic() - last.time)
        if last is None or stale_rssi or age > _STALE_ADV_MAX_SECONDS:
            _LOGGER.info(
                "%s: no recent connectable advertisement (%s) — device asleep",
                address,
                "never seen" if last is None
                else "stale RSSI -127" if stale_rssi
                else f"{age:.0f}s ago",
            )
            raise DeviceAsleepException

        device = async_ble_device_from_address(self.hass, address)
        if not device:
            raise DeviceNotFoundException("BLE device not found")

        client: BleakClient | None = None
        try:
            # Progress milestones: the connect is a single await and by far
            # the longest leg, so the bar sits low until it lands, then
            # advances per characteristic read.
            self._bump_progress(0.05)
            # use_services_cache skips a full service re-discovery on
            # reconnects (retry after wake / not_paired retry); the 30 s
            # budget matches Sonicare — with the probe running as a
            # progress task a longer connect no longer freezes the dialog.
            # A stale bond makes establish_connection retry internally for
            # up to ~90 s (4 attempts) — creep the bar toward the
            # post-connect milestone so the dialog visibly keeps working.
            creep = self.hass.async_create_task(
                self._creep_progress(0.05, 0.38, 90.0)
            )
            try:
                client = await establish_connection(
                    BleakClient, device, "philips_shaver",
                    use_services_cache=True, timeout=30.0,
                )
            finally:
                creep.cancel()

            if not client.is_connected:
                raise CannotConnectException("BLE connection failed")
            _LOGGER.info("Connected to %s, address=%s", device.name, address)
            self._bump_progress(0.4)

            capabilities["connection_path"] = describe_connection_path(
                self.hass, client, device
            )
            # Remember which transport carried this probe: a later
            # NotPairedException must route to the matching pairing
            # dialog (host instructions vs. proxy guidance) and decide
            # whether the D-Bus pairing machinery applies at all.
            self._probe_via_proxy = not is_local_bluez_connection(client)
            # Scanner names carry the adapter MAC in parentheses — strip it
            # for the dialog (same as _short_scanner in the preview).
            self._probe_proxy_name = (
                capabilities["connection_path"].split(" (")[0]
                if self._probe_via_proxy else None
            )
            _LOGGER.info(
                "%s: capabilities probe connected via %s",
                address,
                capabilities["connection_path"],
            )

            _LOGGER.info("Reading services from %s...", address)
            services = client.services
            capabilities["services"] = [str(s.uuid) for s in services]
            self._bump_progress(0.45)

            # Probe battery level to verify pairing (requires encryption).
            # Any read failure here indicates the device is not paired —
            # BlueZ returns ATT errors (e.g. 0x0e "Unlikely Error") or
            # times out while attempting auto-pairing.
            #
            # Via ESPHome bluetooth_proxy: the first read on a protected
            # char returns status=0x05 while the ESP is still negotiating
            # SMP in the background. Auth completes a moment later and the
            # retry succeeds. Without the retry we'd disconnect before the
            # proxy has a chance to finish bonding.
            _LOGGER.info("Probing pairing status on %s...", address)
            if services.get_characteristic(CHAR_BATTERY_LEVEL):
                try:
                    raw_battery = await self._read_with_auth_retry(
                        client, CHAR_BATTERY_LEVEL, timeout=10
                    )
                    if raw_battery:
                        capabilities["battery"] = raw_battery[0]
                    else:
                        raise NotPairedException(
                            "Battery probe returned empty data"
                        )
                except NotPairedException:
                    raise
                except (BleakError, TimeoutError) as err:
                    err_msg = str(err).lower()
                    # ATT errors that indicate missing pairing/encryption,
                    # even if BlueZ drops the connection afterwards:
                    #   0x05 = Insufficient Authentication
                    #   0x0e = Unlikely Error (encryption required)
                    #   0x0f = Insufficient Encryption
                    if any(
                        hint in err_msg
                        for hint in (
                            "0x05",
                            "0x0e",
                            "0x0f",
                            "unlikely error",
                            "insufficient auth",
                            "insufficient enc",
                        )
                    ) or client.is_connected:
                        _LOGGER.warning(
                            "Battery probe failed on %s: %s – device not paired",
                            address,
                            err,
                        )
                        raise NotPairedException from err
                    _LOGGER.warning(
                        "Connection lost during battery probe on %s: %s",
                        address,
                        err,
                    )
                    raise CannotConnectException from err
                except EOFError:
                    # BlueZ drops the D-Bus connection when auto-pairing
                    # fails on an unpaired device.
                    _LOGGER.warning(
                        "D-Bus connection dropped during battery probe "
                        "on %s – device not paired",
                        address,
                    )
                    raise NotPairedException(
                        "D-Bus EOF during encrypted read"
                    )

            self._bump_progress(0.6)
            _LOGGER.info("Reading capabilities from %s...", address)
            if services.get_characteristic(CHAR_CAPABILITIES):
                try:
                    raw_cap = await self._read_with_auth_retry(
                        client, CHAR_CAPABILITIES, timeout=10
                    )
                except BleakError as err:
                    err_msg = str(err).lower()
                    if any(
                        hint in err_msg
                        for hint in (
                            "notpermitted",
                            "not permitted",
                            "authentication",
                            "security",
                            "insufficient",
                        )
                    ):
                        raise NotPairedException from err
                    raise CannotConnectException from err

                if raw_cap:
                    cap_int = int.from_bytes(raw_cap, "little")
                    capabilities["capabilities"] = cap_int
                else:
                    raise NotPairedException(
                        "Could not read characteristics – device may not be paired"
                    )
            else:
                capabilities["capabilities"] = 0

            self._bump_progress(0.7)
            # Read model number and firmware for display in capabilities step
            for char_uuid, key in (
                (CHAR_MODEL_NUMBER, "model_number"),
                (CHAR_FIRMWARE_REVISION, "firmware"),
            ):
                if services.get_characteristic(char_uuid):
                    try:
                        raw = await client.read_gatt_char(char_uuid)
                        if raw:
                            capabilities[key] = bytes(raw).decode(
                                "utf-8", errors="replace"
                            ).strip()
                    except Exception:
                        pass

            # Fallback: Software Revision when Firmware Revision is absent
            if not capabilities.get("firmware"):
                if services.get_characteristic(CHAR_SOFTWARE_REVISION):
                    try:
                        raw = await client.read_gatt_char(CHAR_SOFTWARE_REVISION)
                        if raw:
                            capabilities["firmware"] = bytes(raw).decode(
                                "utf-8", errors="replace"
                            ).strip()
                    except Exception:
                        pass

            self._bump_progress(0.85)
            # Read Device Type (0x0119) — "OneBlade" for OneBlade, model number for shavers
            if services.get_characteristic(CHAR_DEVICE_TYPE):
                try:
                    raw = await client.read_gatt_char(CHAR_DEVICE_TYPE)
                    if raw:
                        capabilities["device_type"] = bytes(raw).decode(
                            "utf-8", errors="replace"
                        ).strip().strip("\x00")
                except Exception:
                    pass

            self._bump_progress(0.95)
            # Read Groomer Capabilities (0x0702) when Smart Groomer Service is present
            if services.get_characteristic(CHAR_GROOMER_CAPABILITIES):
                try:
                    raw = await client.read_gatt_char(CHAR_GROOMER_CAPABILITIES)
                    if raw:
                        capabilities["groomer_capabilities"] = int.from_bytes(
                            raw, "little"
                        )
                except Exception:
                    pass

        except (BleakConnectionError, TimeoutError) as err:
            err_msg = str(err).lower()
            # "failed to discover services, device disconnected" is the
            # classic symptom of a stale bond — BlueZ connects with old
            # encryption keys, the device rejects them and disconnects
            # during service discovery.
            if "failed to discover services" in err_msg:
                _LOGGER.warning(
                    "Service discovery failed for %s — likely stale bond: %s",
                    address,
                    err,
                )
                raise NotPairedException from err
            _LOGGER.error("Connection error during capabilities fetch: %s", err)
            raise CannotConnectException from err
        finally:
            if client and client.is_connected:
                await client.disconnect()

        return capabilities

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle Zeroconf discovery of ESPHome devices.

        Checks if the discovered ESPHome device has our Shaver bridge
        services registered. If not, aborts silently.
        """
        host = discovery_info.hostname or ""
        device_name = host.rstrip(".").removesuffix(".local").replace("-", "_")
        if not device_name:
            return self.async_abort(reason="not_supported")

        # Wait for ESPHome to register services (may not be ready yet)
        for _ in range(10):
            bridge_ids = self._detect_esp_bridge_ids(device_name)
            if bridge_ids:
                break
            await asyncio.sleep(3)
        else:
            return self.async_abort(reason="not_supported")

        # Found bridges — probe to verify they are OURS (not Sonicare etc.)
        # by calling ble_get_info and listening on our event name.
        self.fetched_esp_device_name = device_name
        self._esp_bridge_ids = bridge_ids

        configured_macs = {
            entry.unique_id.upper()
            for entry in self._async_current_entries()
            if entry.unique_id
        }
        # (esp_device_name, esp_bridge_id) tuples that already have a
        # ConfigEntry — a probe-independent fallback: the info event's
        # ``mac`` is the live remote_bda, which reads 00:00:… while the
        # shaver is disconnected (asleep, ESP freshly booted), so a
        # MAC-only check would re-offer an already-configured slot.
        configured_bridges = {
            (
                entry.data.get(CONF_ESP_DEVICE_NAME, ""),
                entry.data.get(CONF_ESP_BRIDGE_ID, ""),
            )
            for entry in self._async_current_entries()
            if entry.data.get(CONF_TRANSPORT_TYPE) == TRANSPORT_ESP_BRIDGE
        }

        unconfigured = False
        found_any = False
        for did in bridge_ids:
            # Direct ConfigEntry match — skip the probe; the entry also
            # proves this is a Shaver bridge (it answered ours once).
            if (device_name, did) in configured_bridges:
                found_any = True
                continue
            info = await self._probe_bridge_info(device_name, did)
            if info is None:
                continue  # Not our bridge type or not responding — skip
            found_any = True
            # Prefer identity_address (NVS-persisted, used as the
            # ConfigEntry unique_id) over mac (live remote_bda, zeroed
            # while the shaver is disconnected).
            identity = info.get("identity_address", "").upper()
            mac = info.get("mac", "").upper()
            known = {
                m for m in (identity, mac)
                if m and m != "00:00:00:00:00:00"
            }
            if not known or not known.intersection(configured_macs):
                unconfigured = True
                break

        if not found_any:
            # No bridge responded on our event — not a Shaver bridge
            return self.async_abort(reason="not_supported")
        if not unconfigured:
            return self.async_abort(reason="already_configured")

        _LOGGER.info("Zeroconf: found Shaver bridge on ESP device '%s'", device_name)
        # Tag the discovery card with the transport class so users can tell an
        # ESP-bridge discovery apart from a direct-Bluetooth one at a glance.
        self.context["title_placeholders"] = {
            "name": f"ESP32 Bridge ({device_name.replace('_', '-')})"
        }

        if len(bridge_ids) > 1:
            return await self.async_step_esp_select_device()
        self.fetched_esp_bridge_id = bridge_ids[0]
        return await self._esp_bridge_health_check()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_already_configured()

        self.discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery and fetch capabilities."""
        assert self.discovery_info is not None
        # Progress re-invocations of a running probe land here first —
        # before the ESP auto-route, whose slot probes would add seconds
        # of latency to every re-entry.
        if (progress := self._ble_probe_progress("bluetooth_confirm")) is not None:
            return progress

        # On first display, check if an ESP bridge is already connected
        # to this shaver — redirect to ESP flow if so. Checked once per
        # flow: re-renders after a failed probe must not repeat the
        # multi-second slot probes.
        if user_input is None and not self._esp_redirect_checked:
            self._esp_redirect_checked = True
            esp = await self._find_esp_bridge_for_mac(
                self.discovery_info.address
            )
            if esp:
                _LOGGER.info(
                    "ESP bridge '%s' is already connected to %s — "
                    "redirecting to ESP bridge setup",
                    esp["device_name"],
                    self.discovery_info.address,
                )
                self.fetched_esp_device_name = esp["device_name"]
                # Lowercase: HA lowercases service names, so the bridge_id
                # suffix is lowercase on the wire — keep our copy consistent.
                self.fetched_esp_bridge_id = esp.get("bridge_id", "").lower()
                self.fetched_bridge_info = esp["info"]
                # Tag the discovery card so flow_title ("{name}") renders the
                # transport class here too — this redirect bypasses the normal
                # bluetooth_confirm path that would otherwise set it.
                self.context["title_placeholders"] = {
                    "name": f"ESP32 Bridge ({esp['device_name'].replace('_', '-')})"
                }
                return await self._esp_bridge_health_check()

        if user_input is not None:
            address = self.discovery_info.address
            # Quick D-Bus pre-check: if the device is known to BlueZ but
            # not paired, skip the slow bleak connection attempts (~80s)
            # and go straight to the pairing step. Skipped when a remote
            # scanner is the likely carrier — the BlueZ bond state says
            # nothing about a proxy-carried connection.
            paths = describe_available_paths(self.hass, address)
            likely_proxy = bool(paths) and not paths[0]["is_local"]
            if not likely_proxy:
                from .dbus_pairing import is_dbus_available, async_is_device_paired

                if is_dbus_available():
                    paired = await async_is_device_paired(address)
                    if paired is False:
                        _LOGGER.info(
                            "D-Bus pre-check: %s is not paired — "
                            "skipping to pairing step",
                            address,
                        )
                        self._pair_address = address
                        return await self.async_step_pair()

            return self._start_ble_probe("bluetooth_confirm", address)

        # One-shot outcome from ble_probe_finish. errors["base"] does not
        # render on this schema-less confirmation step, so failures are
        # injected as an <ha-alert> into the description; ha-markdown
        # renders it as a real coloured alert box.
        status = self._confirm_status
        self._confirm_status = ""

        self.context["title_placeholders"] = {
            "name": f"Bluetooth ({self.discovery_info.address})"
        }

        via, warning = self._transport_lines()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self.discovery_info.name or self.discovery_info.address,
                "address": self.discovery_info.address,
                "status": status,
                "via": via,
                "transport": warning,
            },
        )

    @staticmethod
    def _short_scanner(p: dict) -> str:
        # Scanner names carry the adapter MAC in parentheses; strip it —
        # the dialog cares about *which* device, not its MAC.
        return str(p["name"]).split(" (")[0]

    def _transport_lines(self) -> tuple[str, str]:
        """Return ``(via_suffix, warning)`` for the discovery confirm step.

        ``via_suffix`` names the likely carrier inline after "discovered
        at <mac>", mirroring the capabilities dialog's
        ``via <class> (<detail>)`` framing: "Direct Bluetooth" for a
        local adapter, "Bluetooth proxy" for a remote scanner.

        ``warning`` is a proxy-only <ha-alert>. Unlike the Sonicare
        integration (where proxy pairing is model-dependent), Philips
        shavers use LE Secure Connections with numeric comparison, which
        a standard Bluetooth proxy cannot complete — pairing over one
        fails outright, so the warning is unconditional and hard.

        habluetooth routes by signal strength, so the strongest scanner
        is only the *likely* carrier; recomputed each render so the
        ranking stays current.
        """
        address = self.discovery_info.address if self.discovery_info else ""
        paths = describe_available_paths(self.hass, address)
        if not paths:
            return "", ""

        def _rssi(p: dict) -> str:
            return f" ({p['rssi']} dBm)" if p["rssi"] is not None else ""

        best = paths[0]
        best_name = self._short_scanner(best)
        best_rssi = f", {best['rssi']} dBm" if best["rssi"] is not None else ""

        if best["is_local"]:
            via = f" via **Direct Bluetooth** ({best_name}{best_rssi})"
            return via, ""

        via = f" via **Bluetooth proxy** ({best_name}{best_rssi})"

        # Markdown is not parsed inside an HTML block, so the warning uses
        # <b>/<br> for emphasis and paragraph breaks.
        local = next((p for p in paths if p["is_local"]), None)
        if local is None:
            tail = (
                "Set the shaver up via a local Bluetooth adapter or the "
                "dedicated ESP32 bridge instead."
            )
        else:
            tail = (
                f"Your local adapter <b>{self._short_scanner(local)}</b> "
                f"also sees the shaver{_rssi(local)} — Home Assistant "
                "connects through the strongest signal, so move the "
                "shaver closer to it to prefer that path."
            )
        warning = (
            '<ha-alert alert-type="warning">'
            "This connection would go through the Bluetooth proxy "
            f"<b>{best_name}</b>{_rssi(best)}."
            "<br><br>Philips shavers cannot pair over a standard Bluetooth "
            "proxy — setup and live updates over this path will fail."
            f"<br><br>{tail}</ha-alert>\n\n"
        )
        return via, warning

    # ------------------------------------------------------------------
    # Direct BLE probe as a progress task (discovery + manual + pair)
    # ------------------------------------------------------------------
    def _ble_probe_placeholders(self) -> dict[str, str]:
        name = ""
        if self.discovery_info:
            name = self.discovery_info.name or self.discovery_info.address
        return {"name": name or self._ble_probe_address or ""}

    def _ble_probe_progress(
        self, step_id: str, action: str = "ble_probing"
    ) -> ConfigFlowResult | None:
        """Progress bookkeeping for a running direct-BLE probe.

        Returns None when no probe is in flight (the caller renders its
        form as usual), the progress view while the task runs, and the
        transition to ``ble_probe_finish`` once it is done.
        """
        task = self._ble_probe_task
        if task is None:
            return None
        if not task.done():
            return self.async_show_progress(
                step_id=step_id,
                progress_action=action,
                progress_task=task,
                description_placeholders=self._ble_probe_placeholders(),
            )
        self._ble_probe_result = task.result()
        self._ble_probe_task = None
        return self.async_show_progress_done(next_step_id="ble_probe_finish")

    def _start_ble_probe(self, step_id: str, address: str | None) -> ConfigFlowResult:
        """Kick off the capabilities probe as a background progress task."""
        self._ble_probe_origin = step_id
        self._ble_probe_address = address or ""
        self._ble_probe_task = self.hass.async_create_task(
            self._async_ble_probe(address or "")
        )
        return self.async_show_progress(
            step_id=step_id,
            progress_action="ble_probing",
            progress_task=self._ble_probe_task,
            description_placeholders=self._ble_probe_placeholders(),
        )

    async def _async_ble_probe(self, address: str) -> dict[str, Any]:
        """Run the capabilities probe (progress task) and box the outcome."""
        try:
            data = await self._async_fetch_capabilities(address)
            # Label BLE security for the capabilities dialog. On a proxy
            # connection the bond lives in the proxy's NVS — BlueZ can't
            # see it, but every readable shaver characteristic is
            # encrypt-gated, so a successful probe implies encryption.
            if self._probe_via_proxy:
                data["pairing"] = "bonded"
            else:
                from .dbus_pairing import is_dbus_available, async_is_device_paired

                if is_dbus_available():
                    paired = await async_is_device_paired(address)
                    # None = indeterminate (device not in the BlueZ tree,
                    # D-Bus hiccup) — better no row than a wrong one.
                    if paired is not None:
                        data["pairing"] = "bonded" if paired else "open_gatt"
            return {"ok": True, "data": data}
        except DeviceAsleepException:
            return {"ok": False, "error": "asleep"}
        except NotPairedException:
            _LOGGER.error("Device %s is not paired", address)
            return {"ok": False, "error": "not_paired"}
        except DeviceNotFoundException:
            _LOGGER.error("Device %s not found in range", address)
            return {"ok": False, "error": "device_not_found"}
        except CannotConnectException:
            _LOGGER.error("Cannot connect to %s", address)
            return {"ok": False, "error": "cannot_connect"}
        except BleakOutOfConnectionSlotsError:
            _LOGGER.error("No connection slot available for %s", address)
            return {"ok": False, "error": "out_of_slots"}
        except BleakAbortedError:
            _LOGGER.error(
                "Connection aborted for %s — device may be out of range "
                "or using an unsupported Bluetooth proxy",
                address,
            )
            return {"ok": False, "error": "connection_aborted"}
        except BleakNotFoundError:
            # If habluetooth sees the device (advertisements) but bleak
            # can't connect, the most likely cause is a stale bond in
            # BlueZ preventing new connections.
            if async_ble_device_from_address(self.hass, address):
                _LOGGER.warning(
                    "Device %s is visible but unreachable — likely stale bond",
                    address,
                )
                return {"ok": False, "error": "stale_bond"}
            _LOGGER.error(
                "Device %s not found by any Bluetooth adapter", address
            )
            return {"ok": False, "error": "device_not_found"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during capabilities fetch")
            return {"ok": False, "error": "unknown"}

    async def async_step_ble_probe_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Route the probe outcome captured by the progress step.

        Success continues to show_capabilities; failures go back to the
        origin step — rendered as errors[] on the manual/pair forms and
        as an <ha-alert> on the schema-less discovery confirm.
        """
        result = self._ble_probe_result or {}
        self._ble_probe_result = None
        origin = self._ble_probe_origin
        address = self._ble_probe_address

        if result.get("ok"):
            self.fetched_data = result["data"]
            self.fetched_address = address
            self.fetched_name = (
                self.discovery_info.name if self.discovery_info else None
            ) or address
            self.fetched_transport_type = TRANSPORT_BLEAK
            return await self.async_step_show_capabilities()

        error = result.get("error", "unknown")

        if error in ("not_paired", "stale_bond"):
            self._pair_address = address
            # A proxy-carried connection cannot complete the shaver's
            # LESC pairing, and host-side tools (D-Bus agent, pair.sh)
            # have no effect on it — route to the hard proxy dialog
            # instead of the pairing machinery.
            if self._probe_via_proxy:
                return await self.async_step_not_paired_proxy()
            if origin == "pair":
                if error == "stale_bond":
                    self._pair_error = "pairing_failed"
                    return await self.async_step_pair()
                # D-Bus pairing succeeded but the device still refuses
                # reads — fall back to the manual instructions.
                _LOGGER.error(
                    "Pairing succeeded but device still not accessible "
                    "for %s — falling back to manual instructions",
                    address,
                )
                return await self.async_step_not_paired()
            return await self._route_to_pairing()

        if origin == "pair":
            if error == "asleep":
                self._pair_error = "device_asleep"
            elif error == "pairing_failed":
                self._pair_error = "pairing_failed"
            elif error == "unknown":
                self._pair_error = "pairing_failed"
            else:
                self._pair_error = "cannot_connect"
            return await self.async_step_pair()

        if origin == "user_bleak":
            self._manual_error = (
                "device_asleep" if error == "asleep" else error
            )
            return await self.async_step_user_bleak()

        # Discovery origin — keep the flow alive: an abort would dismiss
        # the discovery card, and ADV deduplication stops HA from
        # re-creating it when the shaver wakes.
        if error == "asleep":
            self._confirm_status = (
                '<ha-alert alert-type="error">The shaver is asleep — wake '
                "it (press the power button or place it on its charging "
                "stand), then click Read capabilities again.</ha-alert>\n\n"
            )
        elif error == "connection_aborted":
            self._confirm_status = (
                '<ha-alert alert-type="error">The connection was aborted — '
                "the shaver may be out of range, or the connection went "
                "through an unsupported standard Bluetooth proxy. Move the "
                "shaver closer to a local Bluetooth adapter, then click "
                "Read capabilities again.</ha-alert>\n\n"
            )
        else:
            self._confirm_status = (
                '<ha-alert alert-type="error">Could not read the shaver. '
                "Make sure it is switched on and in range, then click "
                "Read capabilities to try again. Details are in the logs "
                "(Settings → System → Logs).</ha-alert>\n\n"
            )
        return await self.async_step_bluetooth_confirm()

    @staticmethod
    def _esp_entry_unreachable(entry: ConfigEntry, context: str) -> bool:
        """True when an ESPHome entry cannot serve a bridge probe right now.

        Disabled bridges cannot hold a connection, and bridges whose
        ESPHome API link is down cannot answer — probing either only burns
        the probe timeout (their stale services may still be registered,
        so the service-based detection alone would wrongly pick them up).
        runtime_data is ESPHome's RuntimeEntryData; fall back to probing
        if the attribute layout ever changes.
        """
        if entry.disabled_by:
            _LOGGER.debug(
                "%s: bridge check — skipping disabled ESPHome entry '%s'",
                context, entry.title,
            )
            return True
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None and getattr(runtime, "available", True) is False:
            _LOGGER.debug(
                "%s: bridge check — skipping offline ESPHome entry '%s'",
                context, entry.title,
            )
            return True
        return False

    async def _find_esp_bridge_for_mac(self, mac: str) -> dict | None:
        """Locate an ESP bridge slot that already holds this shaver.

        Probes candidate slots via the lightweight ``ble_get_info`` event
        round-trip (3 s, parallel per ESP) instead of a full transport
        connect (10 s per slot) — and only slots answering on the
        *shaver* event channel count, so a Sonicare bridge sharing the
        same service-name pattern is no longer probed as a candidate.
        Matches ``identity_address`` in addition to the live ``mac`` so a
        bonded-but-asleep shaver (mac reads 00:00:…) still redirects to
        its bridge.
        """
        target = mac.upper()
        for entry in self.hass.config_entries.async_entries("esphome"):
            if self._esp_entry_unreachable(entry, mac):
                continue
            device_name = entry.data.get("device_name")
            if not device_name:
                continue
            esp_name = device_name.replace("-", "_")
            device_ids = self._detect_esp_bridge_ids(esp_name)
            if not device_ids:
                continue
            for did, info in await self._probe_shaver_bridges(
                esp_name, device_ids
            ):
                if info is None:
                    continue
                identity = info.get("identity_address", "").upper()
                live_mac = info.get("mac", "").upper()
                known = {
                    m for m in (identity, live_mac)
                    if m and m != "00:00:00:00:00:00"
                }
                if target in known:
                    return {
                        "device_name": esp_name,
                        "bridge_id": did,
                        "info": info,
                    }
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user — choose connection type."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["user_bleak", "esp_bridge"],
        )

    async def async_step_user_bleak(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual MAC address entry for direct BLE."""
        # Progress re-invocations of a running probe land here.
        if (progress := self._ble_probe_progress("user_bleak")) is not None:
            return progress

        errors: dict[str, str] = {}
        # One-shot outcome from ble_probe_finish (this form has a schema,
        # so errors[] renders normally here).
        if self._manual_error:
            errors["base"] = self._manual_error
            self._manual_error = ""

        if user_input is not None:
            raw = user_input["address"]
            if raw == _MANUAL_ADDRESS:
                # User picked the "enter manually" sentinel — re-render the
                # step as a free-text field, keep prior errors empty.
                self._manual_address_entry = True
            else:
                address = raw.upper()
                await self.async_set_unique_id(address)
                self._abort_if_already_configured()

                # Quick D-Bus pre-check (same as bluetooth_confirm path);
                # skipped when a remote scanner is the likely carrier.
                paths = describe_available_paths(self.hass, address)
                likely_proxy = bool(paths) and not paths[0]["is_local"]
                if not likely_proxy:
                    from .dbus_pairing import is_dbus_available, async_is_device_paired

                    if is_dbus_available():
                        paired = await async_is_device_paired(address)
                        if paired is False:
                            _LOGGER.info(
                                "D-Bus pre-check: %s is not paired — "
                                "skipping to pairing step",
                                address,
                            )
                            self._pair_address = address
                            return await self._route_to_pairing()

                return self._start_ble_probe("user_bleak", address)

        free_text_schema = vol.Schema({vol.Required("address"): str})

        # Free-text entry path: nothing discovered, or user asked for it.
        if self._manual_address_entry:
            return self.async_show_form(
                step_id="user_bleak",
                data_schema=free_text_schema,
                errors=errors,
            )

        # Build the discovered-device picker. Each option label carries the
        # advertisement age, RSSI and the scanner that would likely carry
        # the connect — the step is titled "Direct Bluetooth", but
        # habluetooth routes by signal strength and may pick a
        # bluetooth_proxy (which cannot pair a shaver).
        now_mono = time.monotonic()
        scored: list[tuple[int, SelectOptionDict]] = []
        for info in async_discovered_service_info(self.hass):
            uuids = {u.lower() for u in (info.service_uuids or [])}
            if not uuids & _SHAVER_ADV_UUIDS:
                continue
            age_s = max(0, int(now_mono - info.time)) if info.time else None
            rssi = info.rssi
            label_parts = [f"{info.name or 'Philips Shaver'} ({info.address})"]
            if age_s is not None:
                label_parts.append(f"{age_s}s ago")
            if rssi is not None:
                label_parts.append(f"{rssi} dBm")
            # Local scanner names carry the adapter MAC in parentheses;
            # strip it to keep the label compact ("hci0" / "atom-lite (proxy)").
            paths = describe_available_paths(self.hass, info.address)
            if paths:
                best = paths[0]
                via = str(best["name"]).split(" (")[0]
                label_parts.append(
                    f"via {via}" + ("" if best["is_local"] else " (proxy)")
                )
            label = label_parts[0] + (
                " — " + ", ".join(label_parts[1:]) if len(label_parts) > 1 else ""
            )
            scored.append((
                age_s if age_s is not None else 9999,
                SelectOptionDict(value=info.address, label=label),
            ))

        if scored:
            scored.sort(key=lambda t: t[0])  # freshest first
            options: list[SelectOptionDict] = [opt for _, opt in scored]
            options.append(SelectOptionDict(
                value=_MANUAL_ADDRESS,
                label="Other — enter address manually",
            ))
            return self.async_show_form(
                step_id="user_bleak",
                data_schema=vol.Schema({
                    vol.Required("address"): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }),
                errors=errors,
            )

        # No discoveries — fall back to free text.
        return self.async_show_form(
            step_id="user_bleak",
            data_schema=free_text_schema,
            errors=errors,
        )

    # Map each service to one representative characteristic for probing
    SERVICE_PROBE_CHARS: dict[str, str] = {
        SVC_BATTERY: CHAR_BATTERY_LEVEL,
        SVC_DEVICE_INFO: CHAR_MODEL_NUMBER,
        SVC_PLATFORM: CHAR_DEVICE_STATE,
        SVC_HISTORY: CHAR_HISTORY_SYNC_STATUS,
        SVC_CONTROL: CHAR_HANDLE_LOAD_TYPE,
        SVC_GROOMER: CHAR_GROOMER_CAPABILITIES,
    }

    async def _async_fetch_capabilities_esp(
        self,
        address: str,
        esp_device_name: str,
        esp_bridge_id: str = "",
    ) -> dict[str, Any]:
        """Read capabilities and probe services via ESP32 bridge."""
        transport = EspBridgeTransport(self.hass, address, esp_device_name, esp_bridge_id)
        try:
            # Progress milestones — each read is its own bridge round-trip,
            # so the bar advances per characteristic.
            self._bump_progress(0.05)
            await transport.connect()
            self._bump_progress(0.2)

            # Probe each service with one representative characteristic
            found_services: list[str] = []
            model_number: str | None = None
            probe_results: dict[str, bytes] = {}
            probe_count = max(1, len(self.SERVICE_PROBE_CHARS))
            for index, (svc_uuid, probe_char) in enumerate(
                self.SERVICE_PROBE_CHARS.items(), start=1
            ):
                raw = await transport.read_char(probe_char)
                if raw is not None:
                    found_services.append(svc_uuid)
                    probe_results[probe_char] = raw
                    if probe_char == CHAR_MODEL_NUMBER:
                        model_number = raw.decode("utf-8", errors="replace").strip()
                self._bump_progress(0.2 + 0.5 * index / probe_count)

            if not found_services:
                raise CannotConnectException(
                    "Could not read any service via ESP bridge – shaver may not be connected"
                )

            # Read capabilities (Control Service) — 0 if service absent (e.g. OneBlade)
            cap_int = 0
            if SVC_CONTROL in found_services:
                raw_cap = await transport.read_char(CHAR_CAPABILITIES)
                if raw_cap is not None:
                    cap_int = int.from_bytes(raw_cap, "little")

            self._bump_progress(0.75)
            # Battery — reuse probe result if available, otherwise read separately
            battery: int | None = None
            raw_bat = probe_results.get(CHAR_BATTERY_LEVEL)
            if not raw_bat:
                raw_bat = await transport.read_char(CHAR_BATTERY_LEVEL)
            if raw_bat:
                battery = raw_bat[0]

            self._bump_progress(0.82)
            # Read firmware revision (with Software Revision fallback)
            firmware: str | None = None
            raw_fw = await transport.read_char(CHAR_FIRMWARE_REVISION)
            if raw_fw:
                firmware = raw_fw.decode("utf-8", errors="replace").strip()
            if not firmware:
                raw_sw = await transport.read_char(CHAR_SOFTWARE_REVISION)
                if raw_sw:
                    firmware = raw_sw.decode("utf-8", errors="replace").strip()

            self._bump_progress(0.92)
            # Read Device Type (0x0119)
            device_type: str | None = None
            raw_dt = await transport.read_char(CHAR_DEVICE_TYPE)
            if raw_dt:
                device_type = raw_dt.decode("utf-8", errors="replace").strip().strip("\x00")

            # Groomer Capabilities — reuse probe result (probe char IS groomer caps)
            groomer_cap: int | None = None
            raw_gc = probe_results.get(CHAR_GROOMER_CAPABILITIES)
            if raw_gc:
                groomer_cap = int.from_bytes(raw_gc, "little")

            result: dict[str, Any] = {
                "services": found_services,
                "capabilities": cap_int,
                "shaver_mac": transport.detected_mac,
                "model_number": model_number,
                "firmware": firmware,
                "battery": battery,
            }
            if device_type:
                result["device_type"] = device_type
            if groomer_cap is not None:
                result["groomer_capabilities"] = groomer_cap
            return result

        except TransportError as err:
            raise CannotConnectException(str(err)) from err

        finally:
            await transport.disconnect()

    async def _get_esphome_device_options(self) -> list[SelectOptionDict]:
        """Build a list of ESPHome devices that host a philips_shaver bridge.

        Filters via `_detect_esp_bridge_ids()` so that ESPs without the
        philips_shaver component (e.g. plain bluetooth_proxy bridges) are
        excluded — picking one of those would otherwise fail later with
        a generic ``cannot_connect``. Note: device_name uses dashes
        (``atom-lite``) while HA service names use underscores
        (``atom_lite_ble_get_info``), so we substitute before the lookup.

        Probes each candidate ESP via ``ble_get_info`` to count paired vs
        free bridge slots; falls back to a plain bridge count if the
        probe times out or the ESP is offline.
        """
        # Slot-occupation counts use unicode markers (🔗 = paired slot,
        # 🟢 = empty slot) instead of English words so the picker reads
        # the same regardless of HA UI language. The data_description
        # below the field explains the markers in the user's locale.
        # See https://github.com/mtheli/philips_shaver — HA's strings.json
        # schema doesn't allow custom keys for Python-side label
        # translations, hence the icon route.
        esphome_entries = self.hass.config_entries.async_entries("esphome")
        options: list[SelectOptionDict] = []
        # Per-slot probe results, keyed by underscored ESP name. The slot
        # picker reuses these instead of re-probing the same bridges seconds
        # later; health check and capabilities fetch still probe fresh.
        self._probed_bridges: dict[str, list[tuple[str, dict | None]]] = {}
        # Option values whose ESP didn't answer any probe — the sole-ESP
        # auto-select must not skip the picker for one of these.
        self._offline_esp_values = set()
        for entry in esphome_entries:
            # A disabled entry cannot serve as a bridge — offering it would
            # only fail later with a generic cannot_connect.
            if entry.disabled_by:
                _LOGGER.debug(
                    "esp_select: skipping disabled ESPHome entry '%s'",
                    entry.title,
                )
                continue
            device_name = entry.data.get("device_name")
            if not device_name:
                continue
            esp_service_id = device_name.replace("-", "_")
            bridge_ids = self._detect_esp_bridge_ids(esp_service_id)
            if not bridge_ids:
                continue
            # When ESPHome already knows the link is down, don't burn the
            # probe timeout — fall through to the offline branch directly
            # (the ESP stays visible with the ⚪ marker by design).
            runtime = getattr(entry, "runtime_data", None)
            if runtime is not None and getattr(runtime, "available", True) is False:
                _LOGGER.debug(
                    "esp_select: ESPHome entry '%s' is offline — skipping probe",
                    entry.title,
                )
                results = [(did, None) for did in bridge_ids]
            else:
                results = await self._probe_shaver_bridges(
                    esp_service_id, bridge_ids
                )
            self._probed_bridges[esp_service_id] = results
            infos = [info for _, info in results if info is not None]
            slot_info = ""
            is_offline = False
            if infos:
                # A slot counts as paired when it holds an identity (NVS
                # bond) or a live remote MAC — mac alone reads 00:00:…
                # while the bonded shaver is asleep.
                paired = sum(
                    1
                    for info in infos
                    if (info.get("identity_address") or "").strip()
                    or (
                        info.get("mac")
                        and info["mac"] != "00:00:00:00:00:00"
                    )
                )
                free = len(infos) - paired
                if paired and free:
                    slot_info = f"{paired} 🔗 / {free} 🟢"
                elif free:
                    slot_info = f"{free} 🟢"
                elif paired:
                    slot_info = f"{paired} 🔗"
            else:
                # Probe failed for every bridge_id — ESP is offline (or
                # services are stale leftovers from a previous firmware).
                # Show but mark with the ⚪ prefix; the data_description
                # below the field explains the marker. (Sonicare's config
                # flow filters offline ESPs entirely; we deliberately keep
                # them visible so the user can see *why* their ESP is in
                # the list but unselectable.)
                is_offline = True
                self._offline_esp_values.add(device_name)
                if len(bridge_ids) > 1:
                    slot_info = f"{len(bridge_ids)} bridges"
            label = f"{entry.title} ({device_name})"
            if slot_info:
                label = f"{label}, {slot_info}"
            if is_offline:
                label = f"⚪ {label}"
            options.append(SelectOptionDict(value=device_name, label=label))
        return options

    async def _probe_bridge_info(
        self, esp_device_name: str, bridge_id: str, timeout: float = 3.0,
    ) -> dict[str, str] | None:
        """Probe a single bridge slot via ble_get_info.

        Returns the info-event payload, or ``None`` if the call timed out
        or no shaver-bridge response was received. Listening on
        ``esphome.philips_shaver_ble_status`` is the disambiguator versus
        a philips_sonicare bridge that happens to share service names.
        """
        svc_name = f"{esp_device_name}_ble_get_info"
        if bridge_id:
            svc_name += f"_{bridge_id}"
        if not self.hass.services.has_service("esphome", svc_name):
            return None

        info_future: asyncio.Future[dict[str, str]] = self.hass.loop.create_future()

        @callback
        def _on_status(event: Event) -> None:
            if (event.data.get("status") == "info"
                    # HA's ServiceRegistry lowercases service names, so an
                    # uppercase bridge_id yields a lowercase service suffix
                    # while the event echoes the original case — compare
                    # case-insensitively.
                    and event.data.get("bridge_id", "").lower() == bridge_id.lower()
                    and not info_future.done()):
                info_future.set_result(dict(event.data))

        unsub = self.hass.bus.async_listen(
            "esphome.philips_shaver_ble_status", _on_status
        )
        try:
            await self.hass.services.async_call(
                "esphome", svc_name, {}, blocking=True
            )
            return await asyncio.wait_for(info_future, timeout=timeout)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — best-effort probe
            return None
        finally:
            unsub()

    async def _probe_shaver_bridges(
        self, device_name: str, bridge_ids: list[str]
    ) -> list[tuple[str, dict[str, str] | None]]:
        """Probe all bridge_ids on an ESP in parallel via ble_get_info.

        Returns ``(bridge_id, info | None)`` for every slot — ``None``
        marks a slot that didn't answer on our event channel (offline,
        or a different component such as a Sonicare bridge sharing the
        service-name pattern). Callers that only care about responders
        filter the Nones; the picker keeps them to show ⚪ slots.
        """
        results = await asyncio.gather(
            *(self._probe_bridge_info(device_name, did) for did in bridge_ids)
        )
        return list(zip(bridge_ids, results))

    def _detect_esp_bridge_ids(self, esp_device_name: str) -> list[str]:
        """Detect available device_id suffixes on an ESP bridge.

        Returns [""] for single-device (no suffix) or ["shaver", "oneblade", ...]
        for multi-device setups.
        """
        # Try unsuffixed first (single device)
        if self.hass.services.has_service("esphome", f"{esp_device_name}_ble_get_info"):
            return [""]

        # Multi-device: find suffixed services
        esphome_services = self.hass.services.async_services().get("esphome", {})
        prefix = f"{esp_device_name}_ble_get_info_"
        return [
            svc_name[len(prefix):]
            for svc_name in esphome_services
            if svc_name.startswith(prefix)
        ]

    async def async_step_esp_bridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle ESP32 bridge configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            esp_device_name = user_input["esp_device_name"].strip().replace("-", "_")

            # Detect available device_ids (single vs multi-device)
            device_ids = self._detect_esp_bridge_ids(esp_device_name)
            if not device_ids:
                _LOGGER.error("No philips_shaver services found on %s", esp_device_name)
                errors["base"] = "cannot_connect"
            else:
                self.fetched_esp_device_name = esp_device_name
                self._esp_bridge_ids = device_ids

                if len(device_ids) > 1:
                    # Multiple devices — let user pick
                    return await self.async_step_esp_select_device()

                # Single device (or single suffixed device)
                self.fetched_esp_bridge_id = device_ids[0]
                return await self._esp_bridge_health_check()

        esp_options = await self._get_esphome_device_options()

        # A single reachable ESP needs no dropdown — route straight into
        # its health check (Sonicare pattern). Offline (⚪) ESPs still get
        # the picker so the user sees *why* nothing is selectable.
        if len(esp_options) == 1 and user_input is None:
            sole = esp_options[0]["value"]
            if sole not in self._offline_esp_values:
                esp_device_name = sole.strip().replace("-", "_")
                bridge_ids = self._detect_esp_bridge_ids(esp_device_name)
                if bridge_ids:
                    self.fetched_esp_device_name = esp_device_name
                    self._esp_bridge_ids = bridge_ids
                    if len(bridge_ids) > 1:
                        return await self.async_step_esp_select_device()
                    self.fetched_esp_bridge_id = bridge_ids[0]
                    return await self._esp_bridge_health_check()

        if esp_options:
            data_schema = vol.Schema(
                {
                    vol.Required("esp_device_name"): SelectSelector(
                        SelectSelectorConfig(options=esp_options)
                    ),
                }
            )
        else:
            # Fallback to text input if no ESPHome devices found
            data_schema = vol.Schema(
                {
                    vol.Required("esp_device_name"): str,
                }
            )
            errors["base"] = "no_esphome_devices"

        return self.async_show_form(
            step_id="esp_bridge",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_esp_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let user pick which device on a multi-device ESP bridge."""
        # Collect MACs already configured for this integration
        configured_macs = {
            entry.unique_id.upper()
            for entry in self._async_current_entries()
            if entry.unique_id
        }

        if user_input is not None:
            selected = user_input["esp_bridge_id"]
            # Re-derive state from stored info instead of parsing the value
            # (was a fragile "✅ "-prefix hack before).
            info = self._esp_device_info.get(selected) or {}
            mac = info.get("mac", "").upper()
            if mac and mac in configured_macs:
                return self.async_abort(reason="already_configured")
            self.fetched_esp_bridge_id = selected
            self.fetched_bridge_info = info
            return await self._esp_bridge_health_check()

        # Reuse the probes collected while building the ESP dropdown when they
        # cover this ESP's slots — they are seconds old, and probing again only
        # delays the picker (Sonicare pattern). Zeroconf and other entry paths
        # have no cache and probe fresh.
        if not hasattr(self, "_probed_bridges"):
            self._probed_bridges = {}
        cached = self._probed_bridges.get(self.fetched_esp_device_name)
        if cached is not None and {d for d, _ in cached} == set(self._esp_bridge_ids):
            results = cached
        else:
            results = await self._probe_shaver_bridges(
                self.fetched_esp_device_name, self._esp_bridge_ids
            )
            self._probed_bridges[self.fetched_esp_device_name] = results

        self._esp_device_info = {}
        options: list[SelectOptionDict] = []
        unconfigured_dids: list[str] = []
        for did, info in results:
            label_did = did or "default"
            if info is None:
                # ESP slot didn't answer on our event channel — likely
                # offline, sleeping, or a different component (Sonicare
                # bridge sharing service names but firing a different
                # event). Show but don't allow selecting; the user can
                # see which slot needs attention.
                options.append(SelectOptionDict(
                    value=did,
                    label=f"⚪ {label_did}",
                ))
                continue

            self._esp_device_info[did] = info
            mac = info.get("mac", "").upper()
            has_mac = bool(mac) and mac != "00:00:00:00:00:00"
            label = self._format_bridge_label(label_did, info)

            if has_mac and mac in configured_macs:
                # Already imported into HA — prepend the ✅ marker.
                options.append(SelectOptionDict(value=did, label=f"✅ {label}"))
            else:
                # Either a bonded-but-unimported slot (🔒, ready to import)
                # or an empty Mode-B slot in pair-mode (no icons). Both are
                # selectable.
                unconfigured_dids.append(did)
                options.append(SelectOptionDict(value=did, label=label))

        if not options:
            return self.async_abort(reason="no_devices_found")
        if not unconfigured_dids:
            # Distinguish "all already configured" from "all offline" — both
            # leave unconfigured_dids empty but the user-facing reason is
            # very different. If no slot answered the probe at all, the ESP
            # is unreachable; otherwise the slots are genuinely all bonded.
            any_responding = any(info is not None for _, info in results)
            if not any_responding:
                return self.async_abort(reason="esp_not_reachable")
            return self.async_abort(reason="already_configured")

        # Auto-select only when there is a single device total and it is the
        # free one (Sonicare-aligned). When occupied (✅) or offline (⚪) slots
        # exist alongside the free one, show the picker so the user sees the
        # full bridge state instead of silently skipping past it.
        if len(unconfigured_dids) == 1 and len(options) == 1:
            sole = unconfigured_dids[0]
            self.fetched_esp_bridge_id = sole
            self.fetched_bridge_info = self._esp_device_info.get(sole)
            return await self._esp_bridge_health_check()

        # Pre-select the first free slot so the user doesn't have to deselect
        # an already-configured ✅ entry every time.
        default_value = unconfigured_dids[0]

        # The legend + pair hint live as static, translated text in this
        # step's description / data_description (see translations). They must
        # NOT be built here as dynamic placeholders: config-flow descriptions
        # render in the user's FRONTEND language, which a flow handler cannot
        # read (hass.config.language is the *server* language and can differ),
        # producing a mixed-language dialog. Static json keeps them in sync.
        return self.async_show_form(
            step_id="esp_select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "esp_bridge_id", default=default_value
                    ): SelectSelector(
                        SelectSelectorConfig(options=options)
                    ),
                }
            ),
        )

    @staticmethod
    def _format_bridge_label(bridge_id: str, info: dict[str, str]) -> str:
        """Human-readable label for a BLE device entry in the picker.

        Mirrors the Sonicare picker: an empty Mode-B slot (``pair_capable``)
        shows just its name with no status icons; a slot with an identity
        shows a pairing-lock + connection-dot. The caller prepends ✅ when
        the device is already configured in HA.
        """
        # Prefer the user's YAML friendly_name (always present, even before the
        # bridge connects), then the device's advertised ble_name, then the
        # bridge_id slot label.
        friendly = (info.get("friendly_name") or "").strip()
        ble_name = (info.get("ble_name") or "").strip()
        name = friendly or ble_name or bridge_id or "default"
        if info.get("pair_capable") == "true":
            return name  # empty pair-mode slot — no status icons

        mac = info.get("mac", "")
        connected = info.get("ble_connected") == "true"
        paired = info.get("paired", "")

        icons: list[str] = []
        if paired == "true":
            icons.append("🔒")
        elif paired == "false":
            icons.append("🔓")
        icons.append("🟢" if connected else "⚪")

        body = [name]
        if mac and mac != "00:00:00:00:00:00":
            body.append(mac.upper())
        return f"{' '.join(icons)} {' — '.join(body)}"

    def _esp_target_label(
        self,
        esp_device_name: str | None = None,
        esp_bridge_id: str | None = None,
    ) -> str:
        """Human label for an ESP bridge slot: ``<node> / <slot>``.

        Leads with the ESP node name so a multi-bridge setup shows which
        bridge carries the connection, then the slot's YAML
        ``friendly_name`` (or the ``bridge_id`` when the slot is unnamed).
        Single-bridge nodes with no slot id collapse to just the node.
        Defaults to current flow state; explicit-argument callers skip the
        friendly-name lookup (their bridge info may belong to another slot).
        """
        explicit = esp_device_name is not None or esp_bridge_id is not None
        device = (
            esp_device_name if esp_device_name is not None
            else self.fetched_esp_device_name
        ) or ""
        bridge_id = (
            esp_bridge_id if esp_bridge_id is not None
            else (self.fetched_esp_bridge_id or "")
        )
        friendly = ""
        if not explicit:
            friendly = (
                (self.fetched_bridge_info or {}).get("friendly_name") or ""
            ).strip()
        slot = friendly or bridge_id
        return f"{device} / {slot}" if slot else device

    def _pair_target_placeholders(self) -> dict[str, str]:
        """Placeholders identifying the bridge slot being paired/reset."""
        return {
            "device_name": self.fetched_esp_device_name or "",
            "bridge_id": self.fetched_esp_bridge_id or "",
            "target": self._esp_target_label(),
            # Optional one-shot notice slot (request_pair success alert).
            # Empty by default; every step that renders it must supply it.
            "notice": "",
        }

    async def _route_after_health_check(self) -> ConfigFlowResult:
        """Decide where a probed bridge slot goes next.

        A slot that is already bonded but has no config entry yet (a
        leftover bond, e.g. after removing an entry while the bridge was
        offline) gets a small menu: set it up as-is, or unpair it. Only
        NVS-held identities qualify — a YAML-pinned slot (Mode A, or
        Mode B with an explicit ``mac_address:``) re-bonds automatically,
        so unpairing it would be a confusing no-op. Fresh pairings
        (``_just_paired``) skip straight to the status step.
        """
        info = self.fetched_bridge_info or {}
        if (
            info.get("paired") == "true"
            and info.get("identity_source") == "nvs"
            and not self._just_paired
            and not self._slot_action_chosen
        ):
            return await self.async_step_esp_slot_action()
        return await self.async_step_esp_bridge_status()

    async def async_step_esp_slot_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu for a slot that is bonded but not yet a config entry."""
        return self.async_show_menu(
            step_id="esp_slot_action",
            menu_options=["slot_setup", "slot_unpair"],
            description_placeholders=self._pair_target_placeholders(),
        )

    async def async_step_slot_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu choice: set up the already-bonded shaver (read caps)."""
        self._slot_action_chosen = True
        return await self.async_step_esp_bridge_status()

    async def async_step_slot_unpair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu choice: drop the slot's leftover bond."""
        self._slot_action_chosen = True
        return await self.async_step_reset_bridge()

    async def _esp_bridge_health_check(self) -> ConfigFlowResult:
        """Run bridge health check and proceed to status step.

        ``fetched_bridge_info`` is already populated when the picker or a
        redirect seeded it; otherwise we fetch it live from the bridge.
        """
        # Skip if we already have bridge info from the device selection step
        if self.fetched_bridge_info:
            return await self._route_after_health_check()

        esp_device_name = self.fetched_esp_device_name
        esp_bridge_id = self.fetched_esp_bridge_id

        transport = EspBridgeTransport(
            self.hass, "", esp_device_name, esp_bridge_id
        )
        bridge_info = None
        try:
            await transport.connect()
            bridge_info = await transport.get_bridge_info()
        except TransportError:
            _LOGGER.error("ESP bridge not reachable: %s (bridge_id=%s)", esp_device_name, esp_bridge_id)
            return self.async_show_form(
                step_id="esp_bridge",
                data_schema=vol.Schema({vol.Required("esp_device_name"): str}),
                errors={"base": "cannot_connect"},
            )
        except Exception:
            _LOGGER.exception("Unexpected error checking ESP bridge")
            return self.async_show_form(
                step_id="esp_bridge",
                data_schema=vol.Schema({vol.Required("esp_device_name"): str}),
                errors={"base": "unknown"},
            )
        finally:
            await transport.disconnect()

        self.fetched_bridge_info = bridge_info
        return await self._route_after_health_check()

    async def async_step_esp_bridge_status(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show ESP bridge status before reading shaver capabilities."""
        # A capabilities read is in flight (progress re-invocations land
        # here) — handle it before anything that would probe the bridge.
        if self._esp_caps_task is not None:
            if not self._esp_caps_task.done():
                return self.async_show_progress(
                    step_id="esp_bridge_status",
                    progress_action="esp_reading",
                    progress_task=self._esp_caps_task,
                    description_placeholders=self._pair_target_placeholders(),
                )
            self._esp_caps_result = self._esp_caps_task.result()
            self._esp_caps_task = None
            return self.async_show_progress_done(next_step_id="esp_read_finish")

        if user_input is not None:
            # Mode B detection — bridge supports ble_pair_mode and the user
            # hasn't paired a shaver to it yet. Route to the pair-mode flow
            # instead of attempting a capability fetch (which would fail —
            # there's nothing bonded to read from). YAML-pinned identities
            # (Mode A or Mode B with explicit mac_address:) skip this branch
            # because identity_source == "yaml" guarantees a live target.
            info = self.fetched_bridge_info or {}
            pair_capable = info.get("pair_capable") == "true"
            identity_source = info.get("identity_source", "")
            already_paired = info.get("paired") == "true"
            if pair_capable and identity_source == "none" and not already_paired:
                return await self.async_step_request_pair()

            # "Read capabilities" clicked → run the read as a background task.
            self._esp_caps_task = self.hass.async_create_task(
                self._async_esp_read()
            )
            return self.async_show_progress(
                step_id="esp_bridge_status",
                progress_action="esp_reading",
                progress_task=self._esp_caps_task,
                description_placeholders=self._pair_target_placeholders(),
            )

        # Refresh bridge info to get current BLE connection status
        esp_bridge_id = getattr(self, "fetched_esp_bridge_id", "")
        transport = EspBridgeTransport(
            self.hass,
            "",
            self.fetched_esp_device_name,
            esp_bridge_id,
        )
        try:
            await transport.connect()
            self.fetched_bridge_info = await transport.get_bridge_info()
        except Exception:
            pass
        finally:
            await transport.disconnect()

        # Mode B unpaired: skip the bridge-status form entirely and route
        # straight to request_pair. The status-form's "BLE Disconnected /
        # Paired No" rows look like an error to the user, when actually
        # the bridge is just waiting for ble_pair_mode.
        info = self.fetched_bridge_info or {}
        if (
            info.get("pair_capable") == "true"
            and info.get("identity_source", "") == "none"
            and info.get("paired") != "true"
        ):
            return await self.async_step_request_pair()

        # Format bridge status display
        if info:
            version = info.get("version", "?")
            ble_connected = info.get("ble_connected", "false") == "true"
            paired = info.get("paired", "false") == "true"
            mac = info.get("mac", "")

            ble_status = "✅ Connected" if ble_connected else "❌ Disconnected"
            pair_status = "✅ Yes" if paired else "❌ No"

            rows = [
                f"<tr><td><b>Version</b></td><td>v{version}</td></tr>",
                f"<tr><td><b>BLE</b></td><td>{ble_status}</td></tr>",
                f"<tr><td><b>Paired</b></td><td>{pair_status}</td></tr>",
            ]
            if mac and mac != "00:00:00:00:00:00":
                rows.append(
                    f"<tr><td><b>Shaver MAC</b></td>"
                    f"<td><code>{mac.upper()}</code></td></tr>"
                )

            # Wrap rows in <tbody> so HA's markdown→HTML pass doesn't insert
            # an empty <thead> (causes a blank header row in the rendered UI).
            status_text = f"<table><tbody>{''.join(rows)}</tbody></table>"
        else:
            status_text = (
                "⚠️ Diagnostic details not available. "
                "Consider updating the ESP bridge component."
            )

        # A failed capabilities read surfaces here (errors[] doesn't render
        # on this schema-less step — same quirk as bluetooth_confirm).
        if self._esp_read_error:
            status_text = (
                f'<ha-alert alert-type="error">{self._esp_read_error}</ha-alert>\n\n'
                + status_text
            )
            self._esp_read_error = ""

        # Acknowledge a pairing that wait_pair just completed (one-shot).
        if self._just_paired:
            self._just_paired = False
            status_text = (
                '<ha-alert alert-type="success">Pairing successful — the '
                "bridge is now bonded to your shaver.</ha-alert>\n\n"
                + status_text
            )

        # Determine shaver name for display
        if self.discovery_info:
            shaver_name = self.discovery_info.name or self.discovery_info.address
        elif info.get("ble_name"):
            shaver_name = info["ble_name"]
        elif info.get("mac") and info["mac"] != "00:00:00:00:00:00":
            shaver_name = f"Philips device ({info['mac']})"
        else:
            shaver_name = "Unknown device"

        # Pick the matching translation variant: the "already connected" hint
        # when the bridge holds a live BLE link, the "turn it on" hint
        # otherwise. Both submit to async_step_esp_bridge_status.
        ble_connected = info.get("ble_connected") == "true"
        step_id = (
            "esp_bridge_status_connected" if ble_connected else "esp_bridge_status"
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_name": self.fetched_esp_device_name,
                "shaver_name": shaver_name,
                "target": self._esp_target_label(),
                "status": status_text,
            },
        )

    async def _async_esp_read(self) -> dict[str, Any]:
        """Read capabilities via the ESP bridge (runs as a progress task)."""
        esp_device_name = self.fetched_esp_device_name
        try:
            caps = await self._async_fetch_capabilities_esp(
                esp_device_name, esp_device_name,
                getattr(self, "fetched_esp_bridge_id", ""),
            )
            return {"ok": True, "caps": caps}
        except CannotConnectException:
            _LOGGER.error(
                "ESP bridge: unable to read shaver capabilities via %s",
                esp_device_name,
            )
            return {"ok": False, "error": "cannot_connect"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error reading shaver capabilities")
            return {"ok": False, "error": "unknown"}

    async def async_step_esp_read_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Process the capabilities read captured by esp_bridge_status."""
        result = self._esp_caps_result or {}
        self._esp_caps_result = None

        if not result.get("ok"):
            if result.get("error") == "cannot_connect":
                self._esp_read_error = (
                    "Couldn't read the shaver over the bridge. Make sure "
                    "it's switched on and the bridge is online, then try "
                    "again."
                )
            else:
                self._esp_read_error = (
                    "Something went wrong reading the shaver. Check the "
                    "logs (Settings → System → Logs) and try again."
                )
            return await self.async_step_esp_bridge_status()

        capabilities = result["caps"]
        esp_device_name = self.fetched_esp_device_name

        shaver_mac = capabilities.get("shaver_mac")
        if shaver_mac:
            await self.async_set_unique_id(
                shaver_mac.upper(), raise_on_progress=False
            )
        else:
            await self.async_set_unique_id(f"esp_{esp_device_name}")
        self._abort_if_already_configured()

        # Add pairing status from bridge info for the BLE-Security row.
        paired_str = (self.fetched_bridge_info or {}).get("paired", "")
        if paired_str == "true":
            capabilities["pairing"] = "bonded"
        elif paired_str == "false":
            capabilities["pairing"] = "open_gatt"

        self.fetched_data = capabilities
        # Use bridge version from status step
        if self.fetched_bridge_info:
            self.fetched_data["bridge_version"] = self.fetched_bridge_info.get(
                "version"
            )
        self.fetched_address = shaver_mac
        # Use model number as display name if available
        model = capabilities.get("model_number")
        self.fetched_name = model if model else esp_device_name
        self.fetched_transport_type = TRANSPORT_ESP_BRIDGE

        return await self.async_step_show_capabilities()

    async def async_step_esp_bridge_status_connected(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Alias step rendered when the bridge is already BLE-connected.

        HA routes submissions to async_step_<step_id>; the translations are
        split across two step IDs (different action hints) but the
        implementation is shared with async_step_esp_bridge_status.
        """
        return await self.async_step_esp_bridge_status(user_input)

    async def async_step_request_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mode B: confirm before arming ble_pair_mode on the bridge."""
        if user_input is not None:
            return await self.async_step_wait_pair()

        placeholders = self._pair_target_placeholders()
        # Acknowledge a bond that reset_bridge just cleared (one-shot), so
        # the jump from "Reset bridge bond" to pair-mode isn't silent.
        if self._just_unpaired:
            self._just_unpaired = False
            placeholders["notice"] = (
                '<ha-alert alert-type="success">Bond removed — the slot is '
                "free. Switch on the shaver you want to bond, then start "
                "pairing.</ha-alert>\n\n"
            )
        return self.async_show_form(
            step_id="request_pair",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
        )

    async def async_step_wait_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Arm ble_pair_mode and wait for the bond, showing live progress.

        Two ``async_show_progress`` phases so the dialog tells the user
        what is happening instead of freezing on a blank spinner for up
        to a minute: first *arming* pair-mode on the bridge, then
        *scanning/bonding*. Each phase runs as a background task; when it
        finishes HA re-invokes this step. The outcome lands in
        ``_pair_result`` and ``async_step_pair_finish`` renders it.
        """
        # Phase 1 — arm pair-mode on the bridge.
        if (
            self._pair_arm_task is None
            and self._pair_scan_task is None
            and self._pair_result is None
        ):
            self._pair_arm_task = self.hass.async_create_task(
                self._async_arm_pair_mode()
            )

        if self._pair_arm_task is not None:
            if not self._pair_arm_task.done():
                return self.async_show_progress(
                    step_id="wait_pair",
                    progress_action="pair_arming",
                    progress_task=self._pair_arm_task,
                    description_placeholders=self._pair_target_placeholders(),
                )
            armed = self._pair_arm_task.result()
            self._pair_arm_task = None
            if not armed:
                self._pair_result = {"error": "service_call_failed"}
                return self.async_show_progress_done(next_step_id="pair_finish")
            # Arming succeeded — kick off the scan/bond phase.
            self._pair_scan_task = self.hass.async_create_task(
                self._async_scan_and_bond()
            )

        # Phase 2 — wait for the bridge to bond (or time out / fail).
        if self._pair_scan_task is not None:
            if not self._pair_scan_task.done():
                return self.async_show_progress(
                    step_id="wait_pair",
                    progress_action="pair_scanning",
                    progress_task=self._pair_scan_task,
                    description_placeholders=self._pair_target_placeholders(),
                )
            self._pair_result = self._pair_scan_task.result()
            self._pair_scan_task = None

        return self.async_show_progress_done(next_step_id="pair_finish")

    async def _async_arm_pair_mode(self) -> bool:
        """Register the status listener and arm pair-mode on the bridge.

        Returns True when the arm service call succeeded. The listener is
        registered *before* the service call so a fast pair_complete
        can't slip through; ``async_step_pair_finish`` tears it down.
        """
        bridge_id = self.fetched_esp_bridge_id or ""
        self._pair_future = self.hass.loop.create_future()

        @callback
        def _on_status(event: Event) -> None:
            # Filter events by bridge_id so multi-bridge ESPs don't
            # cross-talk. ShaverBridge::fire_event auto-injects bridge_id,
            # so the field is always present (empty for single-bridge
            # YAMLs); compared case-insensitively (HA lowercases service
            # names).
            if event.data.get("bridge_id", "").lower() != bridge_id.lower():
                return
            if event.data.get("status") not in (
                "pair_complete", "pair_timeout", "pair_failed"
            ):
                return
            if self._pair_future is not None and not self._pair_future.done():
                self._pair_future.set_result(dict(event.data))

        self._pair_unsub = self.hass.bus.async_listen(
            "esphome.philips_shaver_ble_status", _on_status
        )

        # Service name with bridge_id suffix (matches ShaverBridge::svc_name_)
        svc = f"{self.fetched_esp_device_name}_ble_pair_mode"
        if bridge_id:
            svc = f"{svc}_{bridge_id}"
        self._pair_svc_name = svc
        try:
            await self.hass.services.async_call(
                "esphome",
                svc,
                {"enabled": True, "timeout_s": "60"},
                blocking=True,
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("ble_pair_mode service call failed: %s", err)
            return False
        return True

    async def _async_scan_and_bond(self) -> dict[str, str]:
        """Wait for pair_complete / pair_timeout / pair_failed.

        Ticks the determinate progress bar along the bridge's 60 s pair
        window while waiting — the only feedback the user gets during a
        wait this long. ``shield`` keeps the per-tick ``wait_for`` from
        cancelling the shared future.
        """
        if self._pair_future is None:  # arming always sets it; defensive
            return {"status": "pair_timeout"}
        timeout_s = 60
        loop = self.hass.loop
        start = loop.time()
        # 65 s margin = 60 s pair window + 5 s grace for the pair_timeout
        # event to land. The bridge fires pair_timeout/pair_complete itself
        # so the deadline is just a safety net for missed events.
        deadline = start + timeout_s + 5
        while True:
            now = loop.time()
            if now >= deadline:
                _LOGGER.warning(
                    "Pair-mode wait elapsed without pair_complete/"
                    "pair_timeout event from bridge"
                )
                return {"status": "pair_timeout"}
            self._bump_progress((now - start) / timeout_s)
            try:
                return await asyncio.wait_for(
                    asyncio.shield(self._pair_future),
                    timeout=min(2.0, deadline - now),
                )
            except asyncio.TimeoutError:
                continue

    async def async_step_pair_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Render the outcome captured by the wait_pair progress phases."""
        result = self._pair_result or {}
        self._pair_result = None

        # Tear down the status listener and, unless we cleanly bonded,
        # tell the bridge to stand down so a stray shaver in range during
        # its leftover window isn't auto-bonded (best-effort — the bridge
        # has its own timer).
        if self._pair_unsub is not None:
            self._pair_unsub()
            self._pair_unsub = None
        clean_complete = result.get("status") == "pair_complete"
        if not clean_complete and self._pair_svc_name:
            try:
                await self.hass.services.async_call(
                    "esphome", self._pair_svc_name,
                    {"enabled": False, "timeout_s": "0"},
                    blocking=False,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Best-effort pair-mode cancel failed (ignoring)")
        self._pair_future = None
        self._pair_svc_name = ""

        if result.get("error"):
            return self.async_show_form(
                step_id="request_pair",
                data_schema=vol.Schema({}),
                errors={"base": result["error"]},
                description_placeholders=self._pair_target_placeholders(),
            )

        result_status = result.get("status")
        if result_status in ("pair_timeout", "pair_failed"):
            # Map the bridge's status to a translation key. pair_failed with
            # reason=auth_max_failures means the shaver retained its half
            # of the bond — user has to clear BT on the shaver before
            # retrying. Generic pair_timeout just means no shaver showed
            # up (or showed up too late).
            if (
                result_status == "pair_failed"
                and result.get("reason") == "auth_max_failures"
            ):
                error_key = "pair_failed_stale_bond"
            else:
                error_key = "pair_timeout"
            return self.async_show_form(
                step_id="request_pair",
                data_schema=vol.Schema({}),
                errors={"base": error_key},
                description_placeholders=self._pair_target_placeholders(),
            )

        # pair_complete — bond established. identity_address comes from
        # the bridge's pair_complete event payload (Coord fills it from
        # parent_->get_remote_bda after AUTH_CMPL.success). Clear the
        # cached bridge info so the status step refetches the
        # freshly-bound state; the success banner acknowledges the bond
        # and the user finishes with "Read capabilities" (now a progress
        # task) from there.
        identity_address = (
            result.get("identity_address") or result.get("mac") or ""
        )
        self.fetched_bridge_info = None
        self._just_paired = True
        if identity_address:
            self.fetched_address = identity_address
            await self.async_set_unique_id(
                identity_address.upper(), raise_on_progress=False
            )
            self._abort_if_already_configured()
        return await self._esp_bridge_health_check()

    async def async_step_reset_bridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm + execute unpair on a bonded Mode B slot.

        The unpair (service call + waiting for the bridge's ``unpaired``
        confirmation, ~4 s) runs as a background task behind an
        ``async_show_progress`` spinner; ``reset_finish`` renders the
        outcome.
        """
        # An unpair is in flight (progress re-invocations land here).
        if self._unpair_task is not None:
            if not self._unpair_task.done():
                return self.async_show_progress(
                    step_id="reset_bridge",
                    progress_action="unpairing",
                    progress_task=self._unpair_task,
                    description_placeholders=self._reset_bridge_placeholders(),
                )
            self._unpair_outcome = self._unpair_task.result()
            self._unpair_task = None
            return self.async_show_progress_done(next_step_id="reset_finish")

        if user_input is not None:
            self._unpair_task = self.hass.async_create_task(
                async_unpair_bridge_slot(
                    self.hass,
                    self.fetched_esp_device_name or "",
                    self.fetched_esp_bridge_id or "",
                )
            )
            return self.async_show_progress(
                step_id="reset_bridge",
                progress_action="unpairing",
                progress_task=self._unpair_task,
                description_placeholders=self._reset_bridge_placeholders(),
            )

        return self.async_show_form(
            step_id="reset_bridge",
            data_schema=vol.Schema({}),
            description_placeholders=self._reset_bridge_placeholders(),
        )

    async def async_step_reset_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Render the unpair outcome captured by reset_bridge."""
        outcome = self._unpair_outcome
        self._unpair_outcome = ""

        # Only proceed when the bridge confirmed the bond is gone. A silent
        # failure (call returned but no `unpaired` event) would otherwise
        # drop the user back onto the still-bonded status screen unexplained.
        if outcome == UNPAIR_OK:
            # pair_capable again — refetch info, then re-pair. Clearing
            # fetched_bridge_info forces a fresh ble_get_info so
            # paired/identity reflect the just-cleared slot;
            # _just_unpaired drives the request_pair success notice.
            self.fetched_bridge_info = None
            self._just_unpaired = True
            return await self._esp_bridge_health_check()

        _LOGGER.error(
            "Unpair on %s did not succeed (%s)",
            self.fetched_esp_device_name, outcome,
        )
        if outcome in (UNPAIR_FAILED, UNPAIR_UNAVAILABLE):
            msg = (
                "Couldn't reach the ESP bridge to clear the bond. Make "
                "sure it's online and powered, then try again."
            )
        else:  # UNPAIR_UNCONFIRMED
            msg = (
                "Couldn't confirm the bridge cleared the bond — it may "
                "need a reboot. Make sure it's online, then try again."
            )
        return self.async_show_form(
            step_id="reset_bridge",
            data_schema=vol.Schema({}),
            description_placeholders=self._reset_bridge_placeholders(msg),
        )

    def _reset_bridge_placeholders(self, error: str = "") -> dict[str, str]:
        """Placeholders for the reset_bridge step.

        ``errors["base"]`` does not render on this schema-less confirmation
        step (same as bluetooth_confirm), so a failure is surfaced by
        injecting an ``<ha-alert>`` into the ``{error}`` placeholder.
        """
        info = self.fetched_bridge_info or {}
        placeholders = self._pair_target_placeholders()
        placeholders["identity_address"] = (
            info.get("identity_address") or info.get("mac", "")
        ).upper()
        placeholders["error"] = (
            f'<ha-alert alert-type="error">{error}</ha-alert>\n\n'
            if error else ""
        )
        return placeholders

    async def _route_to_pairing(self) -> ConfigFlowResult:
        """Route to D-Bus pairing if available, otherwise show script instructions."""
        from .dbus_pairing import is_dbus_available

        if is_dbus_available():
            return await self.async_step_pair()
        return await self.async_step_not_paired()

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair the device via D-Bus and retry capabilities fetch.

        The pairing + follow-up probe run as one background task behind an
        ``async_show_progress`` spinner; ``ble_probe_finish`` routes the
        boxed outcome back here (via ``_pair_error``) or onwards.
        """
        # Progress re-invocations of a running pair+probe land here.
        if (progress := self._ble_probe_progress("pair", action="pairing")) is not None:
            return progress

        errors: dict[str, str] = {}
        # One-shot outcome from ble_probe_finish.
        if self._pair_error:
            errors["base"] = self._pair_error
            self._pair_error = ""

        if user_input is not None:
            address = self._pair_address or ""
            self._ble_probe_origin = "pair"
            self._ble_probe_address = address
            self._ble_probe_task = self.hass.async_create_task(
                self._async_pair_and_probe(address)
            )
            return self.async_show_progress(
                step_id="pair",
                progress_action="pairing",
                progress_task=self._ble_probe_task,
                description_placeholders=self._ble_probe_placeholders(),
            )

        name = ""
        if self.discovery_info:
            name = self.discovery_info.name or self.discovery_info.address
        elif self._pair_address:
            name = self._pair_address

        return self.async_show_form(
            step_id="pair",
            data_schema=vol.Schema({}),
            description_placeholders={"name": name},
            errors=errors,
        )

    async def _async_pair_and_probe(self, address: str) -> dict[str, Any]:
        """D-Bus pair + trust, then the capabilities probe (progress task)."""
        from .dbus_pairing import async_pair_and_trust, PairingError

        try:
            self._bump_progress(0.02)
            await async_pair_and_trust(address)
            _LOGGER.info("D-Bus pairing successful for %s", address)
            # Brief settle time for BlueZ key distribution
            await asyncio.sleep(2)
        except PairingError as err:
            _LOGGER.error("D-Bus pairing failed for %s: %s", address, err)
            return {"ok": False, "error": "pairing_failed"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during pairing")
            return {"ok": False, "error": "pairing_failed"}

        return await self._async_ble_probe(address)

    async def async_step_not_paired(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show pairing instructions when the device is not paired."""
        if user_input is not None:
            # Retry: the discovery path re-enters the confirm submit
            # (D-Bus pre-check + probe); the manual path re-probes the
            # known address directly — just re-rendering the empty
            # address form would silently drop the retry.
            if self.discovery_info:
                return await self.async_step_bluetooth_confirm(user_input)
            if self._pair_address:
                return self._start_ble_probe("user_bleak", self._pair_address)
            return await self.async_step_user_bleak()

        # Build description placeholders based on environment
        pair_cmd = "bash /config/custom_components/philips_shaver/scripts/pair.sh"
        if _is_hassio(self.hass):
            pairing_help = (
                "Open the **Terminal & SSH** addon "
                "([install it first](/hassio/addon/core_ssh/info) if needed) "
                "and run the pairing script:"
            )
        else:
            pairing_help = (
                "Open a terminal on the machine running Home Assistant "
                "and run the pairing script:"
            )

        name = ""
        if self.discovery_info:
            name = self.discovery_info.name or self.discovery_info.address
        elif self.fetched_address:
            name = self.fetched_address

        return self.async_show_form(
            step_id="not_paired",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": name,
                "pairing_help": pairing_help,
                "pair_cmd": pair_cmd,
            },
        )

    async def async_step_not_paired_proxy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Proxy-carried probe hit a missing bond — a dead end by hardware.

        Philips shavers pair via LE Secure Connections, which a standard
        Bluetooth proxy cannot complete; host-side pairing tools don't
        touch a proxy-carried link either. The dialog explains the two
        working paths (local adapter, ESP32 bridge). Retry re-probes:
        habluetooth routes each connect by signal strength, so if a local
        adapter now carries it the normal pairing machinery applies again.
        """
        if user_input is not None:
            if self.discovery_info:
                return await self.async_step_bluetooth_confirm(user_input)
            return self._start_ble_probe(
                "user_bleak", self._pair_address or ""
            )

        # The dead-end itself renders as a red <ha-alert> so it can't be
        # skimmed past; injected as a placeholder because hassfest rejects
        # HTML in static translation strings. Markdown isn't parsed inside
        # the HTML block, so emphasis uses <b>.
        proxy_name = self._probe_proxy_name or "unknown"
        alert = (
            '<ha-alert alert-type="error">This connection runs through the '
            f"standard Bluetooth proxy <b>{proxy_name}</b>. Philips shavers "
            "pair via LE Secure Connections, which a standard Bluetooth "
            "proxy cannot complete — pairing over this path will not "
            "succeed, and pairing tools on the Home Assistant host have no "
            "effect on it.</ha-alert>\n\n"
        )
        return self.async_show_form(
            step_id="not_paired_proxy",
            data_schema=vol.Schema({}),
            description_placeholders={
                "address": self._pair_address or "",
                "proxy_name": proxy_name,
                "alert": alert,
            },
        )

    def _build_default_name(self) -> str:
        """Default device name for the new entry.

        Priority: ESP ``friendly_name`` (Phase 2, when the bridge emits it)
        wins verbatim; otherwise the model with a bridge_id / MAC-suffix
        disambiguator so multi-device households stay distinguishable.
        """
        data = self.fetched_data or {}
        yaml_name = (data.get("friendly_name") or "").strip()
        if yaml_name:
            return yaml_name
        model = (data.get("model_number") or "").strip()
        if (
            self.fetched_transport_type == TRANSPORT_ESP_BRIDGE
            and self.fetched_esp_bridge_id
        ):
            suffix = self.fetched_esp_bridge_id
        elif self.fetched_address:
            suffix = self.fetched_address.replace(":", "")[-4:].upper()
        else:
            suffix = ""
        base = model or "Philips Shaver"
        return f"{base} ({suffix})" if suffix else base

    async def async_step_show_capabilities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show detected services and create entry."""

        if self.fetched_data is None:
            return await self.async_step_user()

        # Surface ESP per-slot friendly_name / area (from ble_get_info) into
        # fetched_data so the default name and area assignment can use them.
        # Empty on older bridges that don't emit these fields.
        if self.fetched_bridge_info:
            for key in ("friendly_name", "area"):
                val = (self.fetched_bridge_info.get(key) or "").strip()
                if val and not self.fetched_data.get(key):
                    self.fetched_data[key] = val

        default_name = self._build_default_name()

        if user_input is not None:
            device_name = (
                user_input.get(CONF_DEVICE_NAME) or ""
            ).strip() or default_name

            entry_data: dict[str, Any] = {
                CONF_CAPABILITIES: self.fetched_data.get("capabilities", 0),
                CONF_SERVICES: self.fetched_data.get("services", []),
                CONF_DEVICE_NAME: device_name,
            }
            device_type = self.fetched_data.get("device_type")
            if device_type:
                entry_data[CONF_DEVICE_TYPE] = device_type
            area = (self.fetched_data.get("area") or "").strip()
            if area:
                entry_data[CONF_AREA] = area

            if self.fetched_transport_type == TRANSPORT_ESP_BRIDGE:
                entry_data[CONF_TRANSPORT_TYPE] = TRANSPORT_ESP_BRIDGE
                entry_data[CONF_ESP_DEVICE_NAME] = self.fetched_esp_device_name
                esp_bridge_id = getattr(self, "fetched_esp_bridge_id", "")
                if esp_bridge_id:
                    entry_data[CONF_ESP_BRIDGE_ID] = esp_bridge_id
                if self.fetched_address:
                    entry_data[CONF_ADDRESS] = self.fetched_address
            else:
                entry_data[CONF_ADDRESS] = self.fetched_address

            return self.async_create_entry(
                title=f"Philips Shaver ({device_name})",
                data=entry_data,
            )

        device_type = self.fetched_data.get("device_type", "")
        device_info_text = self._get_device_info_text(
            self.fetched_data, self.fetched_address
        )

        cap_val = self.fetched_data.get("capabilities", 0)
        groomer_cap = self.fetched_data.get("groomer_capabilities")
        caps_services_text = self._get_capabilities_services_text(
            cap_val,
            groomer_cap,
            self.fetched_data.get("services", []),
            device_type,
        )

        # Connection info suffix — show adapter / bridge actually used
        if self.fetched_transport_type == TRANSPORT_ESP_BRIDGE:
            path = self._esp_target_label()
        else:
            path = self.fetched_data.get("connection_path")
        connection_status = self._get_connection_status_text(
            self.fetched_transport_type,
            path,
            via_proxy=bool(self._probe_via_proxy),
        )

        return self.async_show_form(
            step_id="show_capabilities",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_NAME, default=default_name): str,
                }
            ),
            description_placeholders={
                "name": str(self.fetched_name),
                "connection_status": connection_status,
                "device_info": device_info_text,
                "caps_services": caps_services_text,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> PhilipsShaverOptionsFlow:
        """Create the options flow."""
        return PhilipsShaverOptionsFlow()

    CAPABILITY_FLAGS = [
        (0, "Motion Sensing"),
        (1, "Brush Programs"),
        (2, "Motion Speed Sensing"),
        (3, "Pressure Feedback"),
        (4, "Unit Cleaning"),
        (5, "Cleaning Mode"),
        (6, "Light Ring"),
    ]

    GROOMER_CAPABILITY_FLAGS = [
        (0, "Speed Guidance"),
    ]

    @staticmethod
    def _get_connection_status_text(
        transport_type: str | None, path: str | None, *, via_proxy: bool = False
    ) -> str:
        """Connection status line shown above the device info.

        Leads with the transport *class* (``ESP32 Bridge`` / ``Bluetooth
        proxy`` / ``Direct Bluetooth``) so it reads the same as the other
        "via" dialogs, with the adapter/bridge label appended in
        parentheses as a disambiguator. ``via_proxy`` marks a
        TRANSPORT_BLEAK probe that rode a remote scanner — labelling that
        "Direct Bluetooth" would hide the very path distinction the
        pairing dialogs are keyed on.

        Rendered as a success <ha-alert> (same style as the pairing
        confirmation); ha-markdown does not parse markdown inside the
        HTML block, so emphasis uses <b>. The step is only reachable
        after a successful capability read, so there is no disconnected
        variant.
        """
        if transport_type == TRANSPORT_ESP_BRIDGE:
            transport_label = "ESP32 Bridge"
        elif via_proxy:
            transport_label = "Bluetooth proxy"
        else:
            transport_label = "Direct Bluetooth"
        suffix = f" ({path})" if path else ""
        return (
            '<ha-alert alert-type="success">Connected via '
            f"<b>{transport_label}</b>{suffix}.</ha-alert>"
        )

    @staticmethod
    def _get_device_info_text(
        data: dict[str, Any], address: str | None = None
    ) -> str:
        """Format the key device facts as an HTML table (no header)."""
        rows: list[str] = []
        model = data.get("model_number")
        if model:
            rows.append(f"<tr><td><b>Model</b></td><td>{model}</td></tr>")
        # Device class. The raw device_type characteristic returns cryptic
        # codes ("m" for OneBlade) or just the model number for shavers, so
        # never show it verbatim. Surface a friendly "OneBlade" label when the
        # Smart Groomer service (or device_type text) marks this handle as a
        # OneBlade; for regular shavers the Model row already says everything.
        services = {s.lower() for s in data.get("services", [])}
        is_oneblade = (
            SVC_GROOMER.lower() in services
            or "oneblade" in (data.get("device_type") or "").lower()
        )
        if is_oneblade:
            rows.append("<tr><td><b>Type</b></td><td>OneBlade</td></tr>")
        if firmware := data.get("firmware"):
            rows.append(f"<tr><td><b>Firmware</b></td><td>{firmware}</td></tr>")
        if (battery := data.get("battery")) is not None:
            rows.append(f"<tr><td><b>Battery</b></td><td>{battery}%</td></tr>")
        mac = data.get("shaver_mac") or address
        if mac:
            rows.append(
                f"<tr><td><b>MAC</b></td><td><code>{mac.upper()}</code></td></tr>"
            )
        pairing = data.get("pairing")
        if pairing == "bonded":
            rows.append(
                "<tr><td><b>BLE Security</b></td><td>Bonded (encrypted)</td></tr>"
            )
        elif pairing == "open_gatt":
            rows.append(
                "<tr><td><b>BLE Security</b></td><td>Unpaired (no encryption)</td></tr>"
            )
        if not rows:
            return ""
        # Trailing <br/> separates this table from the capabilities table that
        # follows. It lives in this runtime-generated value rather than the
        # translation string because hassfest rejects HTML tags in static
        # translation values (it does not inspect placeholder content).
        return f"<table><tbody>{''.join(rows)}</tbody></table><br/>"

    @staticmethod
    def _capability_items(cap_val: int, groomer_cap: int | None = None) -> list[str]:
        """Hardware-capability flags as a list of "icon name" strings."""
        items: list[str] = []
        # Standard shaver capabilities (0x0302)
        if cap_val > 0:
            for bit, name in PhilipsShaverConfigFlow.CAPABILITY_FLAGS:
                icon = "✅" if cap_val & (1 << bit) else "⬜"
                items.append(f"{icon} {name}")
        # OneBlade groomer capabilities (0x0702)
        if groomer_cap is not None:
            for bit, name in PhilipsShaverConfigFlow.GROOMER_CAPABILITY_FLAGS:
                icon = "✅" if groomer_cap & (1 << bit) else "⬜"
                items.append(f"{icon} {name}")
        return items

    def _get_capabilities_services_text(
        self,
        cap_val: int,
        groomer_cap: int | None,
        fetched_uuids: list[str],
        device_type: str,
    ) -> str:
        """Hardware capabilities (left) and detected services (right) side by
        side in one 2-column table, plus the family-aware footer explaining
        any expectedly-absent service."""
        cap_items = self._capability_items(cap_val, groomer_cap)
        if not cap_items:
            cap_items = ["⬜ Basic monitoring only"]
        svc_items, notes = self._service_status_items(fetched_uuids, device_type)

        rows = [
            "<tr><td><b>Hardware Capabilities</b></td>"
            "<td><b>Detected Services</b></td></tr>"
        ]
        for i in range(max(len(cap_items), len(svc_items))):
            left = cap_items[i] if i < len(cap_items) else ""
            right = svc_items[i] if i < len(svc_items) else ""
            rows.append(f"<tr><td>{left}</td><td>{right}</td></tr>")

        table = f"<table><tbody>{''.join(rows)}</tbody></table>"
        if notes:
            table += "\n\n" + "\n\n".join(notes)
        return table

    # Standard BLE services present on every device — hide from display
    _STANDARD_BLE_SERVICES = {
        "00001800-0000-1000-8000-00805f9b34fb",  # Generic Access
        "00001801-0000-1000-8000-00805f9b34fb",  # Generic Attribute
    }

    SERVICE_NAMES: dict[str, str] = {
        SVC_BATTERY.lower(): "Battery",
        SVC_DEVICE_INFO.lower(): "Device Information",
        SVC_PLATFORM.lower(): "Platform",
        SVC_HISTORY.lower(): "History",
        SVC_CONTROL.lower(): "Control",
        SVC_SERIAL.lower(): "Serial / Diagnostic",
        SVC_GROOMER.lower(): "Smart Groomer",
        "e50ba3c0-af04-4564-92ad-fef019489de6": "ByteStreaming",
    }

    @staticmethod
    def _detect_family(fetched_lower: set[str], device_type: str) -> str:
        """Return device family: 'oneblade' or 'shaver'.

        The Smart Groomer service (0x0700) is the OneBlade marker — analogous
        to how the Sonicare integration keys its newer-protocol family off the
        transport service rather than a model string. Fall back to the
        device-type text ("OneBlade" vs a model number like "XP9201") when
        the service set is ambiguous.
        """
        if SVC_GROOMER.lower() in fetched_lower:
            return "oneblade"
        if "oneblade" in (device_type or "").lower():
            return "oneblade"
        return "shaver"

    @staticmethod
    def _missing_reason(uuid_lower: str, family: str) -> str:
        """Why a service is absent on this family, if we can explain it."""
        if family == "oneblade" and uuid_lower in (
            SVC_CONTROL.lower(),
            SVC_SERIAL.lower(),
        ):
            return "not on oneblade"
        if family == "shaver" and uuid_lower == SVC_GROOMER.lower():
            return "groomer oneblade only"
        return ""

    def _service_status_items(
        self, fetched_uuids: list[str], device_type: str = ""
    ) -> tuple[list[str], list[str]]:
        """Detected services as "icon name" strings, plus family-aware footer
        notes.

        Returns ``(items, notes)``. Services absent for the detected family
        (OneBlade vs shaver) are shown ❌; ``notes`` explains that their
        absence is expected — not a fault — so users don't report "missing
        service" issues for hardware that never had it.
        """
        fetched_lower = {s.lower() for s in fetched_uuids} - self._STANDARD_BLE_SERVICES
        known_lower = {s.lower() for s in PHILIPS_SERVICE_UUIDS}
        # Only assert ✅/❌ for services whose presence we can actually
        # determine: the ESP bridge path probes one char per service and can
        # only see the services in SERVICE_PROBE_CHARS. SVC_SERIAL (0x0600)
        # has no readable characteristic, so it is never probeable via ESP —
        # listing it as expected would show a false ❌ on bridge setups even
        # though the device has it. The Direct-BLE path enumerates the full
        # service list, so a present-but-unprobed service (e.g. Serial) still
        # shows ✅ via the "extra services" loop below.
        expected = {s.lower() for s in self.SERVICE_PROBE_CHARS}

        family = self._detect_family(fetched_lower, device_type)

        found: list[str] = []
        missing: list[str] = []
        unknown: list[str] = []
        used_reasons: set[str] = set()

        for uuid in sorted(expected):
            name = self.SERVICE_NAMES.get(uuid, "Unknown")
            if uuid in fetched_lower:
                found.append(f"✅ {name}")
            else:
                reason = self._missing_reason(uuid, family)
                if reason:
                    used_reasons.add(reason)
                missing.append(f"❌ {name}")

        for uuid in sorted(fetched_lower - expected):
            name = self.SERVICE_NAMES.get(uuid, "Unknown")
            if uuid in known_lower:
                found.append(f"✅ {name}")
            else:
                unknown.append(f"❔ {name}")

        items = found + missing + unknown

        footer_for = {
            "not on oneblade":
                "❌ Control and Serial/Diagnostic services are not present on "
                "OneBlade models — this is expected.",
            "groomer oneblade only":
                "❌ The Smart Groomer service is only available on OneBlade / "
                "QP models.",
        }
        notes = [footer_for[r] for r in sorted(used_reasons) if r in footer_for]
        return items, notes
