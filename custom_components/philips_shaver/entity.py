# custom_components/philips_shaver/entity.py
from __future__ import annotations

import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .coordinator import PhilipsShaverCoordinator
from .const import DOMAIN, CONF_ADDRESS, CONF_TRANSPORT_TYPE, TRANSPORT_ESP_BRIDGE, CONF_ESP_DEVICE_NAME, CONF_ESP_BRIDGE_ID, CONF_DEVICE_NAME

_LOGGER = logging.getLogger(__name__)


class PhilipsShaverEntity(CoordinatorEntity[PhilipsShaverCoordinator]):
    """Base class for all Philips Shaver entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PhilipsShaverCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._is_esp_bridge = (
            entry.data.get(CONF_TRANSPORT_TYPE) == TRANSPORT_ESP_BRIDGE
        )

        # Device identifier: shaver MAC (preferred) or esp_device_name fallback
        if self._is_esp_bridge:
            self._device_id = entry.data.get(CONF_ADDRESS) or entry.data[CONF_ESP_DEVICE_NAME]
        else:
            self._device_id = entry.data["address"]

        # User-chosen name (set during setup). For pre-name entries fall back
        # to a bridge_id-disambiguated default so multi-device households stay
        # distinguishable instead of all reading "Philips Shaver".
        device_name = entry.data.get(CONF_DEVICE_NAME)
        if not device_name:
            bridge_id = entry.data.get(CONF_ESP_BRIDGE_ID, "")
            device_name = f"Philips Shaver ({bridge_id})" if bridge_id else "Philips Shaver"
        self._device_name = device_name

        # Set initial device info
        device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Philips",
            name=self._device_name,
        )
        if not self._is_esp_bridge:
            device_info["connections"] = {(dr.CONNECTION_BLUETOOTH, self._device_id)}
        else:
            # Add BLE connection if shaver MAC is known (auto-detected or migrated)
            shaver_mac = entry.data.get(CONF_ADDRESS)
            if shaver_mac:
                device_info["connections"] = {(dr.CONNECTION_BLUETOOTH, shaver_mac)}
        self._attr_device_info = device_info

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Dynamic icon update
        if hasattr(self, "icon"):
            try:
                new_icon = self.icon
                if getattr(self, "_attr_icon", None) != new_icon:
                    self._attr_icon = new_icon
            except Exception as err:
                _LOGGER.debug(
                    "Failed to update dynamic icon for %s: %s",
                    self.entity_id or self.__class__.__name__,
                    err,
                )

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return True once the device has ever been seen.

        The shaver is a sleepy device — it is out of BLE reach between
        sessions as its normal state, so availability can't hinge on being
        currently reachable (same reasoning as core's Oral-B integration).
        Once it has been seen — live or restored from storage — the last
        known values stay available; live connectivity is exposed on the
        Connection sub-device instead.
        """
        if self.coordinator.data and self.coordinator.data.get("last_seen"):
            return True

        # Never seen (fresh install): fall back to reachability
        if self._is_esp_bridge:
            return self.coordinator.transport.is_connected
        return async_last_service_info(self.hass, self._device_id) is not None


class PhilipsConnectionEntity(PhilipsShaverEntity):
    """Base class for entities on the Connection sub-device.

    Groups transport-level diagnostics (adapter, RSSI, link status) on a
    dedicated device so the main device only shows shaver state.

    Identifier is kept as `{device_id}_bridge` (historical) so existing ESP
    Bridge installations keep their registry entries without a migration.
    """

    def __init__(
        self,
        coordinator: PhilipsShaverCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        # Inherit the parent device's name so the Connection sub-device reads
        # "<Name> Connection" (e.g. "Bathroom Shaver Connection"), matching
        # the Sonicare sub-device naming convention.
        manufacturer = "Espressif" if self._is_esp_bridge else "Home Assistant"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, f"{self._device_id}_bridge")},
            manufacturer=manufacturer,
            name=f"{self._device_name} Connection",
        )

    @property
    def available(self) -> bool:
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


# Backwards-compat alias for any out-of-tree imports
PhilipsBridgeEntity = PhilipsConnectionEntity
