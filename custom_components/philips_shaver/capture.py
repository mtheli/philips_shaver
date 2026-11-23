"""Build an anonymized GATT capture of a shaver connected through the bridge.

The snapshot has the same shape as ``scripts/shaver_scan.py --fixture`` so it
can go straight into ``tests/fixtures/``: ``gatt_services[*].characteristics[*]``
with uuid/name/properties/handle/value_hex/value_text.
"""

from __future__ import annotations

import time
from typing import Any

from . import const as _const

# Placeholder MAC for anonymized captures (same as shaver_scan.py)
FIXTURE_MAC = "24:E5:AA:00:00:01"

_STANDARD_NAMES = {
    "00002a00-0000-1000-8000-00805f9b34fb": "Device Name",
    "00002a01-0000-1000-8000-00805f9b34fb": "Appearance",
    "00002a04-0000-1000-8000-00805f9b34fb": "Preferred Conn Params",
    "00002a05-0000-1000-8000-00805f9b34fb": "Service Changed",
    "00002a19-0000-1000-8000-00805f9b34fb": "Battery Level",
    "00002a23-0000-1000-8000-00805f9b34fb": "System ID",
    "00002a24-0000-1000-8000-00805f9b34fb": "Model Number",
    "00002a25-0000-1000-8000-00805f9b34fb": "Serial Number",
    "00002a26-0000-1000-8000-00805f9b34fb": "Firmware Revision",
    "00002a27-0000-1000-8000-00805f9b34fb": "Hardware Revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "Software Revision",
    "00002a29-0000-1000-8000-00805f9b34fb": "Manufacturer Name",
    "00002a2a-0000-1000-8000-00805f9b34fb": "IEEE Regulatory Cert",
    "00002a50-0000-1000-8000-00805f9b34fb": "PnP ID",
    "00002aa6-0000-1000-8000-00805f9b34fb": "Central Addr Resolution",
}
# Shown in device_info like the scan script does
_DEVICE_INFO_NAMES = {
    "Battery Level", "Model Number", "Serial Number", "Firmware Revision",
    "Hardware Revision", "Software Revision", "Manufacturer Name",
}
# Values that identify the individual unit: zeroed, length preserved
_PRIVATE_NAMES = {"Serial Number", "System ID"}
# Characteristics that hold text. Only these get value_text: arbitrary
# bytes that happen to be printable (battery 0x5a = "Z") are not text.
_TEXT_CHARS = {
    "00002a00-0000-1000-8000-00805f9b34fb",  # Device Name
    "00002a24-0000-1000-8000-00805f9b34fb",  # Model Number
    "00002a25-0000-1000-8000-00805f9b34fb",  # Serial Number
    "00002a26-0000-1000-8000-00805f9b34fb",  # Firmware Revision
    "00002a27-0000-1000-8000-00805f9b34fb",  # Hardware Revision
    "00002a28-0000-1000-8000-00805f9b34fb",  # Software Revision
    "00002a29-0000-1000-8000-00805f9b34fb",  # Manufacturer Name
    _const.CHAR_DEVICE_TYPE,                  # 0x0119
    # 0x01FD-0x01FF: NUL-padded version strings (e.g. "OLED_1.0_…")
    "8d5601fd-3cb9-4387-a7e8-b79d826a7025",
    "8d5601fe-3cb9-4387-a7e8-b79d826a7025",
    "8d5601ff-3cb9-4387-a7e8-b79d826a7025",
}
_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
_DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"

_CONST_NAMES = {
    value.lower(): name.removeprefix("CHAR_").replace("_", " ").title()
    for name, value in vars(_const).items()
    if name.startswith("CHAR_") and isinstance(value, str)
}


def _char_name(uuid: str) -> str | None:
    return _STANDARD_NAMES.get(uuid) or _CONST_NAMES.get(uuid)


def readable_chars(services: list[dict[str, Any]]) -> list[str]:
    """UUIDs of all characteristics with the read property."""
    return [
        c["uuid"]
        for s in services
        for c in s["characteristics"]
        if "read" in c["properties"]
    ]


# Requests per read batch. The bridge queues at most 64 calls
# (MAX_PENDING_CALLS) and live notifications share that queue; a full
# XP9201 table has ~74 readable characteristics, so one batch overflows it.
READ_BATCH = 12


async def async_read_values(transport: Any, readable: list[str]) -> dict[str, bytes | None]:
    """Read every characteristic in small batches, retry gaps one by one.

    Stops as soon as the shaver disconnects instead of letting each
    remaining read run into its timeout.
    """
    values: dict[str, bytes | None] = {}
    for i in range(0, len(readable), READ_BATCH):
        if not transport.is_connected:
            return values
        values.update(await transport.read_chars(readable[i:i + READ_BATCH]))
    for char_uuid in [u for u in readable if values.get(u) is None]:
        if not transport.is_connected:
            break
        values[char_uuid] = await transport.read_char(char_uuid)
    # A 0-byte value reads as None too; keep it as empty, not unreadable
    pop_empty = getattr(transport, "pop_empty_read", None)
    if pop_empty is not None:
        for char_uuid in readable:
            if values.get(char_uuid) is None and pop_empty(char_uuid):
                values[char_uuid] = b""
    return values


def _mac_patterns(mac: str | None) -> tuple[list[bytes], list[str]]:
    """Byte and text forms of the device MAC that may appear in values."""
    if not mac:
        return [], []
    try:
        octets = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    except ValueError:
        return [], []
    if len(octets) != 6:
        return [], []
    plain = octets.hex()
    texts = {
        plain, plain.upper(),
        ":".join(f"{b:02x}" for b in octets),
        ":".join(f"{b:02X}" for b in octets),
    }
    return [octets, octets[::-1]], sorted(texts, key=len, reverse=True)


def _scrub_mac(raw: bytes, mac_bytes: list[bytes], mac_texts: list[str]) -> bytes:
    """Zero every occurrence of the device MAC (binary, either byte order,
    or as hex/colon text) inside a value. Length is preserved."""
    for pattern in mac_bytes:
        raw = raw.replace(pattern, b"\x00" * len(pattern))
    for text in mac_texts:
        encoded = text.encode()
        raw = raw.replace(encoded, b"0" * len(encoded))
    return raw


def build_snapshot(
    services: list[dict[str, Any]],
    values: dict[str, bytes | None],
    *,
    mac: str | None = None,
    source: str = "esp_bridge",
) -> dict[str, Any]:
    """Assemble an anonymized capture from the GATT table and read values.

    ``mac`` is the shaver's real address: besides the address field, any
    copy of it inside a characteristic value is zeroed as well.
    """
    mac_bytes, mac_texts = _mac_patterns(mac)
    device_info: dict[str, str] = {}
    gatt_services: list[dict[str, Any]] = []
    has_legacy = False
    for service in services:
        if service["uuid"].startswith("8d56"):
            has_legacy = True
        chars = []
        for char in service["characteristics"]:
            uuid = char["uuid"]
            name = _char_name(uuid)
            raw = values.get(uuid)
            if raw:
                raw = _scrub_mac(raw, mac_bytes, mac_texts)
            value_hex = raw.hex() if raw is not None else None
            value_text = None
            if raw and uuid in _TEXT_CHARS:
                text = raw.rstrip(b"\x00").decode("utf-8", errors="replace")
                if text.strip():
                    value_text = text
            if name in _PRIVATE_NAMES and raw:
                if value_text is not None:
                    value_text = "0" * len(value_text)
                    value_hex = value_text.encode().hex()
                else:
                    value_hex = "00" * len(raw)
            if name in _DEVICE_INFO_NAMES and value_hex is not None:
                if uuid == _BATTERY_LEVEL and raw:
                    device_info[name] = f"{raw[0]}%"
                else:
                    device_info[name] = value_text if value_text is not None else value_hex
            chars.append({
                "uuid": uuid,
                "name": name,
                "properties": list(char["properties"]),
                "handle": char.get("handle"),
                "value_hex": value_hex,
                "value_text": value_text,
            })
        gatt_services.append({"uuid": service["uuid"], "characteristics": chars})

    device_name = next(
        (
            c["value_text"]
            for s in gatt_services for c in s["characteristics"]
            if c["uuid"] == _DEVICE_NAME
        ),
        None,
    )
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "address": FIXTURE_MAC,
        # Not the advertised name (the bridge does not pass that on) but
        # the GAP Device Name, which carries the same "Philips <model>".
        "adv_name": device_name,
        "protocol": (
            "Shaver Legacy (8d56…, supported by philips_shaver)"
            if has_legacy else "Unknown"
        ),
        "source": source,
        "device_info": device_info,
        "gatt_services": gatt_services,
    }
