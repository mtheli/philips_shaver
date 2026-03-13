from __future__ import annotations

from typing import Any

import asyncio
import voluptuous as vol
import logging

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
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
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
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
    DEFAULT_POLL_INTERVAL,
    DEFAULT_ENABLE_LIVE_UPDATES,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    CONF_ADDRESS,
    CONF_POLL_INTERVAL,
    CONF_ENABLE_LIVE_UPDATES,
    CONF_CAPABILITIES,
    CONF_SERVICES,
    CONF_DEVICE_TYPE,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_BLEAK,
    TRANSPORT_ESP_BRIDGE,
    CONF_ESP_DEVICE_NAME,
    CONF_ESP_DEVICE_ID,
    CONF_NOTIFY_THROTTLE,
    DEFAULT_NOTIFY_THROTTLE,
    MIN_NOTIFY_THROTTLE,
    MAX_NOTIFY_THROTTLE,
)
from .transport import EspBridgeTransport
from .exceptions import (
    DeviceNotFoundException,
    CannotConnectException,
    NotPairedException,
    TransportError,
)

def _is_hassio(hass) -> bool:
    """Check if Home Assistant is running on HAOS / Supervised."""
    return "hassio" in hass.config.components

_LOGGER = logging.getLogger(__name__)


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
            entry_data = {
                CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                CONF_ENABLE_LIVE_UPDATES: user_input[CONF_ENABLE_LIVE_UPDATES],
            }
            if is_esp and CONF_NOTIFY_THROTTLE in user_input:
                entry_data[CONF_NOTIFY_THROTTLE] = int(
                    user_input[CONF_NOTIFY_THROTTLE]
                )
            return self.async_create_entry(data=entry_data)

        schema_fields: dict = {
            vol.Required(CONF_POLL_INTERVAL): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_POLL_INTERVAL,
                    max=MAX_POLL_INTERVAL,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_ENABLE_LIVE_UPDATES): BooleanSelector(),
        }

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

        data_schema = vol.Schema(schema_fields)

        suggested_values = {
            CONF_POLL_INTERVAL: self.config_entry.options.get(
                CONF_POLL_INTERVAL,
                DEFAULT_POLL_INTERVAL,
            ),
            CONF_ENABLE_LIVE_UPDATES: self.config_entry.options.get(
                CONF_ENABLE_LIVE_UPDATES,
                DEFAULT_ENABLE_LIVE_UPDATES,
            ),
        }
        if is_esp:
            suggested_values[CONF_NOTIFY_THROTTLE] = self.config_entry.options.get(
                CONF_NOTIFY_THROTTLE,
                DEFAULT_NOTIFY_THROTTLE,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                data_schema, suggested_values
            ),
            description_placeholders={
                "min_int": str(MIN_POLL_INTERVAL),
                "max_int": str(MAX_POLL_INTERVAL),
                "rec_int": str(DEFAULT_POLL_INTERVAL),
            },
            errors=errors,
        )


class PhilipsShaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Philips Shaver."""

    VERSION = 1
    MINOR_VERSION = 2

    discovery_info: BluetoothServiceInfoBleak | None = None

    # Intermediate data storage between steps
    fetched_data: dict[str, Any] | None = None
    fetched_address: str | None = None
    fetched_name: str | None = None
    fetched_transport_type: str | None = None
    fetched_esp_device_name: str | None = None
    fetched_bridge_info: dict[str, str] | None = None
    _pair_address: str | None = None  # MAC for D-Bus pairing step

    async def _async_fetch_capabilities(
        self,
        address,
    ) -> dict[str, Any]:
        """Connect to the BLE device and read its capabilities."""
        capabilities: dict[str, Any] = {}

        device = async_ble_device_from_address(self.hass, address)
        if not device:
            raise DeviceNotFoundException("BLE device not found")

        try:
            client: BleakClient | None = None
            client = await establish_connection(
                BleakClient, device, "philips_shaver", timeout=15
            )

            if not client.is_connected:
                raise CannotConnectException("BLE connection failed")
            _LOGGER.info("Connected to %s, address=%s", device.name, address)

            _LOGGER.info("Reading services from %s...", address)
            services = client.services
            capabilities["services"] = [str(s.uuid) for s in services]

            # Probe battery level to verify pairing (requires encryption).
            # Any read failure here indicates the device is not paired —
            # BlueZ returns ATT errors (e.g. 0x0e "Unlikely Error") or
            # times out while attempting auto-pairing.
            _LOGGER.info("Probing pairing status on %s...", address)
            if services.get_characteristic(CHAR_BATTERY_LEVEL):
                try:
                    raw_battery = await asyncio.wait_for(
                        client.read_gatt_char(CHAR_BATTERY_LEVEL), timeout=10
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
                    raw_cap = await client.read_gatt_char(CHAR_CAPABILITIES)
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

        return capabilities

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
                self.fetched_esp_device_id = esp.get("device_id", "")
                self.fetched_bridge_info = esp["info"]
                return await self.async_step_esp_bridge_status()

        return await self._async_bluetooth_confirm(user_input, "bluetooth_confirm")

    async def _find_esp_bridge_for_mac(self, mac: str) -> dict | None:
        """Check if any ESP bridge is connected to the given MAC."""
        esphome_entries = self.hass.config_entries.async_entries("esphome")
        for entry in esphome_entries:
            device_name = entry.data.get("device_name")
            if not device_name:
                continue
            esp_name = device_name.replace("-", "_")
            device_ids = self._detect_esp_device_ids(esp_name)
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
                            "device_id": did,
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
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"

        self.context["title_placeholders"] = {
            "name": self.discovery_info.name or self.discovery_info.address
        }

        return self.async_show_form(
            step_id=step_id,
            description_placeholders={
                "name": self.discovery_info.name or self.discovery_info.address,
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
        esp_device_id: str = "",
    ) -> dict[str, Any]:
        """Read capabilities and probe services via ESP32 bridge."""
        transport = EspBridgeTransport(self.hass, address, esp_device_name, esp_device_id)
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

    def _get_esphome_device_options(self) -> list[SelectOptionDict]:
        """Build a list of available ESPHome devices for the selector."""
        esphome_entries = self.hass.config_entries.async_entries("esphome")
        options: list[SelectOptionDict] = []
        for entry in esphome_entries:
            device_name = entry.data.get("device_name")
            if device_name:
                options.append(
                    SelectOptionDict(
                        value=device_name,
                        label=f"{entry.title} ({device_name})",
                    )
                )
        return options

    def _detect_esp_device_ids(self, esp_device_name: str) -> list[str]:
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
            device_ids = self._detect_esp_device_ids(esp_device_name)
            if not device_ids:
                _LOGGER.error("No philips_shaver services found on %s", esp_device_name)
                errors["base"] = "cannot_connect"
            else:
                self.fetched_esp_device_name = esp_device_name
                self._esp_device_ids = device_ids

                if len(device_ids) > 1:
                    # Multiple devices — let user pick
                    return await self.async_step_esp_select_device()

                # Single device (or single suffixed device)
                self.fetched_esp_device_id = device_ids[0]
                return await self._esp_bridge_health_check()

        esp_options = self._get_esphome_device_options()

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
        if user_input is not None:
            self.fetched_esp_device_id = user_input["esp_device_id"]
            # Store bridge info from the probe if available
            self.fetched_bridge_info = self._esp_device_info.get(
                user_input["esp_device_id"]
            )
            return await self._esp_bridge_health_check()

        # Collect MACs already configured for this integration
        configured_macs = {
            entry.unique_id.upper()
            for entry in self._async_current_entries()
            if entry.unique_id
        }

        # Probe each device_id to get MAC and connection status
        self._esp_device_info: dict[str, dict] = {}
        options: list[SelectOptionDict] = []
        for did in self._esp_device_ids:
            transport = EspBridgeTransport(
                self.hass, self.fetched_esp_device_name,
                self.fetched_esp_device_name, did,
            )
            info = None
            try:
                await transport.connect()
                info = await transport.get_bridge_info()
            except Exception:
                pass
            finally:
                await transport.disconnect()

            self._esp_device_info[did] = info or {}
            mac = (info or {}).get("mac", "")
            ble = (info or {}).get("ble_connected", "false") == "true"

            # Skip devices that are already configured
            if mac and mac.upper() in configured_macs:
                continue

            if mac and mac != "00:00:00:00:00:00":
                label = f"{did} — {mac} ({'connected' if ble else 'disconnected'})"
            else:
                label = did
            options.append(SelectOptionDict(value=did, label=label))

        if not options:
            return self.async_abort(reason="already_configured")

        # Auto-select if only one device left
        if len(options) == 1:
            self.fetched_esp_device_id = options[0]["value"]
            self.fetched_bridge_info = self._esp_device_info.get(options[0]["value"])
            return await self._esp_bridge_health_check()

        return self.async_show_form(
            step_id="esp_select_device",
            data_schema=vol.Schema(
                {
                    vol.Required("esp_device_id"): SelectSelector(
                        SelectSelectorConfig(options=options)
                    ),
                }
            ),
        )

    async def _esp_bridge_health_check(self) -> ConfigFlowResult:
        """Run bridge health check and proceed to status step."""
        # Skip if we already have bridge info from the device selection step
        if self.fetched_bridge_info:
            return await self.async_step_esp_bridge_status()

        esp_device_name = self.fetched_esp_device_name
        esp_device_id = self.fetched_esp_device_id

        transport = EspBridgeTransport(
            self.hass, esp_device_name, esp_device_name, esp_device_id
        )
        bridge_info = None
        try:
            await transport.connect()
            bridge_info = await transport.get_bridge_info()
        except TransportError:
            _LOGGER.error("ESP bridge not reachable: %s (device_id=%s)", esp_device_name, esp_device_id)
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
            try:
                capabilities = await self._async_fetch_capabilities_esp(
                    esp_device_name, esp_device_name,
                    getattr(self, "fetched_esp_device_id", ""),
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
        esp_device_id = getattr(self, "fetched_esp_device_id", "")
        transport = EspBridgeTransport(
            self.hass,
            self.fetched_esp_device_name,
            self.fetched_esp_device_name,
            esp_device_id,
        )
        try:
            await transport.connect()
            self.fetched_bridge_info = await transport.get_bridge_info()
        except Exception:
            pass
        finally:
            await transport.disconnect()

        # Format bridge status display
        info = self.fetched_bridge_info or {}
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
                rows.append(f"<tr><td><b>MAC</b></td><td><code>{mac}</code></td></tr>")

            status_text = "<table>" + "".join(rows) + "</table>"
        else:
            status_text = (
                "⚠️ Diagnostic details not available. "
                "Consider updating the ESP bridge component."
            )

        # Determine shaver name for display
        if self.discovery_info:
            shaver_name = self.discovery_info.name or self.discovery_info.address
        elif info.get("mac") and info["mac"] != "00:00:00:00:00:00":
            shaver_name = info["mac"]
        else:
            shaver_name = "Unknown device"

        return self.async_show_form(
            step_id="esp_bridge_status",
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_name": self.fetched_esp_device_name,
                "shaver_name": shaver_name,
                "status": status_text,
            },
            errors=errors,
        )

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

    async def async_step_show_capabilities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show detected services and create entry."""

        if self.fetched_data is None:
            return await self.async_step_user()

        if user_input is not None:
            entry_data: dict[str, Any] = {
                CONF_CAPABILITIES: self.fetched_data.get("capabilities", 0),
                CONF_SERVICES: self.fetched_data.get("services", []),
            }
            device_type = self.fetched_data.get("device_type")
            if device_type:
                entry_data[CONF_DEVICE_TYPE] = device_type

            if self.fetched_transport_type == TRANSPORT_ESP_BRIDGE:
                entry_data[CONF_TRANSPORT_TYPE] = TRANSPORT_ESP_BRIDGE
                entry_data[CONF_ESP_DEVICE_NAME] = self.fetched_esp_device_name
                esp_device_id = getattr(self, "fetched_esp_device_id", "")
                if esp_device_id:
                    entry_data[CONF_ESP_DEVICE_ID] = esp_device_id
                if self.fetched_address:
                    entry_data[CONF_ADDRESS] = self.fetched_address
            else:
                entry_data[CONF_ADDRESS] = self.fetched_address

            return self.async_create_entry(
                title=f"Philips Shaver ({self.fetched_name})",
                data=entry_data,
                options={
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                    CONF_ENABLE_LIVE_UPDATES: DEFAULT_ENABLE_LIVE_UPDATES,
                },
            )

        device_type = self.fetched_data.get("device_type", "")
        services_text = self._get_service_status_text(
            self.fetched_data.get("services", []), device_type
        )

        cap_val = self.fetched_data.get("capabilities", 0)
        groomer_cap = self.fetched_data.get("groomer_capabilities")
        capabilities_text = self._get_capabilities_text(cap_val, groomer_cap)

        # Connection info suffix (e.g. " via ESP Bridge")
        esp_name = self.fetched_esp_device_name
        bridge_info = " via ESP Bridge" if esp_name else ""

        return self.async_show_form(
            step_id="show_capabilities",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": str(self.fetched_name),
                "services": services_text,
                "capabilities": capabilities_text,
                "bridge_info": bridge_info,
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
    def _get_capabilities_text(
        cap_val: int, groomer_cap: int | None = None
    ) -> str:
        """Format capability flags as HTML table."""
        if cap_val == 0 and groomer_cap is None:
            return "No advanced capabilities detected (basic monitoring only)"

        rows: list[str] = []

        # Standard shaver capabilities (0x0302)
        if cap_val > 0:
            for bit, name in PhilipsShaverConfigFlow.CAPABILITY_FLAGS:
                icon = "✅" if cap_val & (1 << bit) else "⬜"
                rows.append(f"<tr><td>{icon}</td><td>{name}</td></tr>")

        # OneBlade groomer capabilities (0x0702)
        if groomer_cap is not None:
            for bit, name in PhilipsShaverConfigFlow.GROOMER_CAPABILITY_FLAGS:
                icon = "✅" if groomer_cap & (1 << bit) else "⬜"
                rows.append(f"<tr><td>{icon}</td><td>{name}</td></tr>")

        if not rows:
            return "No advanced capabilities detected (basic monitoring only)"
        return "<table>" + "".join(rows) + "</table>"

    SERVICE_NAMES: dict[str, str] = {
        SVC_BATTERY.lower(): "Battery",
        SVC_DEVICE_INFO.lower(): "Device Information",
        SVC_PLATFORM.lower(): "Platform",
        SVC_HISTORY.lower(): "History",
        SVC_CONTROL.lower(): "Control",
        SVC_SERIAL.lower(): "Serial / Diagnostic",
        SVC_GROOMER.lower(): "Smart Groomer",
    }

    @staticmethod
    def _uuid_short(uuid: str) -> str:
        """Extract the short prefix from a UUID (e.g. '8d560100' or '0000180f')."""
        return uuid.split("-")[0]

    def _get_service_status_text(self, fetched_uuids: list[str], device_type: str = "") -> str:
        """Compare found services with expected services for this device type."""
        fetched_lower = {s.lower() for s in fetched_uuids}
        known_lower = {s.lower() for s in PHILIPS_SERVICE_UUIDS}

        # Expected services depend on device type
        expected = {s.lower() for s in PHILIPS_SERVICE_UUIDS}
        if device_type == "m":
            # OneBlade: no Control Service (0x0300), no Serial/Diagnostic (0x0600)
            expected.discard(SVC_CONTROL.lower())
            expected.discard(SVC_SERIAL.lower())
        else:
            # Shaver: no Smart Groomer Service (0x0700)
            expected.discard(SVC_GROOMER.lower())

        found_rows: list[str] = []
        missing_rows: list[str] = []
        unknown_rows: list[str] = []

        for uuid in sorted(expected):
            name = self.SERVICE_NAMES.get(uuid, "Unknown")
            short = self._uuid_short(uuid)
            if uuid in fetched_lower:
                found_rows.append(
                    f"<tr><td>✅</td><td>{name}</td><td><code>{short}</code></td></tr>"
                )
            else:
                missing_rows.append(
                    f"<tr><td>❌</td><td>{name}</td><td><code>{short}</code></td></tr>"
                )

        for uuid in sorted(fetched_lower - expected):
            short = self._uuid_short(uuid)
            if uuid in known_lower:
                name = self.SERVICE_NAMES.get(uuid, "Unknown")
                found_rows.append(
                    f"<tr><td>✅</td><td>{name}</td><td><code>{short}</code></td></tr>"
                )
            else:
                unknown_rows.append(
                    f"<tr><td>❔</td><td>Unknown</td><td><code>{short}</code></td></tr>"
                )

        rows = found_rows + missing_rows + unknown_rows
        return "<table>" + "".join(rows) + "</table>"
