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
from bleak_retry_connector import BleakConnectionError, establish_connection

from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
)
from .exceptions import DeviceNotFoundException, CannotConnectException

from .const import (
    DOMAIN,
    PHILIPS_SERVICE_UUIDS,
    CHAR_CAPABILITIES,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_ENABLE_LIVE_UPDATES,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    CONF_ADDRESS,
    CONF_POLL_INTERVAL,
    CONF_ENABLE_LIVE_UPDATES,
    CONF_CAPABILITIES,
)

_LOGGER = logging.getLogger(__name__)


class PhilipsShaverOptionsFlow(OptionsFlowWithReload):
    """Options flow für Philips Shaver."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                    CONF_ENABLE_LIVE_UPDATES: user_input[CONF_ENABLE_LIVE_UPDATES],
                }
            )

        data_schema: vol.Schema = vol.Schema(
            {
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
        )
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
    MINOR_VERSION = 1

    discovery_info: BluetoothServiceInfoBleak | None = None

    # Zwischenspeicher für Daten zwischen den Steps
    fetched_data: dict[str, Any] | None = None
    fetched_address: str | None = None
    fetched_name: str | None = None

    async def _async_fetch_capabilities(
        self,
        address,
    ) -> dict[str, Any]:
        """Connect to the BLE device and read its capabilities."""
        capabilities: dict[str, Any] = {}

        # getting BLE device
        device = async_ble_device_from_address(self.hass, address)
        if not device:
            raise DeviceNotFoundException("BLE device not found")

        # connecting to the device using retry connector
        # Note: We use standard BleakClient here for discovery,
        # coordinator will use InitialGattCache later.
        try:
            client: BleakClient | None = None
            client = await establish_connection(
                BleakClient, device, "philips_shaver", timeout=15
            )

            if not client.is_connected:
                raise CannotConnectException("BLE connection failed")
            _LOGGER.info("Connected to %s, address=%s", device.name, address)

            # getting services
            _LOGGER.info("Reading services from %s...", address)
            services = client.services
            capabilities["services"] = [str(s.uuid) for s in services]

            # reading capabilities characteristic
            _LOGGER.info("Reading capabilities from %s...", address)
            if services.get_characteristic(CHAR_CAPABILITIES):
                raw_cap = await client.read_gatt_char(CHAR_CAPABILITIES)
                if raw_cap:
                    # WICHTIG: Als Int speichern für JSON Serialisierung
                    cap_int = int.from_bytes(raw_cap, "little")
                    capabilities["capabilities"] = cap_int
            else:
                capabilities["capabilities"] = (
                    0  # Fallback 0 statt None für einfachere Handhabung
                )

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

        # Direkt zur Bestätigung, Unpaired-Check entfernt
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery and fetch capabilities."""
        assert self.discovery_info is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # 1. Daten holen
                capabilities = await self._async_fetch_capabilities(
                    self.discovery_info.address
                )

                # 2. Daten zwischenspeichern
                self.fetched_data = capabilities
                self.fetched_address = self.discovery_info.address
                self.fetched_name = (
                    self.discovery_info.name or self.discovery_info.address
                )

                # 3. Weiterleiten zur Anzeige (statt create_entry)
                return await self.async_step_show_capabilities()

            except Exception:
                _LOGGER.error(
                    "Setup failed: Unable to connect to the device or fetch capabilities"
                )
                errors["base"] = "cannot_connect"

        self.context["title_placeholders"] = {
            "name": self.discovery_info.name or self.discovery_info.address
        }

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self.discovery_info.name or self.discovery_info.address,
            },
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user (manual MAC address entry)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input["address"].upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            try:
                # 1. Daten holen
                capabilities = await self._async_fetch_capabilities(address)

                # 2. Daten zwischenspeichern
                self.fetched_data = capabilities
                self.fetched_address = address
                self.fetched_name = address

                # 3. Weiterleiten zur Anzeige
                return await self.async_step_show_capabilities()

            except Exception:
                _LOGGER.error(
                    "Setup failed: Unable to connect to the device or fetch capabilities"
                )
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema({vol.Required("address"): str})
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_show_capabilities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show detected services and create entry."""

        if self.fetched_data is None:
            return await self.async_step_user()

        # Wenn der User bestätigt -> Eintrag erstellen
        if user_input is not None:
            return self.async_create_entry(
                title=f"Philips Shaver ({self.fetched_name})",
                data={
                    CONF_ADDRESS: self.fetched_address,
                    CONF_CAPABILITIES: self.fetched_data.get("capabilities", 0),
                },
                options={
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                    CONF_ENABLE_LIVE_UPDATES: DEFAULT_ENABLE_LIVE_UPDATES,
                },
            )

        # helper method to get services status text
        services_text = self._get_service_status_text(
            self.fetched_data.get("services", [])
        )

        # getting capability value for display
        cap_val = self.fetched_data.get("capabilities", 0)

        return self.async_show_form(
            step_id="show_capabilities",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": str(self.fetched_name),
                "services": services_text,
                "capability_value": f"{cap_val} (0x{cap_val:02X})",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> PhilipsShaverOptionsFlow:
        """Create the options flow."""
        return PhilipsShaverOptionsFlow()

    def _get_service_status_text(self, fetched_uuids: list[str]) -> str:
        """Vergleicht gefundene Services mit PHILIPS_SERVICE_UUIDS und gibt formatierten Text zurück."""

        # Listen normalisieren (Kleinschreibung)
        fetched_lower = [s.lower() for s in fetched_uuids]
        required_lower = [s.lower() for s in PHILIPS_SERVICE_UUIDS]

        found_required = []
        missing_required = []
        unknown_services = []

        # 1. Erwartete Services prüfen (sortiert)
        for uuid in sorted(required_lower):
            if uuid in fetched_lower:
                found_required.append(f"✅ {uuid}")
            else:
                missing_required.append(f"❌ {uuid}")

        # 2. Unbekannte Services identifizieren (sortiert)
        for uuid in sorted(fetched_lower):
            if uuid not in required_lower:
                unknown_services.append(f"❔ {uuid}")

        # Alles zusammenführen
        return "\n".join(found_required + missing_required + unknown_services)
