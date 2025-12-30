from homeassistant.exceptions import HomeAssistantError


class PhilipsShaverException(HomeAssistantError):
    """Base class for Philips Shaver exceptions."""


class DeviceNotFoundException(PhilipsShaverException):
    """Device not found."""


class CannotConnectException(PhilipsShaverException):
    """Cannot connect to the device."""
