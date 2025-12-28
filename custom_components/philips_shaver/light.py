from __future__ import annotations

import logging
from datetime import datetime
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    LightEntityFeature,
)
from .coordinator import PhilipsShaverCoordinator

from .entity import PhilipsShaverEntity
from .const import (
    DOMAIN,
    CHAR_LIGHTRING_COLOR_LOW,
    CHAR_LIGHTRING_COLOR_OK,
    CHAR_LIGHTRING_COLOR_HIGH,
    CHAR_LIGHTRING_COLOR_MOTION,
    CHAR_LIGHTRING_COLOR_BRIGHTNESS,
    LIGHTRING_DEFAULT_COLORS,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SETUP ENTRY: register all four LightEntities
# ---------------------------------------------------------------------------
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [
        PhilipsColorConfigLight(
            coordinator,
            entry,
            CHAR_LIGHTRING_COLOR_LOW,
            "color_low",
        ),
        PhilipsColorConfigLight(
            coordinator,
            entry,
            CHAR_LIGHTRING_COLOR_OK,
            "color_ok",
        ),
        PhilipsColorConfigLight(
            coordinator,
            entry,
            CHAR_LIGHTRING_COLOR_HIGH,
            "color_high",
        ),
        PhilipsColorConfigLight(
            coordinator,
            entry,
            CHAR_LIGHTRING_COLOR_MOTION,
            "color_motion",
        ),
    ]

    # checking if light ring capability is supported
    if coordinator.capabilities.light_ring:
        async_add_entities(entities)
    else:
        _LOGGER.info(
            "Shaver does not support light ring configuration – skipping light entities"
        )


# ---------------------------------------------------------------------------
# LIGHT ENTITY: Color configuration Light
# ---------------------------------------------------------------------------
class PhilipsColorConfigLight(PhilipsShaverEntity, LightEntity):
    """
    LightEntity that maps directly to one of the Philips Shaver's
    RGB color configuration GATT characteristics.
    """

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = False

    def __init__(
        self,
        coordinator: PhilipsShaverCoordinator,
        entry: ConfigEntry,
        uuid: str,
        translation_key: str,
    ) -> None:
        super().__init__(coordinator, entry)

        self._uuid = uuid
        self._attr_translation_key = translation_key

        # Unique ID keeps HA happy
        self._attr_unique_id = f"{self._address}_{uuid}"

        # Default color until read (future improvement)
        key = {
            CHAR_LIGHTRING_COLOR_LOW: "color_low",
            CHAR_LIGHTRING_COLOR_OK: "color_ok",
            CHAR_LIGHTRING_COLOR_HIGH: "color_high",
            CHAR_LIGHTRING_COLOR_MOTION: "color_motion",
        }[uuid]
        self._rgb = self.coordinator.data.get(key) or LIGHTRING_DEFAULT_COLORS[uuid]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Wird automatisch bei jedem Coordinator-Update aufgerufen."""
        key_map = {
            CHAR_LIGHTRING_COLOR_LOW: "color_low",
            CHAR_LIGHTRING_COLOR_OK: "color_ok",
            CHAR_LIGHTRING_COLOR_HIGH: "color_high",
            CHAR_LIGHTRING_COLOR_MOTION: "color_motion",
        }
        key = key_map.get(self._uuid)
        if key:
            rgb = self.coordinator.data.get(key)
            if rgb and rgb != self._rgb:
                self._rgb = rgb
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Current RGB value shown in the UI
    # ------------------------------------------------------------------
    @property
    def rgb_color(self) -> tuple[int, int, int]:
        return self._rgb

    @property
    def is_on(self):
        return True

    @property
    def supported_features(self) -> LightEntityFeature:
        return LightEntityFeature(0)

    # ------------------------------------------------------------------
    # Turn ON = set color
    # ------------------------------------------------------------------
    async def async_turn_on(self, **kwargs) -> None:
        """Set new RGB color on the shaver."""
        client = self.coordinator.live_client

        if not client or not client.is_connected:
            _LOGGER.warning(
                "Shaver not connected – cannot write color %s (%s)",
                self._attr_translation_key,
                self._uuid,
            )
            return

        if "rgb_color" not in kwargs:
            # Nur anschalten ohne Farbänderung → nichts tun (Licht ist immer "an")
            return

        r, g, b = kwargs["rgb_color"]

        # Philips erwartet RGBA mit letztem Byte = 0xFF
        payload = bytes([r, g, b, 0xFF])

        try:
            await client.write_gatt_char(self._uuid, payload)
            _LOGGER.info(
                "Color %s set to (%d, %d, %d) → characteristic %s",
                self._attr_translation_key,
                r,
                g,
                b,
                self._uuid,
            )
        except Exception as e:
            _LOGGER.error("Failed to write color %s: %s", self._attr_translation_key, e)
            return  # Nicht lokal updaten, wenn Schreiben fehlgeschlagen ist

        # Erfolgreich geschrieben → sofort im Coordinator aktualisieren
        key_map = {
            CHAR_LIGHTRING_COLOR_LOW: "color_low",
            CHAR_LIGHTRING_COLOR_OK: "color_ok",
            CHAR_LIGHTRING_COLOR_HIGH: "color_high",
            CHAR_LIGHTRING_COLOR_MOTION: "color_motion",
        }
        key = key_map[self._uuid]

        new_data = self.coordinator.data.copy()
        new_data[key] = (r, g, b)
        new_data["last_seen"] = datetime.now()

        self.coordinator.async_set_updated_data(new_data)

        # Lokalen Cache aktualisieren (für rgb_color-Property
        self._rgb = (r, g, b)

    # ------------------------------------------------------------------
    # Turning off has no meaning for this type of configuration light
    # ------------------------------------------------------------------
    async def async_turn_off(self, **kwargs) -> None:
        # Optional: you could write 00-00-00-FF here, but better leave unchanged
        return
