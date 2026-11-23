"""GATT capture through the ESP bridge (ble_list_services + capture_gatt).

The bridge sends one event per service with "uuid/props/handle" entries; the
integration turns them into a fixture-shaped, anonymized snapshot. A capture
rebuilt from an existing fixture must match that fixture's layout.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.philips_shaver import capture
from custom_components.philips_shaver.transport import _parse_service_chars

from .conftest import ALL_FIXTURE_NAMES, load_json_fixture


def _bridge_events(fixture: dict) -> list[dict]:
    """The services of a fixture as the bridge would report them.

    Fixtures carry bleak's declaration handle; the bridge reports ESP-IDF's
    value handle, one higher.
    """
    letters = {"read": "R", "write": "W", "write-without-response": "w",
               "notify": "N", "indicate": "I"}
    services = []
    for svc in fixture["gatt_services"]:
        chars = ",".join(
            "{}/{}/{:04x}".format(
                c["uuid"],
                "".join(letters[p] for p in c["properties"] if p in letters),
                c["handle"] + 1,
            )
            for c in svc["characteristics"]
        )
        services.append({"uuid": svc["uuid"], "characteristics": _parse_service_chars(chars)})
    return services


def test_parse_service_chars() -> None:
    chars = _parse_service_chars(
        "8d560322-3cb9-4387-a7e8-b79d826a7025/RN/005a,2a19/R/0010,abc/"
    )
    assert chars[0] == {
        "uuid": "8d560322-3cb9-4387-a7e8-b79d826a7025",
        "properties": ["read", "notify"],
        "handle": 0x59,  # value handle 0x5a - 1 = declaration handle
    }
    assert chars[1]["uuid"] == "00002a19-0000-1000-8000-00805f9b34fb"
    assert chars[2] == {"uuid": "abc", "properties": [], "handle": None}


def test_capture_matches_fixture_layout() -> None:
    fixture = load_json_fixture("xp9201.json")
    services = _bridge_events(fixture)
    values = {
        c["uuid"]: bytes.fromhex(c["value_hex"])
        for s in fixture["gatt_services"] for c in s["characteristics"]
        if c.get("value_hex") is not None
    }

    snap = capture.build_snapshot(services, values)

    assert snap["address"] == capture.FIXTURE_MAC
    assert snap["device_info"]["Model Number"] == "XP9201"
    got = {
        c["uuid"]: (tuple(c["properties"]), c["handle"], c["value_hex"], c["value_text"])
        for s in snap["gatt_services"] for c in s["characteristics"]
    }
    want = {
        c["uuid"]: (
            tuple(c["properties"]), c["handle"], c.get("value_hex"), c.get("value_text")
        )
        for s in fixture["gatt_services"] for c in s["characteristics"]
    }
    assert got == want


def test_capture_anonymizes_serial() -> None:
    services = [{
        "uuid": "0000180a-0000-1000-8000-00805f9b34fb",
        "characteristics": [{
            "uuid": "00002a25-0000-1000-8000-00805f9b34fb",
            "properties": ["read"], "handle": 0x17,
        }],
    }]
    snap = capture.build_snapshot(
        services, {"00002a25-0000-1000-8000-00805f9b34fb": b"SN123456"}
    )
    char = snap["gatt_services"][0]["characteristics"][0]
    assert char["value_text"] == "00000000"
    assert snap["device_info"]["Serial Number"] == "00000000"


def test_readable_chars_only_read_property() -> None:
    services = _bridge_events(load_json_fixture("xp9201.json"))
    readable = capture.readable_chars(services)
    assert readable
    props = {c["uuid"]: c["properties"] for s in services for c in s["characteristics"]}
    assert all("read" in props[u] for u in readable)


def test_value_text_only_for_text_characteristics() -> None:
    battery = "00002a19-0000-1000-8000-00805f9b34fb"
    model = "00002a24-0000-1000-8000-00805f9b34fb"
    version = "8d5601fd-3cb9-4387-a7e8-b79d826a7025"
    services = [{
        "uuid": "0000180a-0000-1000-8000-00805f9b34fb",
        "characteristics": [
            {"uuid": u, "properties": ["read"], "handle": i}
            for i, u in enumerate((battery, model, version))
        ],
    }]
    snap = capture.build_snapshot(services, {
        battery: b"\x5a",  # printable ("Z"), but a number
        model: b"S7885",
        version: b"OLED_1.0\x00\x00\x00",
    })
    text = {c["uuid"]: c["value_text"] for c in snap["gatt_services"][0]["characteristics"]}
    assert text == {battery: None, model: "S7885", version: "OLED_1.0"}
    assert snap["device_info"]["Battery Level"] == "90%"


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_fixtures_follow_value_text_rule(fixture_name: str) -> None:
    for svc in load_json_fixture(fixture_name)["gatt_services"]:
        for char in svc["characteristics"]:
            if char["uuid"] not in capture._TEXT_CHARS:
                assert char.get("value_text") is None, char["uuid"]


# --- list_services event handling -------------------------------------------

from custom_components.philips_shaver.transport import EspBridgeTransport  # noqa: E402

CONTROL = "8d560300-3cb9-4387-a7e8-b79d826a7025"


class _Bus:
    def __init__(self) -> None:
        self.handlers = []

    def async_listen(self, event_type, handler):
        self.handlers.append(handler)
        return lambda: self.handlers.remove(handler)


class _Services:
    """Answers ble_list_services by firing the given events synchronously."""

    def __init__(self, bus: _Bus, events: list[dict], available: bool = True) -> None:
        self.bus, self.events, self.available = bus, events, available
        self.calls = []

    def has_service(self, domain, name):
        return self.available

    async def async_call(self, domain, name, data, blocking=False):
        self.calls.append(name)
        for data in self.events:
            for handler in list(self.bus.handlers):
                handler(SimpleNamespace(data=data))


def _transport(events, *, available=True, bridge_id="shaver", mac="AA:BB:CC:DD:EE:FF"):
    import asyncio

    class _T(EspBridgeTransport):
        is_connected = True

    t = _T.__new__(_T)
    bus = _Bus()
    t._hass = SimpleNamespace(
        loop=asyncio.get_running_loop(), bus=bus,
        services=_Services(bus, events, available),
    )
    t._device_name = "atom"
    t._esp_bridge_id = bridge_id
    t._detected_mac = mac
    t._listed_char_services = {}
    return t


def _event(index, count, uuid, chars, *, bridge_id="shaver", mac="AA:BB:CC:DD:EE:FF"):
    return {"bridge_id": bridge_id, "mac": mac, "service_count": str(count),
            "service_index": str(index), "service_uuid": uuid, "service_chars": chars}


async def test_list_services_collects_and_maps_chars() -> None:
    t = _transport([
        _event(1, 2, "0x180F", "0x2A19/RN/00db"),
        _event(0, 2, CONTROL.upper(), "8D560302-3CB9-4387-A7E8-B79D826A7025/R/0089"),
    ])
    services = await t.list_services(timeout=1)
    assert [s["uuid"] for s in services] == [CONTROL, "0000180f-0000-1000-8000-00805f9b34fb"]
    assert services[1]["characteristics"][0] == {
        "uuid": "00002a19-0000-1000-8000-00805f9b34fb",
        "properties": ["read", "notify"], "handle": 0xDA,
    }
    # characteristics unknown to CHAR_SERVICE_MAP resolve through the table
    assert t._listed_char_services["00002a19-0000-1000-8000-00805f9b34fb"] == (
        "0000180f-0000-1000-8000-00805f9b34fb"
    )


async def test_list_services_ignores_other_bridges_and_devices() -> None:
    t = _transport([
        _event(0, 1, "0x9999", "", bridge_id="other"),
        _event(0, 1, "0x8888", "", mac="11:22:33:44:55:66"),
        _event(0, 1, "0x180F", "0x2A19/R/0010"),
    ])
    services = await t.list_services(timeout=1)
    assert [s["uuid"] for s in services] == ["0000180f-0000-1000-8000-00805f9b34fb"]


async def test_list_services_zero_services() -> None:
    t = _transport([_event(0, 0, "", "")])
    assert await t.list_services(timeout=1) == []


@pytest.mark.parametrize(
    ("events", "available"),
    [
        ([{"bridge_id": "shaver", "mac": "AA:BB:CC:DD:EE:FF", "error": "not_connected"}], True),
        ([], True),  # bridge never answers: timeout
        ([], False),  # bridge older than 1.15.0: no ble_list_services
    ],
)
async def test_list_services_unknown_returns_none(events, available) -> None:
    t = _transport(events, available=available)
    assert await t.list_services(timeout=0.2) is None


class _ReadTransport:
    def __init__(self, values, drop_after_batches=None):
        self.values, self.batches, self.singles = values, [], []
        self.drop_after = drop_after_batches
        self.is_connected = True

    async def read_chars(self, uuids):
        self.batches.append(list(uuids))
        if self.drop_after is not None and len(self.batches) >= self.drop_after:
            self.is_connected = False
        return {u: self.values.get(u) for u in uuids}

    async def read_char(self, uuid):
        self.singles.append(uuid)
        return self.values.get(uuid)


async def test_read_values_batches_and_retries() -> None:
    uuids = [f"u{i}" for i in range(30)]
    t = _ReadTransport({u: b"\x01" for u in uuids[:-1]})
    values = await capture.async_read_values(t, uuids)
    assert [len(b) for b in t.batches] == [12, 12, 6]
    assert t.singles == ["u29"]  # only the gap is retried
    assert values["u0"] == b"\x01" and values["u29"] is None


async def test_read_values_stops_on_disconnect() -> None:
    uuids = [f"u{i}" for i in range(30)]
    t = _ReadTransport({}, drop_after_batches=1)
    await capture.async_read_values(t, uuids)
    assert len(t.batches) == 1
    assert t.singles == []


def test_capture_scrubs_mac_from_values() -> None:
    services = [{
        "uuid": "8d560100-3cb9-4387-a7e8-b79d826a7025",
        "characteristics": [
            {"uuid": f"8d5601f{i}-3cb9-4387-a7e8-b79d826a7025",
             "properties": ["read"], "handle": i}
            for i in range(4)
        ],
    }]
    u = [c["uuid"] for c in services[0]["characteristics"]]
    mac = "F0:5C:00:00:78:85"
    snap = capture.build_snapshot(services, {
        u[0]: b"\x01" + bytes.fromhex("f05c00007885") + b"\x02",  # MSB first
        u[1]: bytes.fromhex("857800005cf0"),                      # LSB first
        u[2]: b"id=F0:5C:00:00:78:85",                             # as text
        u[3]: b"\x11\x22",                                          # untouched
    }, mac=mac)
    vals = {c["uuid"]: c["value_hex"] for c in snap["gatt_services"][0]["characteristics"]}
    assert vals[u[0]] == "01" + "00" * 6 + "02"
    assert vals[u[1]] == "00" * 6
    assert bytes.fromhex(vals[u[2]]) == b"id=" + b"0" * 17
    assert vals[u[3]] == "1122"


async def test_read_values_keeps_empty_values() -> None:
    class T(_ReadTransport):
        def pop_empty_read(self, uuid):
            return uuid == "empty"

    t = T({"a": b"\x01"})
    values = await capture.async_read_values(t, ["a", "empty", "gone"])
    assert values == {"a": b"\x01", "empty": b"", "gone": None}


async def test_listed_table_wins_over_service_map() -> None:
    """After list_services, reads go to the service the shaver really has."""
    pressure = "8d56030c-3cb9-4387-a7e8-b79d826a7025"  # mapped to 0x0300
    other = "8d560900-3cb9-4387-a7e8-b79d826a7025"
    t = _transport([_event(0, 1, other.upper(), f"{pressure}/RN/0010")])
    await t.list_services(timeout=1)
    assert t._get_service_uuid(pressure) == other


def _bare_transport():
    t = EspBridgeTransport.__new__(EspBridgeTransport)
    t._empty_reads = set()
    t._pending_reads = {}
    return t


def test_empty_payload_marks_empty_read() -> None:
    t = _bare_transport()
    t._on_empty_payload("u", "")
    assert t.pop_empty_read("u") is True
    assert t.pop_empty_read("u") is False  # popped once


def test_late_error_event_is_not_an_empty_read() -> None:
    """A read_timeout arriving after the HA-side timeout has no waiter left
    and carries no payload — it must not turn into an empty value."""
    t = _bare_transport()
    t._on_empty_payload("u", "read_timeout")
    assert t.pop_empty_read("u") is False


def test_invalid_mac_does_not_break_capture() -> None:
    services = [{
        "uuid": "0000180f-0000-1000-8000-00805f9b34fb",
        "characteristics": [{
            "uuid": "00002a19-0000-1000-8000-00805f9b34fb",
            "properties": ["read"], "handle": 1,
        }],
    }]
    for mac in (None, "", "garbage", "AA:BB"):
        snap = capture.build_snapshot(
            services, {"00002a19-0000-1000-8000-00805f9b34fb": b"\x5a"}, mac=mac
        )
        assert snap["device_info"]["Battery Level"] == "90%"


def test_zero_handle_is_dropped() -> None:
    assert _parse_service_chars("2a19/R/0000")[0]["handle"] is None
