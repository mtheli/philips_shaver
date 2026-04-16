# custom_components/philips_shaver/entity.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .coordinator import PhilipsShaverCoordinator
from .const import DOMAIN, CONF_ADDRESS, CONF_TRANSPORT_TYPE, TRANSPORT_ESP_BRIDGE, CONF_ESP_DEVICE_NAME, CONF_ESP_BRIDGE_ID

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

        # Set initial device info
        device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Philips",
            name="Philips Shaver",
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
        """Return True if the device is reachable (BLE range or ESP bridge data)."""

        if not self._is_esp_bridge:
            # Direct BLE: check if device is advertising
            service_info = async_last_service_info(self.hass, self._device_id)
            if service_info is not None:
                return True
        elif self.coordinator.transport.is_connected:
            # ESP bridge: trust the bridge's live connection state
            return True

        # ESP bridge / BLE fallback: check last_seen freshness (10 min timeout)
        last_seen = self.coordinator.data.get("last_seen") if self.coordinator.data else None
        if last_seen:
            return (datetime.now(timezone.utc) - last_seen).total_seconds() < 600

        return False


class PhilipsBridgeEntity(PhilipsShaverEntity):
    """Base for entities on the ESP Bridge sub-device."""

    def __init__(
        self,
        coordinator: PhilipsShaverCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        # Override device_info to register on the bridge sub-device.
        # Linking to the ESPHome parent device is done in __init__.py.
        bridge_id = entry.data.get(CONF_ESP_BRIDGE_ID, "")
        bridge_name = f"ESP Bridge ({bridge_id})" if bridge_id else "ESP Bridge"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, f"{self._device_id}_bridge")},
            name=bridge_name,
            manufacturer="Espressif",
        )

    @property
    def available(self) -> bool:
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
