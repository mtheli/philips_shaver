from __future__ import annotations

from typing import Any

import asyncio
import time
import voluptuous as vol
import logging

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import Event, callback
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_last_service_info,
)
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
from .transport import EspBridgeTransport, describe_connection_path
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
    fetched_bridge_info: dict[str, str] | None = None
    _pair_address: str | None = None  # MAC for D-Bus pairing step

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
        age = None if last is None else (time.monotonic() - last.time)
        if last is None or age > _STALE_ADV_MAX_SECONDS:
            _LOGGER.info(
                "%s: no recent connectable advertisement (%s) — device asleep",
                address,
                "never seen" if last is None else f"{age:.0f}s ago",
            )
            raise DeviceAsleepException

        device = async_ble_device_from_address(self.hass, address)
        if not device:
            raise DeviceNotFoundException("BLE device not found")

        client: BleakClient | None = None
        try:
            client = await establish_connection(
                BleakClient, device, "philips_shaver", timeout=15
            )

            if not client.is_connected:
                raise CannotConnectException("BLE connection failed")
            _LOGGER.info("Connected to %s, address=%s", device.name, address)

            capabilities["connection_path"] = describe_connection_path(
                self.hass, client, device
            )
            _LOGGER.info(
                "%s: capabilities probe connected via %s",
                address,
                capabilities["connection_path"],
            )

            _LOGGER.info("Reading services from %s...", address)
            services = client.services
            capabilities["services"] = [str(s.uuid) for s in services]

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

        unconfigured = False
        found_any = False
        for did in bridge_ids:
            svc_name = f"{device_name}_ble_get_info"
            if did:
                svc_name += f"_{did}"
            info_future: asyncio.Future[dict[str, str]] = self.hass.loop.create_future()

            @callback
            def _on_status(event: Event, _did=did) -> None:
                if (event.data.get("status") == "info"
                        # HA lowercases service names, so an uppercase bridge_id
                        # (e.g. a model number) yields a lowercase suffix while
                        # the event echoes the original case — compare lowercased.
                        and event.data.get("bridge_id", "").lower() == _did.lower()
                        and not info_future.done()):
                    info_future.set_result(dict(event.data))

            unsub = self.hass.bus.async_listen(
                "esphome.philips_shaver_ble_status", _on_status
            )
            try:
                await self.hass.services.async_call(
                    "esphome", svc_name, {}, blocking=True
                )
                info = await asyncio.wait_for(info_future, timeout=3.0)
                found_any = True
                mac = info.get("mac", "")
                if not mac or mac.upper() not in configured_macs:
                    unconfigured = True
                    break
            except (asyncio.TimeoutError, Exception):
                pass  # Not our bridge type or not responding — skip
            finally:
                unsub()

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
        self._abort_if_unique_id_configured()

        self.discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery and fetch capabilities."""
        # On first display, check if an ESP bridge is already connected
        # to this shaver — redirect to ESP flow if so.
        if user_input is None:
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
                return await self.async_step_esp_bridge_status()

        return await self._async_bluetooth_confirm(user_input, "bluetooth_confirm")

    async def _find_esp_bridge_for_mac(self, mac: str) -> dict | None:
        """Check if any ESP bridge is connected to the given MAC."""
        esphome_entries = self.hass.config_entries.async_entries("esphome")
        for entry in esphome_entries:
            # Disabled bridges cannot hold a connection — probing them only
            # burns the 10 s bridge timeout (their stale services may still
            # be registered, so the service-based detection alone would
            # wrongly pick them up).
            if entry.disabled_by:
                _LOGGER.debug(
                    "%s: bridge check — skipping disabled ESPHome entry '%s'",
                    mac, entry.title,
                )
                continue
            # Same for bridges whose ESPHome API link is down: the probe
            # runs over that link, so it can only time out. runtime_data is
            # ESPHome's RuntimeEntryData; fall back to probing if the
            # attribute layout ever changes.
            runtime = getattr(entry, "runtime_data", None)
            if runtime is not None and getattr(runtime, "available", True) is False:
                _LOGGER.debug(
                    "%s: bridge check — skipping offline ESPHome entry '%s'",
                    mac, entry.title,
                )
                continue
            device_name = entry.data.get("device_name")
            if not device_name:
                continue
            esp_name = device_name.replace("-", "_")
            device_ids = self._detect_esp_bridge_ids(esp_name)
            for did in device_ids:
                transport = EspBridgeTransport(
                    self.hass, mac, esp_name, did
                )
                try:
                    await transport.connect()
                    info = await transport.get_bridge_info()
                    if info and info.get("mac", "").upper() == mac.upper():
                        return {
                            "device_name": esp_name,
                            "bridge_id": did,
                            "info": info,
                        }
                except Exception:
                    pass
                finally:
                    await transport.disconnect()
        return None

    async def _async_bluetooth_confirm(
        self, user_input: dict[str, Any] | None, step_id: str
    ) -> ConfigFlowResult:
        """Shared handler for bluetooth confirmation steps."""
        assert self.discovery_info is not None
        errors: dict[str, str] = {}
        status = ""

        if user_input is not None:
            # Quick D-Bus pre-check: if the device is known to BlueZ but
            # not paired, skip the slow bleak connection attempts (~80s)
            # and go straight to the pairing step.
            from .dbus_pairing import is_dbus_available, async_is_device_paired

            if is_dbus_available():
                paired = await async_is_device_paired(
                    self.discovery_info.address
                )
                if paired is False:
                    _LOGGER.info(
                        "D-Bus pre-check: %s is not paired — "
                        "skipping to pairing step",
                        self.discovery_info.address,
                    )
                    self._pair_address = self.discovery_info.address
                    return await self.async_step_pair()

            try:
                capabilities = await self._async_fetch_capabilities(
                    self.discovery_info.address
                )

                self.fetched_data = capabilities
                self.fetched_address = self.discovery_info.address
                self.fetched_name = (
                    self.discovery_info.name or self.discovery_info.address
                )

                return await self.async_step_show_capabilities()

            except NotPairedException:
                _LOGGER.error("Device %s is not paired", self.discovery_info.address)
                self._pair_address = self.discovery_info.address
                return await self._route_to_pairing()
            except DeviceNotFoundException:
                _LOGGER.error("Device %s not found in range", self.discovery_info.address)
                errors["base"] = "device_not_found"
            except CannotConnectException:
                _LOGGER.error("Cannot connect to %s", self.discovery_info.address)
                errors["base"] = "cannot_connect"
            except BleakOutOfConnectionSlotsError:
                _LOGGER.error(
                    "No connection slot available for %s",
                    self.discovery_info.address,
                )
                errors["base"] = "out_of_slots"
            except BleakAbortedError:
                _LOGGER.error(
                    "Connection aborted for %s — device may be out of range "
                    "or using an unsupported Bluetooth proxy",
                    self.discovery_info.address,
                )
                errors["base"] = "connection_aborted"
            except BleakNotFoundError:
                # If habluetooth sees the device (advertisements) but bleak
                # can't connect, the most likely cause is a stale bond in
                # BlueZ preventing new connections.
                ble_dev = async_ble_device_from_address(
                    self.hass, self.discovery_info.address
                )
                if ble_dev:
                    _LOGGER.warning(
                        "Device %s is visible but unreachable — "
                        "likely stale bond",
                        self.discovery_info.address,
                    )
                    self._pair_address = self.discovery_info.address
                    return await self._route_to_pairing()
                _LOGGER.error(
                    "Device %s not found by any Bluetooth adapter",
                    self.discovery_info.address,
                )
                errors["base"] = "device_not_found"
            except DeviceAsleepException:
                # Keep the discovery flow alive — an abort would dismiss the
                # discovery card, and ADV deduplication stops HA from
                # re-creating it when the shaver wakes. errors["base"] does not
                # render on this schema-less confirmation step, so inject an
                # <ha-alert> into the description; ha-markdown renders it as a
                # real coloured alert box.
                status = (
                    '<ha-alert alert-type="error">The shaver is asleep — wake '
                    "it (press the power button or place it on its charging "
                    "stand), then click Read capabilities again.</ha-alert>\n\n"
                )
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"

        self.context["title_placeholders"] = {
            "name": f"Bluetooth ({self.discovery_info.address})"
        }

        return self.async_show_form(
            step_id=step_id,
            description_placeholders={
                "name": self.discovery_info.name or self.discovery_info.address,
                "status": status,
            },
            errors=errors,
        )

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
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input["address"].upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            # Quick D-Bus pre-check (same as bluetooth_confirm path)
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

            try:
                capabilities = await self._async_fetch_capabilities(address)

                self.fetched_data = capabilities
                self.fetched_address = address
                self.fetched_name = address

                return await self.async_step_show_capabilities()

            except NotPairedException:
                _LOGGER.error("Device %s is not paired", address)
                self._pair_address = address
                return await self._route_to_pairing()
            except DeviceAsleepException:
                errors["base"] = "device_asleep"
            except Exception:
                _LOGGER.exception(
                    "Setup failed: Unable to connect to the device or fetch capabilities"
                )
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema({vol.Required("address"): str})
        return self.async_show_form(
            step_id="user_bleak",
            data_schema=data_schema,
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
            await transport.connect()

            # Probe each service with one representative characteristic
            found_services: list[str] = []
            model_number: str | None = None
            probe_results: dict[str, bytes] = {}
            for svc_uuid, probe_char in self.SERVICE_PROBE_CHARS.items():
                raw = await transport.read_char(probe_char)
                if raw is not None:
                    found_services.append(svc_uuid)
                    probe_results[probe_char] = raw
                    if probe_char == CHAR_MODEL_NUMBER:
                        model_number = raw.decode("utf-8", errors="replace").strip()

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

            # Battery — reuse probe result if available, otherwise read separately
            battery: int | None = None
            raw_bat = probe_results.get(CHAR_BATTERY_LEVEL)
            if not raw_bat:
                raw_bat = await transport.read_char(CHAR_BATTERY_LEVEL)
            if raw_bat:
                battery = raw_bat[0]

            # Read firmware revision (with Software Revision fallback)
            firmware: str | None = None
            raw_fw = await transport.read_char(CHAR_FIRMWARE_REVISION)
            if raw_fw:
                firmware = raw_fw.decode("utf-8", errors="replace").strip()
            if not firmware:
                raw_sw = await transport.read_char(CHAR_SOFTWARE_REVISION)
                if raw_sw:
                    firmware = raw_sw.decode("utf-8", errors="replace").strip()

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
                probe_results = []
            else:
                probe_results = await self._probe_shaver_bridges(
                    esp_service_id, bridge_ids
                )
            slot_info = ""
            is_offline = False
            if probe_results:
                paired = sum(
                    1
                    for info in probe_results
                    if info.get("mac")
                    and info["mac"] != "00:00:00:00:00:00"
                )
                free = len(probe_results) - paired
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
                if len(bridge_ids) > 1:
                    slot_info = f"{len(bridge_ids)} bridges"
            label = f"{entry.title} ({device_name})"
            if slot_info:
                label = f"{label}, {slot_info}"
            if is_offline:
                label = f"⚪ {label}"
            options.append(SelectOptionDict(value=device_name, label=label))
        return options

    async def _probe_shaver_bridges(
        self, device_name: str, bridge_ids: list[str]
    ) -> list[dict[str, str]]:
        """Probe each bridge_id via ble_get_info, return list of info dicts.

        Service-name detection alone (`_detect_esp_bridge_ids`) can't tell a
        philips_shaver bridge from another component that registers the same
        service name pattern; only a bridge that actually answers on
        ``esphome.philips_shaver_ble_status`` counts. Best-effort: returns an
        empty list if the probe times out or the ESP is offline, the caller
        should then fall back to the plain bridge count.
        """
        results: list[dict[str, str]] = []
        for did in bridge_ids:
            svc_name = f"{device_name}_ble_get_info"
            if did:
                svc_name += f"_{did}"
            info_future: asyncio.Future[dict[str, str]] = (
                self.hass.loop.create_future()
            )

            @callback
            def _on_status(event: Event, _did: str = did) -> None:
                if (event.data.get("status") == "info"
                        # bridge_id compared case-insensitively (see above)
                        and event.data.get("bridge_id", "").lower() == _did.lower()
                        and not info_future.done()):
                    info_future.set_result(dict(event.data))

            unsub = self.hass.bus.async_listen(
                "esphome.philips_shaver_ble_status", _on_status
            )
            try:
                await self.hass.services.async_call(
                    "esphome", svc_name, {}, blocking=True
                )
                info = await asyncio.wait_for(info_future, timeout=2.0)
                results.append(info)
            except (asyncio.TimeoutError, Exception):
                pass
            finally:
                unsub()
        return results

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

        # Probe all bridge_ids in parallel — filter by bridge_id in response
        async def _probe(did: str) -> tuple[str, dict[str, str] | None]:
            svc_name = f"{self.fetched_esp_device_name}_ble_get_info"
            if did:
                svc_name += f"_{did}"
            info_future: asyncio.Future[dict[str, str]] = self.hass.loop.create_future()

            @callback
            def _on_info(event: Event) -> None:
                if (event.data.get("status") == "info"
                        # bridge_id compared case-insensitively (see above)
                        and event.data.get("bridge_id", "").lower() == did.lower()
                        and not info_future.done()):
                    info_future.set_result(dict(event.data))

            unsub = self.hass.bus.async_listen(
                "esphome.philips_shaver_ble_status", _on_info
            )
            try:
                await self.hass.services.async_call(
                    "esphome", svc_name, {}, blocking=True
                )
                return did, await asyncio.wait_for(info_future, timeout=3.0)
            except (asyncio.TimeoutError, Exception):
                return did, None
            finally:
                unsub()

        results = await asyncio.gather(*[_probe(did) for did in self._esp_bridge_ids])

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

    async def _esp_bridge_health_check(self) -> ConfigFlowResult:
        """Run bridge health check and proceed to status step."""
        # Skip if we already have bridge info from the device selection step
        if self.fetched_bridge_info:
            return await self.async_step_esp_bridge_status()

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
        return await self.async_step_esp_bridge_status()

    async def async_step_esp_bridge_status(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show ESP bridge status before reading shaver capabilities."""
        errors: dict[str, str] = {}

        if user_input is not None:
            esp_device_name = self.fetched_esp_device_name

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

            try:
                capabilities = await self._async_fetch_capabilities_esp(
                    esp_device_name, esp_device_name,
                    getattr(self, "fetched_esp_bridge_id", ""),
                )

                shaver_mac = capabilities.get("shaver_mac")
                if shaver_mac:
                    await self.async_set_unique_id(
                        shaver_mac.upper(), raise_on_progress=False
                    )
                else:
                    await self.async_set_unique_id(f"esp_{esp_device_name}")
                self._abort_if_unique_id_configured()

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

            except CannotConnectException:
                _LOGGER.error(
                    "ESP bridge: unable to read shaver capabilities via %s",
                    esp_device_name,
                )
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error reading shaver capabilities")
                errors["base"] = "unknown"

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

        # Determine shaver name for display
        if self.discovery_info:
            shaver_name = self.discovery_info.name or self.discovery_info.address
        elif info.get("ble_name"):
            shaver_name = info["ble_name"]
        elif info.get("mac") and info["mac"] != "00:00:00:00:00:00":
            shaver_name = f"Philips device ({info['mac']})"
        else:
            shaver_name = "Unknown device"

        # Multi-bridge ESPs ("shaver" + "oneblade" on the same atom-s3r) need
        # the bridge_id in the dialog so the user knows which bridge they're
        # configuring. {target} == "<device_name> / <bridge_id>" if a bridge_id
        # is set, otherwise just "<device_name>".
        bridge_id = self.fetched_esp_bridge_id or ""
        target = (
            f"{self.fetched_esp_device_name} / {bridge_id}"
            if bridge_id
            else self.fetched_esp_device_name
        )
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
                "target": target,
                "status": status_text,
            },
            errors=errors,
        )

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

        bridge_id = self.fetched_esp_bridge_id or ""
        target = (
            f"{self.fetched_esp_device_name} / {bridge_id}"
            if bridge_id
            else self.fetched_esp_device_name
        )
        return self.async_show_form(
            step_id="request_pair",
            data_schema=vol.Schema({}),
            description_placeholders={"target": target},
        )

    async def async_step_wait_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mode B: arm ble_pair_mode and wait for pair_complete or pair_timeout."""
        esp_device_name = self.fetched_esp_device_name
        bridge_id = self.fetched_esp_bridge_id or ""

        # Service name with bridge_id suffix (matches ShaverBridge::svc_name_)
        svc = f"{esp_device_name}_ble_pair_mode"
        if bridge_id:
            svc = f"{svc}_{bridge_id}"

        # Filter events by bridge_id so multi-bridge ESPs don't cross-talk.
        # ShaverBridge::fire_event auto-injects bridge_id, so the field is
        # always present (empty string for single-bridge YAMLs).
        pair_future: asyncio.Future = self.hass.loop.create_future()

        @callback
        def _on_status(event: Event) -> None:
            # bridge_id compared case-insensitively (HA lowercases service names)
            if event.data.get("bridge_id", "").lower() != bridge_id.lower():
                return
            status = event.data.get("status")
            if status not in ("pair_complete", "pair_timeout", "pair_failed"):
                return
            if not pair_future.done():
                pair_future.set_result(dict(event.data))

        unsub = self.hass.bus.async_listen(
            "esphome.philips_shaver_ble_status", _on_status
        )

        try:
            await self.hass.services.async_call(
                "esphome",
                svc,
                {"enabled": True, "timeout_s": "60"},
                blocking=True,
            )
        except Exception as err:  # pylint: disable=broad-except
            unsub()
            _LOGGER.error("ble_pair_mode service call failed: %s", err)
            return self.async_show_form(
                step_id="request_pair",
                data_schema=vol.Schema({}),
                errors={"base": "service_call_failed"},
                description_placeholders={
                    "target": (
                        f"{esp_device_name} / {bridge_id}"
                        if bridge_id else esp_device_name
                    ),
                },
            )

        # 65 s margin = 60 s pair window + 5 s grace for the pair_timeout
        # event to land. The bridge fires pair_timeout/pair_complete itself
        # so the wait_for is just a safety net for missed events.
        try:
            result = await asyncio.wait_for(pair_future, timeout=65)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Pair-mode wait elapsed without pair_complete/pair_timeout "
                "event from bridge"
            )
            result = {"status": "pair_timeout"}
        finally:
            unsub()

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
                description_placeholders={
                    "target": (
                        f"{esp_device_name} / {bridge_id}"
                        if bridge_id else esp_device_name
                    ),
                },
            )

        # pair_complete — bond established. identity_address comes from
        # the bridge's pair_complete event payload (Coord fills it from
        # parent_->get_remote_bda after AUTH_CMPL.success).
        identity_address = (
            result.get("identity_address") or result.get("mac") or ""
        )
        if identity_address:
            self.fetched_address = identity_address

        # Continue with capabilities probe on the now-bonded shaver.
        try:
            capabilities = await self._async_fetch_capabilities_esp(
                esp_device_name, esp_device_name, bridge_id,
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception(
                "Capability fetch failed after pair_complete (%s) — bond "
                "exists but the shaver may have disconnected before probe",
                identity_address,
            )
            return self.async_show_form(
                step_id="request_pair",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
                description_placeholders={
                    "target": (
                        f"{esp_device_name} / {bridge_id}"
                        if bridge_id else esp_device_name
                    ),
                },
            )

        shaver_mac = capabilities.get("shaver_mac") or identity_address
        if shaver_mac:
            await self.async_set_unique_id(
                shaver_mac.upper(), raise_on_progress=False
            )
        else:
            await self.async_set_unique_id(f"esp_{esp_device_name}")
        self._abort_if_unique_id_configured()

        self.fetched_data = capabilities
        if self.fetched_bridge_info:
            self.fetched_data["bridge_version"] = self.fetched_bridge_info.get(
                "version"
            )
        self.fetched_address = shaver_mac
        model = capabilities.get("model_number")
        self.fetched_name = model if model else esp_device_name
        self.fetched_transport_type = TRANSPORT_ESP_BRIDGE

        return await self.async_step_show_capabilities()

    async def _route_to_pairing(self) -> ConfigFlowResult:
        """Route to D-Bus pairing if available, otherwise show script instructions."""
        from .dbus_pairing import is_dbus_available

        if is_dbus_available():
            return await self.async_step_pair()
        return await self.async_step_not_paired()

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair the device via D-Bus and retry capabilities fetch."""
        errors: dict[str, str] = {}

        if user_input is not None:
            from .dbus_pairing import async_pair_and_trust, PairingError

            address = self._pair_address
            try:
                await async_pair_and_trust(address)
                _LOGGER.info("D-Bus pairing successful for %s", address)

                # Brief settle time for BlueZ key distribution
                await asyncio.sleep(2)

                # Retry capabilities fetch
                capabilities = await self._async_fetch_capabilities(address)
                self.fetched_data = capabilities
                self.fetched_address = address
                self.fetched_name = (
                    self.discovery_info.name
                    if self.discovery_info
                    else address
                )
                return await self.async_step_show_capabilities()

            except PairingError as err:
                _LOGGER.error(
                    "D-Bus pairing failed for %s: %s", address, err
                )
                errors["base"] = "pairing_failed"
            except NotPairedException:
                _LOGGER.error(
                    "Pairing succeeded but device still not accessible "
                    "for %s — falling back to manual instructions",
                    address,
                )
                return await self.async_step_not_paired()
            except DeviceAsleepException:
                errors["base"] = "device_asleep"
            except (
                DeviceNotFoundException,
                CannotConnectException,
                BleakOutOfConnectionSlotsError,
                BleakAbortedError,
                BleakNotFoundError,
            ) as err:
                _LOGGER.error(
                    "Post-pairing connection failed for %s: %s", address, err
                )
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during pairing")
                errors["base"] = "pairing_failed"

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

    async def async_step_not_paired(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show pairing instructions when the device is not paired."""
        if user_input is not None:
            # Retry — go back to the appropriate confirm/manual step
            if self.discovery_info:
                return await self.async_step_bluetooth_confirm(user_input)
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
        path = self.fetched_data.get("connection_path") or self.fetched_esp_device_name
        connection_status = self._get_connection_status_text(
            self.fetched_transport_type, path
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
    def _get_connection_status_text(transport_type: str | None, path: str | None) -> str:
        """Connection status line shown above the device info.

        Leads with the transport *class* (ESP32 Bridge / Direct Bluetooth) so
        it reads the same as the other "via" dialogs, with the adapter/bridge
        label appended in parentheses as a disambiguator.
        """
        transport_label = (
            "ESP32 Bridge"
            if transport_type == TRANSPORT_ESP_BRIDGE
            else "Direct Bluetooth"
        )
        if path:
            return f"✅ Connected via **{transport_label}** ({path})."
        return f"✅ Connected via **{transport_label}**."

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
