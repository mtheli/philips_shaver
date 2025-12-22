# custom_components/philips_shaver/entity.py
from __future__ import annotations
from datetime import datetime, timedelta

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .coordinator import PhilipsShaverCoordinator
from .const import DOMAIN


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
        self._address = entry.data["address"]

        # Device-Info wird beim ersten Mal gesetzt
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            connections={(dr.CONNECTION_BLUETOOTH, self._address)},
            manufacturer="Philips",
            name="Philips Shaver",
            # Model und Firmware kommen später → werden in _handle_coordinator_update aktualisiert
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Nur wenn sich relevante Device-Daten geändert haben → Device aktualisieren
        data = self.coordinator.data

        model_changed = (
            self.device_info.get("model") != data.get("model_number")
            if self.device_info
            else True
        )
        fw_changed = (
            self.device_info.get("sw_version") != data.get("firmware")
            if self.device_info
            else True
        )

        if model_changed or fw_changed:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get_device(self._address)

            if device:
                device_registry.async_update_device(
                    device.id,
                    model=data.get("model_number") or "i9000 / XP9201",
                    sw_version=data.get("firmware"),
                )

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.data:
            return False

        # Gerät ist verfügbar, wenn wir in den letzten 5 Minuten Daten hatten
        last_seen = self.coordinator.data.get("last_seen")
        if last_seen is None:
            return False
        return (datetime.now() - last_seen).total_seconds() < 300
