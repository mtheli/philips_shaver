#!/usr/bin/env python3
"""Scan and enumerate GATT services on any Philips shaver / OneBlade.

For devices that expose the newer (e50b…) transport, this script also
probes the device for available products, ports and properties — the
same flow as used on Philips Sonicare toothbrushes. The shaver range is
not known to ship this protocol yet; probing is still useful to check
whether any future model does.

Usage:
  python3 shaver_scan.py              # Auto-detect nearby Philips shaver/OneBlade
  python3 shaver_scan.py AA:BB:CC:DD:EE:FF  # Scan specific MAC address
  python3 shaver_scan.py AA:BB:CC:DD:EE:FF --fixture xp9201.json
                                      # Capture an anonymized test fixture
                                      # for tests/fixtures/

Requirements:
  pip install bleak
"""

import asyncio
import json
import struct
import argparse
import subprocess
import sys
import time
import warnings
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakCharacteristicNotFoundError, BleakError

# Import the integration's D-Bus auto-confirm pairing helper from
# `custom_components/philips_shaver/dbus_pairing.py`. Bleak's built-in
# `client.pair()` does not register an Agent1, so it cannot auto-confirm
# the Just-Works/Numeric-Comparison flow the shavers use — pairing fails
# with AuthenticationFailed and BlueZ tears the link down.
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "philips_shaver"
    ),
)
try:
    from dbus_pairing import (  # type: ignore[import-not-found]
        async_pair_and_trust,
        is_dbus_available,
        PairingError,
    )
    HAS_DBUS_PAIRING = True
except Exception as _imp_err:  # pragma: no cover
    HAS_DBUS_PAIRING = False
    _DBUS_IMPORT_ERR = _imp_err

# --- Protocol detection ------------------------------------------------
# Shaver-range Philips devices advertise one or more of the 8d56xxxx
# services; the integration lists these in its manifest.
SHAVER_LEGACY_SERVICES = {
    "8d560100-3cb9-4387-a7e8-b79d826a7025",  # Platform Service
    "8d560200-3cb9-4387-a7e8-b79d826a7025",  # History Service
    "8d560300-3cb9-4387-a7e8-b79d826a7025",  # Control Service
    "8d560600-3cb9-4387-a7e8-b79d826a7025",  # Serial/Diagnostic Service
    "8d560700-3cb9-4387-a7e8-b79d826a7025",  # Smart Groomer Service (OneBlade)
}
SHAVER_LEGACY_PREFIX = "8d56"
NEWER_PREFIX = "e50ba3c0"

# Device name prefixes seen on the user's devices; used as a secondary
# match when advertisements don't carry service UUIDs.
SHAVER_NAME_HINTS = (
    "philips",
    "oneblade",
    "shaver",
)

# --- Newer (Condor) protocol BLE UUIDs ---
CHAR_RX = "e50b0001-af04-4564-92ad-fef019489de6"
CHAR_RX_ACK = "e50b0002-af04-4564-92ad-fef019489de6"
CHAR_TX = "e50b0003-af04-4564-92ad-fef019489de6"
CHAR_TX_ACK = "e50b0004-af04-4564-92ad-fef019489de6"
CHAR_PROTO_CFG = "e50b0005-af04-4564-92ad-fef019489de6"
CHAR_SERVER_CFG = "e50b0006-af04-4564-92ad-fef019489de6"
CHAR_CLIENT_CFG = "e50b0007-af04-4564-92ad-fef019489de6"

# --- Newer protocol message types ---
MSG_INITIALIZE_REQ = 1
MSG_INITIALIZE_RESP = 2
MSG_GET_PROPS = 4
MSG_SUBSCRIBE = 5
MSG_UNSUBSCRIBE = 6
MSG_GENERIC_RESP = 7
MSG_CHANGE_IND = 8
MSG_CHANGE_IND_RESP = 9
MSG_GET_PRODS = 10
MSG_GET_PORTS = 11

SUBSCRIBE_TIMEOUT_SECS = 31_536_000

MSG_NAMES = {
    1: "InitializeReq", 2: "InitializeResp", 3: "PutProps", 4: "GetProps",
    5: "Subscribe", 6: "Unsubscribe", 7: "GenericResp", 8: "ChangeIndReq",
    9: "ChangeIndResp", 10: "GetProds", 11: "GetPorts", 12: "AddProps",
    13: "DelProps", 15: "RawRequest",
}

STATUS_NAMES = {
    0: "NoError", 1: "NotUnderstood", 2: "OutOfMemory", 3: "NoSuchPort",
    4: "NotImplemented", 5: "VersionNotSupported", 6: "NoSuchProperty",
    7: "NoSuchOperation", 8: "NoSuchProduct", 9: "PropertyAlreadyExists",
    10: "NoSuchMethod", 11: "WrongParameters", 12: "InvalidParameter",
    13: "NotSubscribed", 14: "ProtocolViolation", 255: "Unknown",
}


# =====================================================================
# Known characteristic registry (mirrors const.py from the integration)
# =====================================================================

_DEVICE_STATES = {1: "off", 2: "shaving", 3: "charging"}
_TRAVEL_LOCK = {0: "unlocked", 1: "locked"}
_SHAVING_MODES = {
    0: "sensitive", 1: "regular", 2: "intense",
    3: "custom", 4: "foam", 5: "battery_saving",
}
_HANDLE_LOAD_TYPES = {
    0: "not_supported", 1: "undefined", 2: "detection_in_progress",
    3: "trimmer", 4: "shaving_heads", 5: "styler", 6: "brush",
    7: "precision_trimmer", 8: "beardstyler",
    9: "precision_trimmer_or_beardstyler", 65535: "no_load",
}
_SPEED_VERDICTS = {0: "optimal", 1: "too_fast", 2: "none"}
_LIGHTRING_BRIGHTNESS = {0xFF: "high", 0xCD: "medium", 0x9B: "low"}
_SYSTEM_NOTIF_BITS = [
    (0, "motor_blocked"),
    (1, "clean_reminder"),
    (2, "head_replacement"),
    (3, "battery_overheated"),
    (4, "unplug_before_use"),
]


def _dec_enum(mapping):
    return lambda d: mapping.get(d[0], f"unknown({d[0]})") if d else "?"


def _dec_enum_u16(mapping):
    def _inner(d):
        if len(d) < 2:
            return d.hex()
        v = struct.unpack("<H", d[:2])[0]
        return mapping.get(v, f"unknown({v})")
    return _inner


def _dec_u8(d):
    return str(d[0]) if d else "?"


def _dec_u16(d):
    return str(struct.unpack("<H", d[:2])[0]) if len(d) >= 2 else d.hex()


def _dec_u16_sec(d):
    return f"{struct.unpack('<H', d[:2])[0]}s" if len(d) >= 2 else d.hex()


def _dec_u32(d):
    return str(struct.unpack("<I", d[:4])[0]) if len(d) >= 4 else d.hex()


def _dec_str(d):
    return d.decode("utf-8", errors="replace")


def _dec_pct(d):
    return f"{d[0]}%" if d else "?"


def _dec_rgba(d):
    if len(d) < 4:
        return d.hex()
    r, g, b, a = d[0], d[1], d[2], d[3]
    return f"RGBA=#{r:02X}{g:02X}{b:02X}{a:02X}"


def _dec_system_notifications(d):
    if not d:
        return "?"
    raw = d[:4].ljust(4, b"\x00")
    v = struct.unpack("<I", raw)[0]
    flags = [name for bit, name in _SYSTEM_NOTIF_BITS if v & (1 << bit)]
    return f"0x{v:08X} → [{', '.join(flags) or 'none'}]"


def _dec_app_handle_settings(d):
    if not d:
        return "?"
    if len(d) >= 4:
        v = struct.unpack("<I", d[:4])[0]
    else:
        v = d[0]
    flags = []
    if v & (1 << 0): flags.append("notif_suppression")
    if v & (1 << 1): flags.append("realtime_guidance_sound")
    if v & (1 << 2): flags.append("post_shave_feedback_sound")
    if v & (1 << 3): flags.append("post_shave_feedback_haptic")
    if v & (1 << 4): flags.append("full_coaching")
    if v & (1 << 5): flags.append("max_pressure_coaching")
    if v & (1 << 6): flags.append("auto_unit_detection")
    if v & (1 << 7): flags.append("star_rating_verdict")
    if v & (1 << 8): flags.append("full_motion_coaching")
    if v & (1 << 9): flags.append("max_motion_coaching")
    if v & (1 << 10): flags.append("bit10_unknown")
    return f"0x{v:X} → [{', '.join(flags) or 'none'}]"


# UUID → (display_name, category, decode_fn_or_None)
# category: "device_info" | "standard_ble" | "legacy" | "newer_proto"
KNOWN_CHARS = {
    # Standard BLE — Generic Access / Generic Attribute / common
    "00002a00-0000-1000-8000-00805f9b34fb": ("Device Name",             "standard_ble", _dec_str),
    "00002a01-0000-1000-8000-00805f9b34fb": ("Appearance",              "standard_ble", None),
    "00002a04-0000-1000-8000-00805f9b34fb": ("Preferred Conn Params",   "standard_ble", None),
    "00002a05-0000-1000-8000-00805f9b34fb": ("Service Changed",         "standard_ble", None),
    "00002a23-0000-1000-8000-00805f9b34fb": ("System ID",               "standard_ble", None),
    "00002a2a-0000-1000-8000-00805f9b34fb": ("IEEE Regulatory Cert",    "standard_ble", None),
    "00002a50-0000-1000-8000-00805f9b34fb": ("PnP ID",                  "standard_ble", None),
    "00002aa6-0000-1000-8000-00805f9b34fb": ("Central Addr Resolution", "standard_ble", None),
    # Standard BLE — Device Information / Battery
    "00002a19-0000-1000-8000-00805f9b34fb": ("Battery Level",           "device_info", _dec_pct),
    "00002a24-0000-1000-8000-00805f9b34fb": ("Model Number",            "device_info", _dec_str),
    "00002a25-0000-1000-8000-00805f9b34fb": ("Serial Number",           "device_info", _dec_str),
    "00002a26-0000-1000-8000-00805f9b34fb": ("Firmware Revision",       "device_info", _dec_str),
    "00002a27-0000-1000-8000-00805f9b34fb": ("Hardware Revision",       "device_info", _dec_str),
    "00002a28-0000-1000-8000-00805f9b34fb": ("Software Revision",       "device_info", _dec_str),
    "00002a29-0000-1000-8000-00805f9b34fb": ("Manufacturer Name",       "device_info", _dec_str),
    # Platform Service (0x0100) — legacy
    "8d560102-3cb9-4387-a7e8-b79d826a7025": ("Motor Current",           "legacy", _dec_u16),
    "8d560103-3cb9-4387-a7e8-b79d826a7025": ("Motor Current Max",       "legacy", _dec_u16),
    "8d560104-3cb9-4387-a7e8-b79d826a7025": ("Motor RPM",               "legacy", _dec_u16),
    "8d560105-3cb9-4387-a7e8-b79d826a7025": ("Motor RPM Max",           "legacy", _dec_u16),
    "8d560106-3cb9-4387-a7e8-b79d826a7025": ("Total Age",               "legacy", _dec_u32),
    "8d560107-3cb9-4387-a7e8-b79d826a7025": ("Operational Turns",       "legacy", _dec_u16),
    "8d560108-3cb9-4387-a7e8-b79d826a7025": ("Days Since Last Used",    "legacy", _dec_u16),
    "8d560109-3cb9-4387-a7e8-b79d826a7025": ("Amount of Charges",       "legacy", _dec_u16),
    "8d56010a-3cb9-4387-a7e8-b79d826a7025": ("Device State",            "legacy", _dec_enum(_DEVICE_STATES)),
    "8d56010c-3cb9-4387-a7e8-b79d826a7025": ("Travel Lock",             "legacy", _dec_enum(_TRAVEL_LOCK)),
    "8d56010d-3cb9-4387-a7e8-b79d826a7025": ("Cleaning Reminder",       "legacy", None),
    "8d56010e-3cb9-4387-a7e8-b79d826a7025": ("Blade Replacement",       "legacy", None),
    "8d56010f-3cb9-4387-a7e8-b79d826a7025": ("Shaving Time",            "legacy", _dec_u16_sec),
    "8d560110-3cb9-4387-a7e8-b79d826a7025": ("System Notifications",    "legacy", _dec_system_notifications),
    "8d560117-3cb9-4387-a7e8-b79d826a7025": ("Head Remaining",          "legacy", _dec_u8),
    "8d560118-3cb9-4387-a7e8-b79d826a7025": ("Head Remaining Minutes",  "legacy", _dec_u16),
    "8d560119-3cb9-4387-a7e8-b79d826a7025": ("Device Type",             "legacy", _dec_str),
    "8d56011a-3cb9-4387-a7e8-b79d826a7025": ("Cleaning Progress",       "legacy", _dec_u8),
    "8d56011b-3cb9-4387-a7e8-b79d826a7025": ("Motor RPM Min",           "legacy", _dec_u16),
    # History Service (0x0200) — legacy
    "8d560202-3cb9-4387-a7e8-b79d826a7025": ("History Timestamp",       "legacy", _dec_u32),
    "8d560206-3cb9-4387-a7e8-b79d826a7025": ("History Avg Current",     "legacy", _dec_u16),
    "8d560207-3cb9-4387-a7e8-b79d826a7025": ("History Duration",        "legacy", _dec_u16_sec),
    "8d560208-3cb9-4387-a7e8-b79d826a7025": ("History RPM",             "legacy", _dec_u16),
    "8d560209-3cb9-4387-a7e8-b79d826a7025": ("History Sync Status",     "legacy", _dec_u8),
    # Control Service (0x0300) — legacy
    "8d560302-3cb9-4387-a7e8-b79d826a7025": ("Capabilities",            "legacy", None),
    "8d560305-3cb9-4387-a7e8-b79d826a7025": ("Motion Type",             "legacy", None),
    "8d56030c-3cb9-4387-a7e8-b79d826a7025": ("Pressure",                "legacy", _dec_u16),
    "8d560311-3cb9-4387-a7e8-b79d826a7025": ("Lightring Color Low",     "legacy", _dec_rgba),
    "8d560312-3cb9-4387-a7e8-b79d826a7025": ("Lightring Color OK",      "legacy", _dec_rgba),
    "8d560313-3cb9-4387-a7e8-b79d826a7025": ("Lightring Color High",    "legacy", _dec_rgba),
    "8d560319-3cb9-4387-a7e8-b79d826a7025": ("App Handle Settings",     "legacy", _dec_app_handle_settings),
    "8d56031a-3cb9-4387-a7e8-b79d826a7025": ("Cleaning Cycles",         "legacy", _dec_u16),
    "8d56031c-3cb9-4387-a7e8-b79d826a7025": ("Lightring Color Motion",  "legacy", _dec_rgba),
    "8d560322-3cb9-4387-a7e8-b79d826a7025": ("Handle Load Type",        "legacy", _dec_enum_u16(_HANDLE_LOAD_TYPES)),
    "8d56032a-3cb9-4387-a7e8-b79d826a7025": ("Shaving Mode",            "legacy", _dec_enum(_SHAVING_MODES)),
    "8d560330-3cb9-4387-a7e8-b79d826a7025": ("Custom Shaving Settings", "legacy", None),
    "8d560331-3cb9-4387-a7e8-b79d826a7025": ("Lightring Brightness",    "legacy", _dec_enum(_LIGHTRING_BRIGHTNESS)),
    "8d560332-3cb9-4387-a7e8-b79d826a7025": ("Shaving Mode Settings",   "legacy", None),
    # Smart Groomer Service (0x0700) — OneBlade only, legacy
    "8d560702-3cb9-4387-a7e8-b79d826a7025": ("Groomer Capabilities",    "legacy", None),
    "8d560703-3cb9-4387-a7e8-b79d826a7025": ("Speed",                   "legacy", _dec_u16),
    "8d560705-3cb9-4387-a7e8-b79d826a7025": ("Speed Zone Threshold",    "legacy", None),
    "8d560706-3cb9-4387-a7e8-b79d826a7025": ("Speed Verdict",           "legacy", _dec_enum(_SPEED_VERDICTS)),
    # Newer (Condor) protocol transport
    "e50b0001-af04-4564-92ad-fef019489de6": ("Proto RX",                "newer_proto", None),
    "e50b0002-af04-4564-92ad-fef019489de6": ("Proto RX ACK",            "newer_proto", None),
    "e50b0003-af04-4564-92ad-fef019489de6": ("Proto TX",                "newer_proto", None),
    "e50b0004-af04-4564-92ad-fef019489de6": ("Proto TX ACK",            "newer_proto", None),
    "e50b0005-af04-4564-92ad-fef019489de6": ("Proto Config",            "newer_proto", None),
    "e50b0006-af04-4564-92ad-fef019489de6": ("Proto Server Config",     "newer_proto", None),
    "e50b0007-af04-4564-92ad-fef019489de6": ("Proto Client Config",     "newer_proto", None),
}


# =====================================================================
# Newer protocol probe (identical logic to sonicare_scan.py — the
# transport is device-agnostic; port names are what differ per device.)
# =====================================================================

def _parse_generic_resp_json(resp: bytes):
    if not resp or len(resp) < 2 or resp[0] != 0:
        return None
    body = resp[1:].rstrip(b"\x00")
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        return None


def _parse_json_ids(resp: bytes) -> list[str]:
    data = _parse_generic_resp_json(resp)
    return list(data.keys()) if isinstance(data, dict) else []


def _parse_json_list(resp: bytes) -> list[str]:
    data = _parse_generic_resp_json(resp)
    return [p for p in data if isinstance(p, str)] if isinstance(data, list) else []


class NewerProtocolProbe:
    """Probe a Philips device using the newer (e50b) BLE protocol."""

    CH_DATA = 0
    CH_BINARY = 1
    BIT_CHANNEL = 0x80
    BIT_START = 0x40
    MASK_SEQ = 0x3F

    NEG_VERSIONS = bytes([0x03, 0x04])
    CFG_REQUEST = bytes([0xFF, 0xFF, 0xFF, 0xFF])
    DEFAULT_PACKET_SIZE = 20

    # Known Condor port names from decompiled com.philips.d2cmobile (OneBlade
    # app 3.6.0) and the common Condor framework. Wire names are the strings
    # returned by each Port's getPortName(). Probing these with GetProps lets
    # us discover which ones the device actually implements without going
    # through GetPorts, which on the XP9201 crashes the device firmware when
    # called on Product "1".
    KNOWN_PORT_NAMES = (
        # Shaver-specific
        "bitmap",
        # Common framework
        "firmware", "device", "time", "log", "logsettings", "bleparams",
        "transport", "security", "fac", "pairing", "backend", "locale",
        "wifi", "wifiui",
        # Sonicare-style candidates — unlikely on shaver but cheap to probe
        "Sonicare", "RoutineStatus", "SensorData", "BrushHead",
        "SessionStorage", "Extended", "Diagnostics", "Battery",
        "Shaver", "Handle", "ShavingSession", "BladeHead",
    )

    def __init__(self, client: BleakClient, listen_seconds: int = 0,
                 probe_product_1: bool = False, probe_known_ports: bool = False):
        self.client = client
        self.listen_seconds = listen_seconds
        self.probe_product_1 = probe_product_1
        self.probe_known_ports = probe_known_ports
        self.next_data_seq = 1
        self.last_incoming_seq = -1
        self.rx_buffer = bytearray()
        self.response_event = asyncio.Event()
        self.response_data = b""
        self.server_cfg_event = asyncio.Event()
        self.server_cfg_data = b""
        self.handshake_ack_event = asyncio.Event()
        self.max_packet_size = self.DEFAULT_PACKET_SIZE
        self.indication_count: dict[tuple[str, str], int] = {}

    def _data_header(self) -> int:
        seq = self.next_data_seq & self.MASK_SEQ
        self.next_data_seq = (self.next_data_seq + 1) % 64
        if self.next_data_seq == 0:
            self.next_data_seq = 1
        return seq

    async def _send_handshake(self):
        self.handshake_ack_event.clear()
        await self.client.write_gatt_char(
            CHAR_RX, bytes([self.BIT_START]), response=False
        )

    async def _send_ack(self, seq: int):
        try:
            await self.client.write_gatt_char(
                CHAR_TX_ACK, bytes([seq & self.MASK_SEQ]), response=False
            )
        except Exception as e:
            print(f"      !!! TX_ACK write failed: {e}")

    async def _send_msg(self, msg_type: int, payload: bytes = b""):
        frame = b"\xFE\xFF" + bytes([msg_type]) + struct.pack(">H", len(payload)) + payload
        name = MSG_NAMES.get(msg_type, f"Type{msg_type}")
        print(f"  >>> {name} ({len(frame)}B): {frame.hex()}")

        chunk_payload = max(self.max_packet_size - 1, 1)
        offset = 0
        while offset < len(frame):
            chunk = frame[offset:offset + chunk_payload]
            hdr = self._data_header()
            await self.client.write_gatt_char(
                CHAR_RX, bytes([hdr]) + chunk, response=False
            )
            offset += len(chunk)

    async def _send_and_wait(self, msg_type: int, payload: bytes = b"", timeout: float = 5.0) -> bytes:
        self.response_event.clear()
        self.response_data = b""
        # Drop any half-assembled frame from a previous exchange so a stale
        # prefix cannot swallow the next FE FF start marker.
        self.rx_buffer = bytearray()
        try:
            await self._send_msg(msg_type, payload)
        except BleakError as e:
            print(f"      !!! Send failed ({type(e).__name__}): {e}")
            raise
        try:
            await asyncio.wait_for(self.response_event.wait(), timeout)
        except asyncio.TimeoutError:
            print("      !!! Timeout waiting for response")
            return b""
        return self.response_data

    def _on_tx(self, _sender, data: bytearray):
        if len(data) < 1:
            return
        hdr = data[0]
        seq = hdr & self.MASK_SEQ
        payload = bytes(data[1:])

        self.last_incoming_seq = seq
        asyncio.get_event_loop().create_task(self._send_ack(seq))

        self.rx_buffer.extend(payload)
        buf = bytes(self.rx_buffer)
        if len(buf) >= 5 and buf[0] == 0xFE and buf[1] == 0xFF:
            msg_type = buf[2]
            payload_len = struct.unpack(">H", buf[3:5])[0]
            if len(buf) >= 5 + payload_len:
                self._handle_message(msg_type, buf[5:5 + payload_len])
                self.rx_buffer = bytearray()

    def _on_rx_ack(self, _sender, data: bytearray):
        if not self.handshake_ack_event.is_set():
            print(f"  <<< Channel ACK: {bytes(data).hex()}")
            self.handshake_ack_event.set()

    def _on_server_cfg(self, _sender, data: bytearray):
        self.server_cfg_data = bytes(data)
        print(f"  <<< Server Config: {self.server_cfg_data.hex()}")
        self.server_cfg_event.set()

    def _handle_message(self, msg_type: int, payload: bytes):
        name = MSG_NAMES.get(msg_type, f"Type{msg_type}")

        if msg_type == MSG_CHANGE_IND:
            self._handle_change_indication(payload)
            return

        print(f"  <<< {name}: {payload.hex()}")

        if msg_type == MSG_GENERIC_RESP and len(payload) >= 1:
            status = payload[0]
            status_name = STATUS_NAMES.get(status, f"Unknown({status})")
            body = payload[1:]
            print(f"      Status: {status_name} ({status})")
            if body:
                print(f"      Body: {body.hex()}")
                try:
                    text = body.decode("utf-8", errors="replace")
                    if text.isprintable():
                        print(f"      Text: {text}")
                except Exception:
                    pass

        elif msg_type == MSG_INITIALIZE_RESP and len(payload) >= 1:
            status = payload[0]
            status_name = STATUS_NAMES.get(status, f"Unknown({status})")
            print(f"      Status: {status_name} ({status})")
            if len(payload) > 1:
                print(f"      Extra: {payload[1:].hex()}")

        elif len(payload) > 0:
            try:
                text = payload.decode("utf-8", errors="replace")
                if text.isprintable():
                    print(f"      Text: {text}")
            except Exception:
                pass

        self.response_data = payload
        self.response_event.set()

    def _handle_change_indication(self, payload: bytes):
        stamp = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"

        parts = payload.split(b"\x00", 1)
        if len(parts) < 2 or b"/" not in parts[0]:
            print(f"  [{stamp}] <<< ChangeInd (malformed, {len(payload)}B): {payload.hex()}")
            asyncio.get_event_loop().create_task(self._send_change_ind_ack())
            return

        header = parts[0].decode("ascii", errors="replace")
        prod, port = header.split("/", 1)
        body = parts[1]
        while body.endswith(b"\x00"):
            body = body[:-1]

        key = (prod, port)
        self.indication_count[key] = self.indication_count.get(key, 0) + 1

        is_binary = port.endswith(".b")
        if is_binary:
            summary = f"{len(body)}B: {body.hex()}"
        else:
            try:
                decoded = body.decode("utf-8")
                summary = decoded.strip()
            except UnicodeDecodeError:
                summary = f"(non-utf8 {len(body)}B) {body.hex()}"

        print(f"  [{stamp}] <<< ChangeInd prod={prod} port={port}: {summary}")
        asyncio.get_event_loop().create_task(self._send_change_ind_ack())

    async def _send_change_ind_ack(self):
        try:
            await self._send_msg(MSG_CHANGE_IND_RESP, bytes([0]))
        except Exception as e:
            print(f"      !!! ChangeIndResp send failed: {e}")

    async def _subscribe_port(self, prod: str, port: str) -> bool:
        body = json.dumps({"timeout": SUBSCRIBE_TIMEOUT_SECS}).encode("utf-8")
        payload = prod.encode() + b"\x00" + port.encode() + b"\x00" + body
        print(f"\n  -- Subscribe prod={prod} port={port} --")
        resp = await self._send_and_wait(MSG_SUBSCRIBE, payload, timeout=5.0)
        if not resp:
            return False
        status = resp[0] if resp else 255
        return status == 0

    async def _unsubscribe_port(self, prod: str, port: str) -> None:
        payload = prod.encode() + b"\x00" + port.encode() + b"\x00" + b"{}"
        print(f"\n  -- Unsubscribe prod={prod} port={port} --")
        await self._send_and_wait(MSG_UNSUBSCRIBE, payload, timeout=3.0)

    async def _await_server_cfg(self, expected_len: int, timeout: float = 5.0) -> bytes | None:
        self.server_cfg_event.clear()
        self.server_cfg_data = b""
        try:
            await asyncio.wait_for(self.server_cfg_event.wait(), timeout)
        except asyncio.TimeoutError:
            print(f"      !!! No Server Config response (expected {expected_len}B)")
            return None
        if len(self.server_cfg_data) != expected_len:
            print(
                f"      !!! Server Config length mismatch: got {len(self.server_cfg_data)}B, "
                f"expected {expected_len}B"
            )
            return None
        return self.server_cfg_data

    async def _subscribe_data_channels(self) -> bool:
        """Subscribe to TX and RX_ACK. Common to both V3 and V4."""
        for uuid, cb, label in [
            (CHAR_TX, self._on_tx, "TX"),
            (CHAR_RX_ACK, self._on_rx_ack, "RX ACK"),
        ]:
            try:
                await asyncio.wait_for(self.client.start_notify(uuid, cb), timeout=5.0)
            except asyncio.TimeoutError:
                print(f"      !!! Timeout subscribing to {label} ({uuid})")
                return False
            except Exception as e:
                print(f"      !!! Error subscribing to {label} ({uuid}): {e}")
                return False
            if not self.client.is_connected:
                print(f"      !!! Disconnected during subscribe to {label}")
                return False
        return True

    async def _open_data_channel(self) -> bool:
        """Send the BIT_START packet on RX, wait for RX_ACK. Common to V3 + V4."""
        try:
            await self._send_handshake()
        except Exception as e:
            print(f"      !!! Channel-open write failed: {e}")
            return False
        try:
            await asyncio.wait_for(self.handshake_ack_event.wait(), 5.0)
        except asyncio.TimeoutError:
            print("      !!! No channel-open ACK on RX_ACK")
            return False
        return self.client.is_connected

    async def _handshake_v3(self, cfg_bytes: bytes) -> bool:
        """V3 handshake: no version/channel negotiation, PROTO_CFG is static.

        Packet size is fixed at 20 bytes per the V3 spec. Buffer sizes come
        from PROTO_CFG but the transport does not exchange anything — we just
        subscribe the data channels and open channel 0.
        """
        self.max_packet_size = 20
        print(f"      V3 static config → packet_size=20, in_buf={cfg_bytes[1]}, "
              f"out_buf={cfg_bytes[2]}")

        print("\n  [V3 1/2] Subscribe to TX and RX ACK...")
        if not await self._subscribe_data_channels():
            return False

        print("\n  [V3 2/2] Open data channel...")
        if not await self._open_data_channel():
            return False
        print("      Data channel open.")
        return True

    async def _handshake_v4(self) -> bool:
        """V4 handshake: version-negotiation → channel-config → channel-open."""
        print("\n  [V4 1/5] Subscribe to Server Config...")
        try:
            await asyncio.wait_for(
                self.client.start_notify(CHAR_SERVER_CFG, self._on_server_cfg),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            print("      !!! Timeout subscribing to Server Config")
            return False
        except Exception as e:
            print(f"      !!! Error subscribing to Server Config: {e}")
            return False
        if not self.client.is_connected:
            return False

        print("\n  [V4 2/5] Version negotiation...")
        self.server_cfg_event.clear()
        try:
            await self.client.write_gatt_char(
                CHAR_CLIENT_CFG, self.NEG_VERSIONS, response=False
            )
        except Exception as e:
            print(f"      !!! Write to CLIENT_CFG failed: {e}")
            return False
        version_data = await self._await_server_cfg(expected_len=1)
        if version_data is None:
            return False
        chosen_version = version_data[0]
        print(f"      Chosen version: {chosen_version}")
        if chosen_version != 4:
            print(f"      !!! Only transport v4 is implemented in this branch.")
            return False
        if not self.client.is_connected:
            return False

        print("\n  [V4 3/5] Subscribe to TX and RX ACK...")
        if not await self._subscribe_data_channels():
            return False

        print("\n  [V4 4/5] Channel configuration...")
        self.server_cfg_event.clear()
        try:
            await self.client.write_gatt_char(
                CHAR_CLIENT_CFG, self.CFG_REQUEST, response=False
            )
        except Exception as e:
            print(f"      !!! Channel-config request failed: {e}")
            return False
        cfg_data = await self._await_server_cfg(expected_len=6)
        if cfg_data is None:
            return False
        max_pkt, ch0_buf, ch1_buf = struct.unpack("<HHH", cfg_data)
        print(f"      max_packet_size={max_pkt}, ch0_buf={ch0_buf}, ch1_buf={ch1_buf}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            link_mtu = self.client.mtu_size
        self.max_packet_size = max(min(max_pkt, link_mtu - 3), 4)
        print(f"      effective max_packet_size={self.max_packet_size} (link MTU={link_mtu})")
        if not self.client.is_connected:
            return False

        print("\n  [V4 5/5] Open data channel...")
        if not await self._open_data_channel():
            return False
        print("      Data channel open.")
        return True

    async def run(self):
        print("\n--- Newer Protocol Probe ---\n")

        # Read PROTO_CFG to decide V3 vs V4. OneBlade QP4530 has PROTO_CFG
        # present with byte 0 == 3 and NO SERVER_CFG/CLIENT_CFG chars.
        # XP9201 has no PROTO_CFG and uses V4 negotiation. Legacy HX742X also
        # uses V4 without PROTO_CFG.
        version_hint: int | None = None
        cfg_bytes: bytes = b""
        try:
            cfg_bytes = bytes(await self.client.read_gatt_char(CHAR_PROTO_CFG))
            print(f"  Protocol Config: {cfg_bytes.hex()}")
            if len(cfg_bytes) >= 3:
                print(f"    Version={cfg_bytes[0]}, InBuf={cfg_bytes[1]}, OutBuf={cfg_bytes[2]}")
                version_hint = cfg_bytes[0]
        except BleakCharacteristicNotFoundError:
            print("  Protocol Config: characteristic absent — assuming V4")
        except BleakError as e:
            print(f"  Protocol Config read failed: {e} — assuming V4")

        if version_hint == 3:
            print("\n  → Using V3 handshake (static PROTO_CFG, no negotiation)")
            if not await self._handshake_v3(cfg_bytes):
                print("      !!! V3 handshake failed — aborting probe")
                return
        else:
            print("\n  → Using V4 handshake (CLIENT_CFG/SERVER_CFG negotiation)")
            if not await self._handshake_v4():
                print("      !!! V4 handshake failed — aborting probe")
                return

        print("\n  -- Framed exchange --")

        # From here on any BleakError (link drop, GATT not ready, …) just
        # aborts the probe rather than crashing the script — we still got
        # through the transport handshake which is what matters.
        try:
            print("\n  -- Initialize --")
            await self._send_and_wait(MSG_INITIALIZE_REQ)
            await asyncio.sleep(0.3)

            print("\n  -- Get products --")
            prods_resp = await self._send_and_wait(MSG_GET_PRODS)
            prod_ids = _parse_json_ids(prods_resp)
            await asyncio.sleep(0.3)

            product_ports: dict[str, list[str]] = {}
            if prod_ids:
                print("\n  -- Get ports --")
                for prod_id in prod_ids:
                    # XP9201 FW 1.3.4: GetPorts on product "1" freezes the
                    # shaver for several seconds (cannot even be powered off).
                    # Only Product "0" (firmware/OTA) is safe by default;
                    # use --probe-product-1 to opt back in once you believe
                    # the firmware has been fixed.
                    if prod_id != "0" and not self.probe_product_1:
                        print(
                            f"  Skipping GetPorts on product {prod_id!r} — "
                            "known to hang the XP9201 firmware. Re-run with "
                            "--probe-product-1 to override."
                        )
                        product_ports[prod_id] = []
                        continue
                    payload = prod_id.encode() + b"\x00"
                    ports_resp = await self._send_and_wait(MSG_GET_PORTS, payload)
                    ports = _parse_json_list(ports_resp)
                    product_ports[prod_id] = ports
                    if not ports:
                        print(f"      !!! No ports returned for product {prod_id!r} — skipping")
                    await asyncio.sleep(0.3)

            if product_ports and self.client.is_connected:
                print("\n  -- Get properties --")
                for prod_id, ports in product_ports.items():
                    for port in ports:
                        if not self.client.is_connected:
                            break
                        payload = prod_id.encode() + b"\x00" + port.encode() + b"\x00"
                        await self._send_and_wait(MSG_GET_PROPS, payload, timeout=3.0)
                        await asyncio.sleep(0.2)

            # Port-name brute force: probe known Condor port names (from the
            # decompiled app) via GetProps. Known XP9201 FW 1.3.4 behaviour:
            # ANY request (GetPorts, GetProps, …) with product="1" hangs
            # the shaver for several seconds and drops the link. Restrict
            # probing to product "0" unless --probe-product-1 explicitly
            # opts in to the dangerous products.
            if self.probe_known_ports and self.client.is_connected:
                if self.probe_product_1:
                    targets = prod_ids
                else:
                    targets = [p for p in prod_ids if p == "0"]
                    skipped = [p for p in prod_ids if p != "0"]
                    if skipped:
                        print(
                            "\n  Skipping known-port probe on product(s) "
                            f"{skipped!r} — any query on them hangs the "
                            "XP9201 firmware. Use --probe-product-1 to override."
                        )
                print("\n  -- Probe known port names on safe products --")
                for prod_id in targets:
                    print(f"\n  Product {prod_id!r}:")
                    for port in self.KNOWN_PORT_NAMES:
                        if not self.client.is_connected:
                            break
                        payload = (
                            prod_id.encode() + b"\x00" + port.encode() + b"\x00"
                        )
                        resp = await self._send_and_wait(
                            MSG_GET_PROPS, payload, timeout=3.0
                        )
                        status = resp[0] if resp else 255
                        status_name = STATUS_NAMES.get(status, f"Unknown({status})")
                        marker = "✓" if status == 0 else " "
                        print(f"    {marker} {port!r}: {status_name}")
                        await asyncio.sleep(0.15)

            if self.listen_seconds > 0 and self.client.is_connected:
                await self._listen_for_indications(product_ports)
        except BleakError as e:
            print(f"\n  !!! Probe aborted — GATT/link error: {e}")
        except Exception as e:
            print(f"\n  !!! Probe aborted — unexpected error: {type(e).__name__}: {e}")

        print("\n--- Probe complete ---")

    async def _listen_for_indications(
        self, discovered_ports: dict[str, list[str]]
    ) -> None:
        """Subscribe to every JSON port the device advertised and log incoming
        ChangeIndications. Unlike the Sonicare script there is no known
        default port list for shavers — we try whatever GetPorts returned,
        skipping *.b binary streams by default.
        """
        print(f"\n--- Listen phase ({self.listen_seconds}s) ---")

        candidates: list[tuple[str, str]] = []
        for prod, ports in discovered_ports.items():
            for port in ports:
                if port.endswith(".b"):
                    continue
                candidates.append((prod, port))

        if not candidates:
            print("  No JSON ports discovered — nothing to subscribe to.")
            return

        subscribed: list[tuple[str, str]] = []
        for prod, port in candidates:
            ok = await self._subscribe_port(prod, port)
            if ok:
                subscribed.append((prod, port))
            else:
                print(f"      !!! Subscribe failed for {prod}/{port}")
            await asyncio.sleep(0.2)

        if not subscribed:
            print("\n  No ports subscribed — nothing to listen for.")
            return

        print(
            f"\n  Listening for {self.listen_seconds}s on {len(subscribed)} port(s). "
            "Press the shaver power button, switch modes, start/stop a session…"
        )
        try:
            await asyncio.sleep(self.listen_seconds)
        except asyncio.CancelledError:
            print("\n  Listen interrupted.")

        print("\n--- Listen summary ---")
        if self.indication_count:
            for (prod, port), count in sorted(self.indication_count.items()):
                print(f"  prod={prod} port={port}: {count} indication(s)")
        else:
            print("  No ChangeIndications received.")

        print("\n--- Cleaning up subscriptions ---")
        for prod, port in subscribed:
            if not self.client.is_connected:
                break
            await self._unsubscribe_port(prod, port)
            await asyncio.sleep(0.1)


# =====================================================================
# GATT scan (works for both protocols)
# =====================================================================


def _adv_summary(adv) -> str:
    parts = []
    if adv and adv.manufacturer_data:
        for company_id, data in adv.manufacturer_data.items():
            vendor = "Philips" if company_id == 477 else f"0x{company_id:04X}"
            try:
                text = data.decode("utf-8")
                payload = f'"{text}"' if text.isprintable() and text.strip() else data.hex()
            except (UnicodeDecodeError, ValueError):
                payload = data.hex()
            parts.append(f"{vendor}:{payload}")
    return f"  [{', '.join(parts)}]" if parts else ""


def _looks_like_shaver(device, adv) -> bool:
    """Match on the shaver service UUIDs (primary) or a Philips-ish name."""
    if adv and adv.service_uuids:
        for uuid in adv.service_uuids:
            if uuid.lower() in SHAVER_LEGACY_SERVICES:
                return True
    if device.name:
        low = device.name.lower()
        if any(hint in low for hint in SHAVER_NAME_HINTS):
            return True
    return False


async def find_shaver():
    """Scan for any Philips shaver / OneBlade nearby. Returns (address, adv)."""
    print("Scanning for Philips shaver / OneBlade (20s)...")
    print("Tip: Wake the device by pressing the power button or placing it on the charger.\n")

    devices = await BleakScanner.discover(timeout=20, return_adv=True)
    found = []
    for _addr, (device, adv) in devices.items():
        if _looks_like_shaver(device, adv):
            found.append((device, adv))

    if not found:
        print("No Philips shaver / OneBlade found.")
        print("Make sure:")
        print("  - Bluetooth is enabled on this machine")
        print("  - The device is awake (press button or place on charger)")
        print("  - You are close enough to the device")
        return None, None

    if len(found) == 1:
        device, adv = found[0]
        name = device.name or "(unnamed)"
        print(f"Found: {name} ({device.address}), RSSI={adv.rssi}{_adv_summary(adv)}")
        return device.address, adv

    print(f"Found {len(found)} device(s):")
    for i, (device, adv) in enumerate(found):
        name = device.name or "(unnamed)"
        print(f"  [{i+1}] {name} ({device.address}), RSSI={adv.rssi}{_adv_summary(adv)}")
    print()
    choice = input(f"Select device [1-{len(found)}]: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(found):
            return found[idx][0].address, found[idx][1]
    except ValueError:
        pass
    print("Invalid selection.")
    return None, None


async def _negotiate_mtu(client: BleakClient, requested: int | None) -> None:
    if requested is not None:
        try:
            client._mtu_size = requested
            print(f"MTU forced to {requested} (no exchange)")
            return
        except Exception as e:
            print(f"MTU force failed: {e} — falling back to auto-exchange")

    acquire = getattr(client, "_acquire_mtu", None)
    if acquire is None:
        print("MTU auto-exchange unavailable on this bleak version — "
              "stuck at default 23 unless --mtu is used")
        return
    try:
        await acquire()
        print("MTU auto-exchange completed")
    except Exception as e:
        print(f"MTU auto-exchange failed: {e}")


def _remove_shaver_bonds() -> list[str]:
    """Remove paired Philips shaver / OneBlade devices from BlueZ (Linux only).

    Stale bonds cause subscribe timeouts: BlueZ reports the device as
    paired, but the shaver has forgotten the link key, so any encrypted
    operation fails silently. A clean slate avoids that failure mode.
    """
    if sys.platform != "linux":
        return []
    try:
        listing = subprocess.run(
            ["bluetoothctl", "devices", "Paired"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    removed: list[str] = []
    for line in listing.stdout.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) < 3 or parts[0] != "Device":
            continue
        mac, name = parts[1], parts[2]
        low = name.lower()
        # "philips qp" covers OneBlade models that advertise as
        # "Philips QP4530" rather than "OneBlade".
        if not any(tag in low for tag in ("oneblade", "shaver", "philips xp", "philips s", "philips qp")):
            continue
        try:
            subprocess.run(
                ["bluetoothctl", "remove", mac],
                capture_output=True, text=True, timeout=5, check=False,
            )
            removed.append(f"{mac} ({name})")
        except Exception:
            pass
    return removed


# ATT/BlueZ error fragments that mean "this read needs a bond/encryption".
# Shavers use lazy encryption: connect + discovery run unbonded, individual
# reads can come back with INSUF_AUTHENTICATION (XP9400, issue #3).
_AUTH_ERROR_HINTS = (
    "insufficient", "authentication", "encryption", "not permitted",
    "not paired", "not authorized", "0x05", "0x0f",
)


def _is_auth_error(msg: str) -> bool:
    low = msg.lower()
    return any(hint in low for hint in _AUTH_ERROR_HINTS)


async def _do_dbus_pair(mac: str) -> bool:
    """Pair via the integration's D-Bus helper. Returns True on success."""
    if not HAS_DBUS_PAIRING:
        print(f"--pair requested but dbus_pairing import failed: {_DBUS_IMPORT_ERR}")
        return False
    if not is_dbus_available():
        print("--pair requested but D-Bus system bus is not available (non-Linux?)")
        return False
    try:
        print(f"Pairing {mac} via D-Bus (auto-confirm agent)...")
        await async_pair_and_trust(mac)
        print("Paired and trusted.")
        return True
    except PairingError as err:
        print(f"D-Bus pairing failed: {err}")
        return False


async def _read_char_into(client, char, char_info, char_entry, device_info) -> str:
    """Read one characteristic into ``char_entry``. Returns a status string:
    "ok", "auth" (needs bonding), "link_lost", or "error"."""
    try:
        value = await client.read_gatt_char(char)
    except BleakError as e:
        msg = str(e)
        print(f"    Read error: {e}")
        # These errors mean the link is dead; remaining reads will all
        # raise the same thing.
        if (
            "Service Discovery has not been performed" in msg
            or "Not connected" in msg
            or "disconnected" in msg.lower()
        ):
            return "link_lost"
        return "auth" if _is_auth_error(msg) else "error"
    except Exception as e:
        print(f"    Read error: {e}")
        return "auth" if _is_auth_error(str(e)) else "error"

    hex_str = value.hex()
    char_entry["value_hex"] = hex_str
    decoded = None
    if char_info and char_info[2]:
        try:
            decoded = char_info[2](value)
        except Exception as dec_err:
            decoded = f"(decode error: {dec_err})"
    try:
        text = value.decode("utf-8")
        if text.isprintable() and text.strip():
            char_entry["value_text"] = text
            value_str = f"{hex_str} = \"{text}\""
        else:
            value_str = hex_str
    except (UnicodeDecodeError, ValueError):
        value_str = hex_str

    if char_info and char_info[1] in ("device_info", "standard_ble"):
        device_info[char_info[0]] = (
            char_entry["value_text"]
            if char_entry["value_text"] is not None
            else hex_str
        )

    if decoded is not None:
        print(f"    Value: {value_str}  →  {decoded}")
    else:
        print(f"    Value: {value_str}")
    return "ok"


async def scan_device(
    address: str,
    mtu: int | None = None,
    listen_seconds: int = 0,
    remove_bonds: bool = False,
    pair: bool = False,
    probe_product_1: bool = False,
    probe_known_ports: bool = False,
    json_path: str | None = None,
    fixture: bool = False,
    adv_name: str | None = None,
):
    """Connect to a shaver and dump all GATT services."""
    if remove_bonds:
        removed = _remove_shaver_bonds()
        if removed:
            print("Removed stale bonds before connecting:")
            for entry in removed:
                print(f"  - {entry}")
            print()

    paired = False
    if pair:
        # Shavers use LE Secure Connections with Numeric Comparison — the
        # integration registers a BlueZ Agent1 that auto-confirms. Doing
        # this BEFORE the bleak connect means the resulting bond is valid
        # when CCCD writes later require encryption. The helper disconnects
        # the D-Bus session once pairing completes.
        paired = await _do_dbus_pair(address)

    print(f"Connecting to {address} ...")
    async with BleakClient(address, timeout=30) as client:
        print(f"Connected: {client.is_connected}")

        await _negotiate_mtu(client, mtu)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            mtu_actual = client.mtu_size
        print(f"MTU: {mtu_actual}\n")

        has_legacy = False
        has_newer = False
        lost_connection = False

        # Snapshot the service table into plain Python objects up front. If
        # the device drops the link mid-scan, iterating the live
        # ``client.services`` property would raise; a snapshot keeps the
        # structure usable and lets us still write the JSON we gathered.
        services = list(client.services)
        service_count = len(services)
        gatt_services: list[dict] = []
        device_info: dict[str, str] = {}

        for service in services:
            svc_low = service.uuid.lower()
            if svc_low.startswith(SHAVER_LEGACY_PREFIX):
                has_legacy = True
            if svc_low.startswith(NEWER_PREFIX):
                has_newer = True

            svc_entry: dict = {"uuid": service.uuid, "characteristics": []}
            gatt_services.append(svc_entry)

            print(f"Service: {service.uuid}")
            if service.description and service.description != service.uuid:
                print(f"  Description: {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                char_info = KNOWN_CHARS.get(char.uuid.lower())
                char_label = f"  [{char_info[0]}]" if char_info else ""
                print(f"  Char: {char.uuid}  [{props}]  handle=0x{char.handle:04X}{char_label}")
                char_entry = {
                    "uuid": char.uuid,
                    "name": char_info[0] if char_info else None,
                    "properties": list(char.properties),
                    "handle": char.handle,
                    "value_hex": None,
                    "value_text": None,
                }
                svc_entry["characteristics"].append(char_entry)
                if "read" in char.properties and not lost_connection:
                    status = await _read_char_into(
                        client, char, char_info, char_entry, device_info
                    )
                    # Lazy encryption: the first read that demands a bond
                    # triggers pairing (auto-confirm agent), then a retry —
                    # same reactive pattern the integration uses. Without
                    # this, encrypted values end up null in the capture.
                    if status == "auth" and not paired:
                        print("    → read needs encryption, pairing ...")
                        paired = await _do_dbus_pair(address)
                        if paired and client.is_connected:
                            status = await _read_char_into(
                                client, char, char_info, char_entry, device_info
                            )
                    if status == "link_lost":
                        lost_connection = True
                        print("    (link lost — skipping remaining reads)")
                for desc in char.descriptors:
                    print(f"    Desc: {desc.uuid}  handle=0x{desc.handle:04X}")
            print()

        print("=" * 60)
        if has_legacy and has_newer:
            protocol = "Both Shaver Legacy + Newer Condor (first-ever find on a shaver)"
        elif has_legacy:
            protocol = "Shaver Legacy (8d56…, supported by philips_shaver)"
        elif has_newer:
            protocol = "Newer / Condor (e50b…, not yet seen on shavers)"
        else:
            protocol = "Unknown"
        print(f"Protocol: {protocol}")
        print(f"Total services: {service_count}")
        if lost_connection:
            print("Note: link dropped mid-enumeration. Retry with --pair to")
            print("      establish the bond first (shavers require auto-confirm).")
        print("=" * 60)

        if has_newer and client.is_connected and not lost_connection:
            probe = NewerProtocolProbe(
                client,
                listen_seconds=listen_seconds,
                probe_product_1=probe_product_1,
                probe_known_ports=probe_known_ports,
            )
            await probe.run()
        elif has_newer:
            print("\nSkipping Condor probe because the link is no longer healthy.")

        if json_path:
            _write_capture(
                json_path,
                address=address,
                adv_name=adv_name,
                protocol=protocol,
                device_info=device_info,
                gatt_services=gatt_services,
                anonymize=fixture,
            )


# Placeholder identity used when writing anonymized fixtures. Same vendor
# prefix as the Sonicare test fixtures so captures are recognizable as
# sanitized at a glance.
_FIXTURE_MAC = "24:E5:AA:00:00:01"
# Characteristics whose values identify the individual unit; their bytes are
# zeroed in fixture mode (structure and length are preserved).
_PRIVATE_CHAR_NAMES = {"Serial Number", "System ID"}


def _anonymize_snapshot(snapshot: dict) -> None:
    """Strip unit-identifying data in place: MAC, serial number, system ID."""
    snapshot["address"] = _FIXTURE_MAC
    for service in snapshot["gatt_services"]:
        for char in service["characteristics"]:
            if char.get("name") in _PRIVATE_CHAR_NAMES:
                if char.get("value_hex"):
                    if char.get("value_text"):
                        char["value_text"] = "0" * len(char["value_text"])
                        char["value_hex"] = char["value_text"].encode().hex()
                    else:
                        char["value_hex"] = "00" * (len(char["value_hex"]) // 2)
    for key in _PRIVATE_CHAR_NAMES:
        if key in snapshot["device_info"]:
            snapshot["device_info"][key] = "0" * len(snapshot["device_info"][key])


def _write_capture(
    path: str,
    *,
    address: str,
    adv_name: str | None,
    protocol: str,
    device_info: dict,
    gatt_services: list,
    anonymize: bool,
) -> None:
    """Write a structured snapshot of the scan to a JSON file.

    The shape matches the Sonicare capture format so ``tests/conftest.py``
    helpers work unchanged: ``gatt_services[*].characteristics[*]`` carries
    uuid/name/properties/handle/value_hex/value_text. With ``anonymize``
    (the ``--fixture`` flag) the MAC and serial number are scrubbed so the
    file can go straight into ``tests/fixtures/``.
    """
    snapshot = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "address": address,
        "adv_name": adv_name,
        "protocol": protocol,
        "device_info": device_info,
        "gatt_services": gatt_services,
    }
    if anonymize:
        _anonymize_snapshot(snapshot)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, ensure_ascii=False, sort_keys=False)
            fh.write("\n")
        label = "Fixture" if anonymize else "Capture"
        print(f"\n{label} written to {path}")
    except OSError as e:
        print(f"\n!!! Could not write capture to {path}: {e}")


async def main():
    parser = argparse.ArgumentParser(
        description="Philips shaver / OneBlade GATT scanner and newer-protocol probe",
    )
    parser.add_argument("mac", nargs="?", help="BLE MAC address (optional — scans if omitted)")
    parser.add_argument(
        "--mtu",
        type=int,
        default=None,
        help="Force a specific ATT MTU (e.g. 247). Default: auto-negotiate.",
    )
    parser.add_argument(
        "--listen",
        type=int,
        default=0,
        metavar="SECONDS",
        help=(
            "If the newer-protocol probe succeeds, subscribe to every JSON "
            "port returned by GetPorts and log incoming ChangeIndications "
            "for the given number of seconds. Press buttons, switch modes, "
            "or run a session during this window. Default: 0 (no listen)."
        ),
    )
    parser.add_argument(
        "--pair",
        action="store_true",
        help=(
            "Pair the device via BlueZ D-Bus using the integration's "
            "auto-confirm agent before connecting. Required for Condor CCCD "
            "writes and for any read that the shaver gates behind encryption."
        ),
    )
    parser.add_argument(
        "--remove-bonds",
        action="store_true",
        help=(
            "Remove existing Philips shaver / OneBlade bonds from BlueZ "
            "before connecting. Only useful when a bond is known-stale; "
            "pair with --pair to re-establish."
        ),
    )
    parser.add_argument(
        "--probe-product-1",
        action="store_true",
        help=(
            "DANGEROUS on XP9201 FW 1.3.4: GetPorts on product '1' freezes "
            "the shaver for several seconds. Only use if you believe the "
            "firmware has since been fixed on your device."
        ),
    )
    parser.add_argument(
        "--probe-known-ports",
        action="store_true",
        help=(
            "After the safe probe, call GetProps on each product with a list "
            "of known Condor port names from the decompiled app (bitmap, "
            "firmware, device, time, …). GetProps on an invalid port replies "
            "with NoSuchPort without crashing, so this is safer than "
            "GetPorts for enumerating real ports."
        ),
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help=(
            "Write a structured snapshot (device info + full GATT map with "
            "properties, handles and read values) to PATH. Same shape as the "
            "Sonicare captures."
        ),
    )
    parser.add_argument(
        "--fixture",
        metavar="PATH",
        default=None,
        help=(
            "Like --json, but anonymized for direct use as a test fixture in "
            "tests/fixtures/: MAC and serial number are scrubbed. "
            "Suggested naming: <model>_<variant>.json (e.g. xp9201.json)."
        ),
    )
    args = parser.parse_args()

    adv_name = None
    if args.mac:
        print(f"Scanning for {args.mac} (10s)...")
        device = await BleakScanner.find_device_by_address(args.mac, timeout=10)
        if not device:
            print(f"Device {args.mac} not found. If it is connected to another process (e.g. bluetoothctl),")
            sys.exit(1)
        print(f"Found: {device.name} ({device.address})")
        adv_name = device.name
        address = args.mac
    else:
        address, adv = await find_shaver()
        if not address:
            sys.exit(1)
        adv_name = adv.local_name if adv else None

    await scan_device(
        address,
        mtu=args.mtu,
        listen_seconds=args.listen,
        remove_bonds=args.remove_bonds,
        pair=args.pair,
        probe_product_1=args.probe_product_1,
        probe_known_ports=args.probe_known_ports,
        json_path=args.fixture or args.json,
        fixture=args.fixture is not None,
        adv_name=adv_name,
    )


asyncio.run(main())
