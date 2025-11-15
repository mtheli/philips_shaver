from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import DOMAIN


class PhilipsShaverConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Philips Shaver ({discovery_info.name or discovery_info.address})",
            data={"address": discovery_info.address},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
