# custom_components/philips_shaver/select.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CHAR_SHAVING_MODE, SHAVING_MODES
from .entity import PhilipsShaverEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips Shaver select platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([PhilipsShavingModeSelect(coordinator, entry)])


class PhilipsShavingModeSelect(PhilipsShaverEntity, SelectEntity):
    """Steuerung des Rasiermodus (Sanft, Normal, Intensiv, Persönlich, Schaum)."""

    _attr_translation_key = "shaving_mode"
    _attr_options = ["sensitive", "regular", "intense", "custom", "foam"]

    def __init__(self, coordinator: Any, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._address}_shaving_mode_select"

    @property
    def current_option(self) -> str | None:
        """Gibt den aktuell im Coordinator gespeicherten Modus zurück."""
        mode_id = self.coordinator.data.get("shaving_mode_value")

        # Mapping basierend auf der Sensor-Logik
        return SHAVING_MODES.get(mode_id)

    async def async_select_option(self, option: str) -> None:
        """Sendet den gewählten Modus an den Rasierer – Muster aus light.py."""
        client = self.coordinator.live_client

        # 1. Verbindung prüfen
        if not client or not client.is_connected:
            _LOGGER.warning(
                "Shaver not connected – cannot set shaving mode to %s", option
            )
            return

        # 2. Mapping der Auswahl auf Hex-Werte (sensitive=0x00)
        write_mapping = {
            "sensitive": 0x00,
            "regular": 0x01,
            "intense": 0x02,
            "custom": 0x03,
            "foam": 0x04,
        }

        val = write_mapping.get(option)
        if val is None:
            return

        # 3. Schreibvorgang ausführen
        try:
            await client.write_gatt_char(CHAR_SHAVING_MODE, bytes([val]))
            _LOGGER.info("Shaving mode set to %s (0x%02x)", option, val)
        except Exception as e:
            _LOGGER.error("Failed to write shaving mode %s: %s", option, e)
            return

        # 4. Coordinator sofort lokal aktualisieren
        new_data = self.coordinator.data.copy()
        new_data["shaving_mode_value"] = val
        new_data["shaving_mode"] = option
        new_data["last_seen"] = datetime.now()

        self.coordinator.async_set_updated_data(new_data)

    @property
    def icon(self) -> str:
        """Nutzt die dynamische Icon-Logik deiner Sensor-Klasse."""
        mode_id = self.coordinator.data.get("shaving_mode_value")
        ICONS = {
            0: "mdi:feather",  # sensitive
            1: "mdi:face-man",  # regular
            2: "mdi:lightning-bolt",  # intense
            3: "mdi:tune",  # custom
            4: "mdi:spray",  # foam
        }
        return ICONS.get(mode_id, "mdi:face-man")
