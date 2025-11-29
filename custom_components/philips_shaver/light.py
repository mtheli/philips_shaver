from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant, callback as hass_callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    LightEntityFeature,
)

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
    entities = [
        PhilipsColorConfigLight(
            hass,
            entry,
            CHAR_LIGHTRING_COLOR_LOW,
            "color_low",
        ),
        PhilipsColorConfigLight(
            hass,
            entry,
            CHAR_LIGHTRING_COLOR_OK,
            "color_ok",
        ),
        PhilipsColorConfigLight(
            hass,
            entry,
            CHAR_LIGHTRING_COLOR_HIGH,
            "color_high",
        ),
        PhilipsColorConfigLight(
            hass,
            entry,
            CHAR_LIGHTRING_COLOR_MOTION,
            "color_motion",
        ),
    ]

    async_add_entities(entities)


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
        hass: HomeAssistant,
        entry: ConfigEntry,
        uuid: str,
        translation_key: str,
    ) -> None:
        super().__init__(hass, entry)

        self._uuid = uuid
        self._attr_translation_key = translation_key

        # Unique ID keeps HA happy
        self._attr_unique_id = f"{self._address}_{uuid}"

        # Default color until read (future improvement)
        self._rgb = LIGHTRING_DEFAULT_COLORS[uuid]

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

    @hass_callback
    def _update_callback(self):
        hass = self.hass
        
        if hass is None or DOMAIN not in hass.data:
            return

        entry_data = hass.data[DOMAIN].get(self.entry.entry_id)
        if entry_data is None or entry_data.get("data") is None:
            return

        store = self.hass.data[DOMAIN][self.entry.entry_id]["data"]

        if self._uuid == CHAR_LIGHTRING_COLOR_LOW:
            rgb = store.get("color_low")
        elif self._uuid == CHAR_LIGHTRING_COLOR_OK:
            rgb = store.get("color_ok")
        elif self._uuid == CHAR_LIGHTRING_COLOR_HIGH:
            rgb = store.get("color_high")
        elif self._uuid == CHAR_LIGHTRING_COLOR_MOTION:
            rgb = store.get("color_motion")
        # else:
        #   rgb = None

        if rgb:
            self._rgb = rgb

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Turn ON = set color
    # ------------------------------------------------------------------
    async def async_turn_on(self, **kwargs) -> None:
        store = self.hass.data[DOMAIN][self.entry.entry_id]
        client = store.get("live_client")

        if not client or not client.is_connected:
            _LOGGER.warning(
                "Shaver not connected – cannot write color %s (%s)",
                self._attr_name,
                self._uuid,
            )
            return

        if "rgb_color" in kwargs:
            r, g, b = kwargs["rgb_color"]
            self._rgb = (r, g, b)

            # Philips uses RGBA with last byte = 0xFF
            payload = bytes([r, g, b, 0xFF])

            try:
                await client.write_gatt_char(self._uuid, payload)
                _LOGGER.info(
                    "Color %s updated to %s for characteristic %s",
                    self._attr_name,
                    self._rgb,
                    self._uuid,
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed writing color for %s: %s",
                    self._attr_name,
                    e,
                )

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Turning off has no meaning for this type of configuration light
    # ------------------------------------------------------------------
    async def async_turn_off(self, **kwargs) -> None:
        # Optional: you could write 00-00-00-FF here, but better leave unchanged
        return
