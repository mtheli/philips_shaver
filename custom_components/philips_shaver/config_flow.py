from __future__ import annotations

from typing import Any

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
from bleak_retry_connector import BleakConnectionError, establish_connection

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
    CHAR_DEVICE_STATE,
    CHAR_HISTORY_SYNC_STATUS,
    SVC_BATTERY,
    SVC_DEVICE_INFO,
    SVC_PLATFORM,
    SVC_HISTORY,
    SVC_CONTROL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_ENABLE_LIVE_UPDATES,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    CONF_ADDRESS,
    CONF_POLL_INTERVAL,
    CONF_ENABLE_LIVE_UPDATES,
    CONF_CAPABILITIES,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_BLEAK,
    TRANSPORT_ESP_BRIDGE,
    CONF_ESP_DEVICE_NAME,
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

        except (BleakConnectionError, TimeoutError) as err:
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
        return await self._async_bluetooth_confirm(user_input, "bluetooth_confirm")

    async def _async_bluetooth_confirm(
        self, user_input: dict[str, Any] | None, step_id: str
    ) -> ConfigFlowResult:
        """Shared handler for bluetooth confirmation steps."""
        assert self.discovery_info is not None
        errors: dict[str, str] = {}

        if user_input is not None:
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
                errors["base"] = "not_paired"
            except Exception:
                _LOGGER.exception(
                    "Setup failed: Unable to connect to the device or fetch capabilities"
                )
                errors["base"] = "cannot_connect"

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

            try:
                capabilities = await self._async_fetch_capabilities(address)

                self.fetched_data = capabilities
                self.fetched_address = address
                self.fetched_name = address

                return await self.async_step_show_capabilities()

            except NotPairedException:
                _LOGGER.error("Device %s is not paired", address)
                errors["base"] = "not_paired"
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
        SVC_CONTROL: CHAR_CAPABILITIES,
    }

    async def _async_fetch_capabilities_esp(
        self,
        address: str,
        esp_device_name: str,
    ) -> dict[str, Any]:
        """Read capabilities and probe services via ESP32 bridge."""
        transport = EspBridgeTransport(self.hass, address, esp_device_name)
        try:
            await transport.connect()

            # Read capabilities first — proves bridge ↔ shaver connectivity
            raw_cap = await transport.read_char(CHAR_CAPABILITIES)
            if raw_cap is None:
                raise CannotConnectException(
                    "Could not read capabilities via ESP bridge – shaver may not be connected"
                )

            cap_int = int.from_bytes(raw_cap, "little")

            # Probe each service with one representative characteristic
            found_services: list[str] = []
            model_number: str | None = None
            for svc_uuid, probe_char in self.SERVICE_PROBE_CHARS.items():
                if probe_char == CHAR_CAPABILITIES:
                    # Already read successfully above
                    found_services.append(svc_uuid)
                    continue
                raw = await transport.read_char(probe_char)
                if raw is not None:
                    found_services.append(svc_uuid)
                    if probe_char == CHAR_MODEL_NUMBER:
                        model_number = raw.decode("utf-8", errors="replace").strip()

            # Also read firmware revision
            firmware: str | None = None
            raw_fw = await transport.read_char(CHAR_FIRMWARE_REVISION)
            if raw_fw:
                firmware = raw_fw.decode("utf-8", errors="replace").strip()

            return {
                "services": found_services,
                "capabilities": cap_int,
                "shaver_mac": transport.detected_mac,
                "model_number": model_number,
                "firmware": firmware,
            }

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

    async def async_step_esp_bridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle ESP32 bridge configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            esp_device_name = user_input["esp_device_name"].strip().replace("-", "_")

            # Quick bridge health check via ble_get_info
            transport = EspBridgeTransport(self.hass, esp_device_name, esp_device_name)
            bridge_info = None
            try:
                await transport.connect()
                bridge_info = await transport.get_bridge_info()
            except TransportError:
                _LOGGER.error("ESP bridge not reachable: %s", esp_device_name)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error checking ESP bridge")
                errors["base"] = "unknown"
            finally:
                await transport.disconnect()

            if not errors:
                self.fetched_esp_device_name = esp_device_name
                self.fetched_bridge_info = bridge_info
                return await self.async_step_esp_bridge_status()

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

    async def async_step_esp_bridge_status(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show ESP bridge status before reading shaver capabilities."""
        errors: dict[str, str] = {}

        if user_input is not None:
            esp_device_name = self.fetched_esp_device_name
            try:
                capabilities = await self._async_fetch_capabilities_esp(
                    esp_device_name, esp_device_name
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

        # Format bridge status display
        info = self.fetched_bridge_info or {}
        if info:
            version = info.get("version", "?")
            ble_connected = info.get("ble_connected", "false") == "true"
            paired = info.get("paired", "false") == "true"
            mac = info.get("mac", "")

            status_lines = [
                f"**Version:** v{version}",
                f"**BLE:** {'✅ Connected' if ble_connected else '❌ Disconnected'}",
                f"**Paired:** {'✅ Yes' if paired else '❌ No'}",
            ]
            if mac and mac != "00:00:00:00:00:00":
                status_lines.append(f"**MAC:** {mac}")
            status_text = "\n".join(status_lines)
        else:
            status_text = (
                "⚠️ Diagnostic details not available. "
                "Consider updating the ESP bridge component."
            )

        return self.async_show_form(
            step_id="esp_bridge_status",
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_name": self.fetched_esp_device_name,
                "status": status_text,
            },
            errors=errors,
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
            }

            if self.fetched_transport_type == TRANSPORT_ESP_BRIDGE:
                entry_data[CONF_TRANSPORT_TYPE] = TRANSPORT_ESP_BRIDGE
                entry_data[CONF_ESP_DEVICE_NAME] = self.fetched_esp_device_name
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

        services_text = self._get_service_status_text(
            self.fetched_data.get("services", [])
        )

        cap_val = self.fetched_data.get("capabilities", 0)
        capabilities_text = self._get_capabilities_text(cap_val)

        # Device info line (model + firmware)
        model = self.fetched_data.get("model_number")
        firmware = self.fetched_data.get("firmware")
        device_info_parts: list[str] = []
        if model:
            device_info_parts.append(f"Model: {model}")
        if firmware:
            device_info_parts.append(f"Firmware: {firmware}")
        device_info = "\n" + " | ".join(device_info_parts) if device_info_parts else ""

        # Bridge info (ESP bridge only)
        bridge_version = self.fetched_data.get("bridge_version")
        esp_name = self.fetched_esp_device_name
        if bridge_version and esp_name:
            bridge_info = f"\nESP Bridge: {esp_name} (v{bridge_version})"
        elif bridge_version:
            bridge_info = f"\nESP Bridge: v{bridge_version}"
        elif esp_name:
            bridge_info = f"\nESP Bridge: {esp_name}"
        else:
            bridge_info = ""

        return self.async_show_form(
            step_id="show_capabilities",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": str(self.fetched_name),
                "services": services_text,
                "capabilities": capabilities_text,
                "device_info": device_info,
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

    @staticmethod
    def _get_capabilities_text(cap_val: int) -> str:
        """Format capability flags as human-readable checklist."""
        lines: list[str] = []
        for bit, name in PhilipsShaverConfigFlow.CAPABILITY_FLAGS:
            if cap_val & (1 << bit):
                lines.append(f"✅ {name}")
            else:
                lines.append(f"⬜ {name}")
        return "\n".join(lines)

    def _get_service_status_text(self, fetched_uuids: list[str]) -> str:
        """Compare found services with PHILIPS_SERVICE_UUIDS and return formatted text."""

        fetched_lower = [s.lower() for s in fetched_uuids]
        required_lower = [s.lower() for s in PHILIPS_SERVICE_UUIDS]

        found_required = []
        missing_required = []
        unknown_services = []

        for uuid in sorted(required_lower):
            if uuid in fetched_lower:
                found_required.append(f"✅ {uuid}")
            else:
                missing_required.append(f"❌ {uuid}")

        for uuid in sorted(fetched_lower):
            if uuid not in required_lower:
                unknown_services.append(f"❔ {uuid}")

        return "\n".join(found_required + missing_required + unknown_services)
