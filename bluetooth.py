import logging
from homeassistant.core import HomeAssistant
from homeassistant.components.bluetooth import async_register_callback
from .const import DOMAIN, SERVICE_UUIDS

_LOGGER = logging.getLogger(__name__)

async def async_setup_bluetooth(hass: HomeAssistant, entry_id: str):
    """Register BLE callback for Philips Shaver."""

    async def shaver_callback(service_info):
        if service_info.service_uuids:
            for uuid in SERVICE_UUIDS:
                if uuid in service_info.service_uuids:
                    _LOGGER.info("Received Philips Shaver data: %s", service_info)
                    # Hier Sensoren oder State Updates einfügen

    async_register_callback(
        hass,
        shaver_callback,
        bluetooth_service_info=None,  # Alle Geräte, Filter ggf. anpassen
    )
