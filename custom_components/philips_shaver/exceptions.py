from homeassistant.exceptions import HomeAssistantError


class PhilipsShaverException(HomeAssistantError):
    """Base class for Philips Shaver exceptions."""


class DeviceNotFoundException(PhilipsShaverException):
    """Device not found."""


class CannotConnectException(PhilipsShaverException):
    """Cannot connect to the device."""


class NotPairedException(PhilipsShaverException):
    """Device is not paired at OS level."""


class TransportError(PhilipsShaverException):
    """Transport-level communication error."""
