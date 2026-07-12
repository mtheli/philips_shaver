"""Structural GATT-layout checks against real device captures.

These need no characteristic values — only the service/characteristic table
with properties. That lets community-provided scans pin the integration's
expectations against hardware we never had on a desk:

* every characteristic the coordinator polls or subscribes to has a
  ``CHAR_SERVICE_MAP`` entry (the ESP bridge resolves reads through it —
  a missing entry fails with "No service UUID mapping" at runtime),
* the mapped service matches the service each characteristic actually
  lives in on the device,
* polled characteristics are readable and subscribed ones support
  notify/indicate wherever they exist.
"""

from __future__ import annotations

import pytest

from custom_components.philips_shaver.const import (
    CHAR_SERVICE_MAP,
    POLL_READ_CHARS,
    SVC_BATTERY,
    SVC_CONTROL,
    SVC_DEVICE_INFO,
    SVC_GROOMER,
    SVC_HISTORY,
    SVC_PLATFORM,
    SVC_SERIAL,
)
from custom_components.philips_shaver.coordinator import NOTIFICATION_CHARS

from .conftest import ALL_FIXTURE_NAMES, char_index, load_json_fixture

KNOWN_SERVICES = {
    SVC_BATTERY,
    SVC_DEVICE_INFO,
    SVC_PLATFORM,
    SVC_HISTORY,
    SVC_CONTROL,
    SVC_SERIAL,
    SVC_GROOMER,
}


# ---------------------------------------------------------------------------
# Pure const-consistency checks (no fixture needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("char", POLL_READ_CHARS)
def test_polled_char_has_service_mapping(char: str) -> None:
    """Every polled characteristic must resolve through CHAR_SERVICE_MAP."""
    assert char in CHAR_SERVICE_MAP, (
        f"{char} is polled but missing from CHAR_SERVICE_MAP — ESP bridge "
        "reads fail with 'No service UUID mapping'"
    )


@pytest.mark.parametrize("char", NOTIFICATION_CHARS)
def test_notification_char_has_service_mapping(char: str) -> None:
    """Every subscribed characteristic must resolve through CHAR_SERVICE_MAP."""
    assert char in CHAR_SERVICE_MAP


def test_service_map_targets_known_services() -> None:
    assert set(CHAR_SERVICE_MAP.values()) <= KNOWN_SERVICES


# ---------------------------------------------------------------------------
# Fixture-based checks — parametrized over every capture in tests/fixtures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_service_map_matches_device_layout(fixture_name: str) -> None:
    """CHAR_SERVICE_MAP must place each characteristic in the service the
    device actually exposes it under."""
    index = char_index(load_json_fixture(fixture_name))
    checked = 0
    for char, expected_service in CHAR_SERVICE_MAP.items():
        entry = index.get(char.lower())
        if entry is None:
            continue  # not present on this model — fine
        assert entry["service_uuid"] == expected_service.lower(), (
            f"{fixture_name}: {char} lives in {entry['service_uuid']}, "
            f"CHAR_SERVICE_MAP says {expected_service}"
        )
        checked += 1
    assert checked, f"{fixture_name}: no mapped characteristics found at all"


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_polled_chars_readable_where_present(fixture_name: str) -> None:
    index = char_index(load_json_fixture(fixture_name))
    for char in POLL_READ_CHARS:
        entry = index.get(char.lower())
        if entry is None or not entry["properties"]:
            continue  # absent on this model, or export lost the properties
        assert "read" in entry["properties"], (
            f"{fixture_name}: polled char {char} is not readable "
            f"({entry['properties']})"
        )


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_notification_chars_notify_where_present(fixture_name: str) -> None:
    index = char_index(load_json_fixture(fixture_name))
    for char in NOTIFICATION_CHARS:
        entry = index.get(char.lower())
        if entry is None or not entry["properties"]:
            continue
        assert {"notify", "indicate"} & set(entry["properties"]), (
            f"{fixture_name}: subscribed char {char} supports no "
            f"notifications ({entry['properties']})"
        )
