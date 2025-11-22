# custom_components/philips_shaver/entity.py
from __future__ import annotations

from homeassistant.core import HomeAssistant, callback as hass_callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.entity import EntityCategory
from typing import Any

from .const import DOMAIN


class PhilipsShaverEntity(Entity):
    """
    Basisklasse für alle Philips Shaver Entitäten.
    Definiert die gemeinsame DeviceInfo und das Update-Handling.
    """

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialisiert die Philips Shaver Basis-Entität."""
        self.hass = hass
        self.entry = entry
        self._address = entry.data["address"]
        self._state = None

        # 1. DeviceInfo einmal zentral erstellen
        self._set_device_info(hass, entry)

        # 2. Verbindung zur Update-Dispatcher registrieren
        self._unsub = async_dispatcher_connect(
            hass,
            f"{DOMAIN}_update_{entry.entry_id}",
            self._update_callback,
        )
        
    @property
    def available(self) -> bool:
        return True

    def _set_device_info(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Erstellt das DeviceInfo-Objekt für die Entität."""
        # Holen der Service-Informationen
        service_info = async_last_service_info(hass, self._address)

        # Holen der Daten aus dem Cache (kann beim Start None sein)
        data = hass.data[DOMAIN][entry.entry_id]["data"]
        firmware = data.get("firmware")
        model_number = data.get("model_number")
        serial_number = data.get("serial_number")

        # Bestimmen des Gerätenamens (Robuster Zugriff NEU)
        device_name = None
        if service_info and service_info.name:
            device_name = service_info.name.strip()

        # Fallbacks, falls BLE-Name nicht verfügbar ist
        device_name = (
            device_name
            or model_number  # Fallback auf die geparste Modellnummer
            or f"Philips Shaver {self._address[-5:].replace(':', '').upper()}"
        )

        # DeviceInfo festlegen
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            name=device_name,
            manufacturer="Philips",
            # Verwenden der echten Modellnummer, falls vorhanden
            model=model_number or "i9000 / XP9201",
            sw_version=firmware,
            # Seriennummer hinzufügen, um das Gerät eindeutig zu machen
            serial_number=serial_number,
            configuration_url="https://github.com/mtheli/philips_shaver",
        )

    # --- Update-Handling ---
    @hass_callback
    def _update_callback(self):
        """Muss in den Kindklassen implementiert werden."""
        raise NotImplementedError

    async def async_will_remove_from_hass(self) -> None:
        """Wird aufgerufen, wenn die Entität entfernt wird."""
        self._unsub()

    # Eine zentrale Methode zum Aktualisieren der Firmware in der Device Registry
    def _update_firmware_in_registry(self, firmware: str | None) -> None:
        """Aktualisiert die Firmware-Version in der Home Assistant Device Registry."""
        if firmware:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._address)}
            )

            if device and device.sw_version != firmware:
                device_registry.async_update_device(device.id, sw_version=firmware)
