# config/custom_components/philips_shaver/utils.py
import struct
from dataclasses import dataclass


def parse_color(value: bytes | None):
    """Parse Philips RGBA into an (r, g, b) tuple."""
    if not value or len(value) < 3:
        return None

    # Philips liefert RGBA -> letzte Byte ignorieren
    return (value[0], value[1], value[2])


def parse_shaving_settings_to_dict(value: bytes) -> dict:
    """
    Parses the 10-byte shaving mode settings and returns a normalized dictionary.
    """
    # Checking for the proper length (10 Bytes = 5x UINT16)
    if len(value) != 10:
        return {"error": "Invalid data length"}

    # <HHHHH: Little Endian, 5x Unsigned Short (2 Bytes each)
    # m_raw: Motor RPM Raw
    # p_none: Pressure Base/Zero
    # p_low: Lower Green Zone Threshold
    # p_high: Upper Green Zone Threshold
    # p_verdict: Analysis Window/Verdict
    m_raw, p_none, p_low, p_high, p_verdict = struct.unpack("<HHHHH", value)

    return {
        "custom_motor_rpm": int(round(m_raw / 3.036)),
        "pressure_base_value": p_none,
        "pressure_limit_low": p_low,
        "pressure_limit_high": p_high,
        "feedback_analysis_window": p_verdict,
        "raw_motor_value": m_raw,
    }


@dataclass
class ShaverCapabilities:
    """Helper class to represent shaver capabilities."""

    motion: bool = False
    brush: bool = False
    motion_speed: bool = False
    pressure: bool = False
    unit_cleaning: bool = False
    cleaning_mode: bool = False
    light_ring: bool = False


# In deiner PhilipsShaverCoordinator Klasse:
def parse_capabilities(raw_value: bytes) -> ShaverCapabilities:
    """Interpretiert den UINT32 Capability-Wert."""
    val = int.from_bytes(raw_value, "little")
    return ShaverCapabilities(
        motion=bool(val & (1 << 0)),
        brush=bool(val & (1 << 1)),
        motion_speed=bool(val & (1 << 2)),
        pressure=bool(val & (1 << 3)),
        unit_cleaning=bool(val & (1 << 4)),
        cleaning_mode=bool(val & (1 << 5)),
        light_ring=bool(val & (1 << 6)),
    )
