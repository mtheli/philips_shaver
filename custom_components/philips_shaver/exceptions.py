from homeassistant.exceptions import HomeAssistantError


class PhilipsShaverException(HomeAssistantError):
    """Base class for Philips Shaver exceptions."""


class DeviceNotFoundException(PhilipsShaverException):
    """Device not found."""


class CannotConnectException(PhilipsShaverException):
    """Cannot connect to the device."""


class NotPairedException(PhilipsShaverException):
    """Device is not paired at OS level."""


class DeviceAsleepException(PhilipsShaverException):
    """No recent connectable advertisement — the shaver is asleep/unreachable."""


class TransportError(PhilipsShaverException):
    """Transport-level communication error."""


class AdapterNotReceivingException(PhilipsShaverException):
    """The fixed Bluetooth adapter does not receive the shaver."""
