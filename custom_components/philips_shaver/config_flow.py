from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
    TextSelector,
)

from .const import (
    DOMAIN,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_ENABLE_LIVE_UPDATES,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    CONF_ADDRESS,
    CONF_POLL_INTERVAL,
    CONF_ENABLE_LIVE_UPDATES,
)


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

    # --- Korrigierte Hilfsfunktion zum Prüfen des Pairing-Status ---
    def _is_device_bonded(self, discovery_info: BluetoothServiceInfoBleak) -> bool:
        """Check if the Bluetooth device is bonded/paired on the host OS."""

        # 1. Plattformdaten abrufen (enthält bei BlueZ manchmal ein Tupel)
        platform_data = getattr(discovery_info.advertisement, "platform_data", {})

        properties = {}

        # 2. Prüfen, ob es das BlueZ-Tupel-Format ist: (path, properties_dict)
        if (
            isinstance(platform_data, tuple)
            and len(platform_data) == 2
            and isinstance(platform_data[1], dict)
        ):
            # Das Properties-Dictionary ist das zweite Element (Index 1)
            properties = platform_data[1]

        # 3. Ansonsten davon ausgehen, dass es bereits das Dictionary ist
        elif isinstance(platform_data, dict):
            properties = platform_data

        # 4. Wenn keine der Formen zutrifft, ist der Status unbekannt (False)
        else:
            return False

        # 5. Nun sicher auf 'Paired' und 'Bonded' zugreifen
        # Der Benutzer-Log bestätigt: Paired: False, Bonded: False, wenn entkoppelt
        return properties.get("Paired", False) and properties.get("Bonded", False)

    # =============================================================================
    # 1. AUTOMATISCHE ERKENNUNG (async_step_bluetooth)
    # =============================================================================
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        # Eindeutige ID basierend auf der MAC-Adresse setzen und Duplikate abbrechen
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # Discovery-Informationen für die folgenden Schritte speichern
        self.discovery_info = discovery_info

        # Wenn das Gerät NICHT gebunden ist, zeige die Warnung an
        if not self._is_device_bonded(discovery_info):
            return await self.async_step_bluetooth_unpaired()

        # Wenn das Gerät gebunden ist, fordere die Bestätigung an
        return await self.async_step_bluetooth_confirm()

    # =============================================================================
    # 2a. FEHLENDES PAIRING WARNUNG (async_step_bluetooth_unpaired)
    # =============================================================================
    async def async_step_bluetooth_unpaired(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Warn the user that the device must be paired on the host OS first."""
        assert self.discovery_info is not None

        # Wenn der Benutzer auf "Senden" klickt, prüfen wir erneut
        if user_input is not None:
            # Wenn es JETZT gekoppelt ist, fahren wir fort
            if self._is_device_bonded(self.discovery_info):
                return await self.async_step_bluetooth_confirm()

            # Immer noch nicht gekoppelt, aber Benutzer hat bestätigt: Eintrag erstellen
            # (Dies ermöglicht es dem Benutzer, die Warnung zu ignorieren, wenn er sicher ist)
            return self.async_create_entry(
                title=f"Philips Shaver ({self.discovery_info.name or self.discovery_info.address})",
                data={CONF_ADDRESS: self.discovery_info.address},
                options={
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                    CONF_ENABLE_LIVE_UPDATES: DEFAULT_ENABLE_LIVE_UPDATES,
                },
            )

        # Zeige das Warnformular an
        self.context["title_placeholders"] = {
            "name": self.discovery_info.name or self.discovery_info.address
        }
        return self.async_show_form(
            step_id="bluetooth_unpaired",
            description_placeholders={
                "name": self.discovery_info.name or self.discovery_info.address,
            },
            # Leeres Schema, um einen "Senden"-Button anzuzeigen
            data_schema=vol.Schema({}),
        )

    # =============================================================================
    # 2b. BESTÄTIGUNG (async_step_bluetooth_confirm)
    # =============================================================================
    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self.discovery_info is not None

        # Wenn der Benutzer die Bestätigung abschickt (auf "Senden" klickt)
        if user_input is not None:
            return self.async_create_entry(
                title=f"Philips Shaver ({self.discovery_info.name or self.discovery_info.address})",
                data={CONF_ADDRESS: self.discovery_info.address},
                options={
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                    CONF_ENABLE_LIVE_UPDATES: DEFAULT_ENABLE_LIVE_UPDATES,
                },
            )

        # Zeige das Bestätigungsformular an
        self.context["title_placeholders"] = {
            "name": self.discovery_info.name or self.discovery_info.address
        }

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self.discovery_info.name or self.discovery_info.address,
            },
        )

    # =============================================================================
    # 3. MANUELLE EINGABE (async_step_user)
    # =============================================================================
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user (manual MAC address entry)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input["address"].upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            # WICHTIG: Manuelle Eingabe überspringt den Pairing-Check und die Bestätigung
            # Da der Benutzer die Adresse manuell eingibt, wird davon ausgegangen,
            # dass er die Pairing-Anforderungen kennt (gemäß Readme).
            return self.async_create_entry(
                title=f"Philips Shaver ({address})",
                data={"address": address},
                options={
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                    CONF_ENABLE_LIVE_UPDATES: DEFAULT_ENABLE_LIVE_UPDATES,
                },
            )

        data_schema = vol.Schema({vol.Required("address"): str})
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,  # Fehler können hier eingefügt werden, falls nötig
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> PhilipsShaverOptionsFlow:
        """Create the options flow."""
        return PhilipsShaverOptionsFlow()
