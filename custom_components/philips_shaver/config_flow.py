from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import DOMAIN


class PhilipsShaverConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    _attr_flow_title = "Philips Shaver (i9000/XP9201)"

    discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # remembering the discovery info for the next step
        self.discovery_info = discovery_info

        # forwarding to the next step
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self.discovery_info is not None
        
        # on useraction
        if user_input is not None:
            return self.async_create_entry(
                title=f"Philips Shaver ({self.discovery_info.name or self.discovery_info.address})",
                data={"address": self.discovery_info.address},
            )

        # showing the form
        self.context["title_placeholders"] = {
            "name": self.discovery_info.name or self.discovery_info.address
        }
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self.discovery_info.name or self.discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input["address"].upper()

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=f"Philips Shaver ({address})",
                data={"address": address},
            )

        data_schema = vol.Schema({vol.Required("address"): str})
        return self.async_show_form(step_id="user", data_schema=data_schema)
