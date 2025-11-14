from __future__ import annotations
from typing import List

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import DOMAIN

class PhilipsShaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Philips Shaver integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Initial step: select Bluetooth device."""
        errors = {}

        if user_input is not None:
            address = user_input["device"]

            # Ensure uniqueness
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Philips Shaver ({address})",
                data={"address": address},
            )

        # Load nearby Bluetooth devices
        devices = await self._async_get_bluetooth_devices(self.hass)
        if not devices:
            errors["base"] = "no_devices_found"

        schema = vol.Schema({
            vol.Required("device"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"label": f"{d.name} ({d.address})", "value": d.address} for d in devices],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def _async_get_bluetooth_devices(self, hass: HomeAssistant) -> List[BluetoothServiceInfoBleak]:
        """Return list of BLE devices discovered by HA."""
        bt = hass.data.get("bluetooth", {})
        devices: List[BluetoothServiceInfoBleak] = []

        discovered = bt.get("discovered_devices", [])
        for dev in discovered:
            if isinstance(dev, BluetoothServiceInfoBleak):
                devices.append(dev)

        return devices
