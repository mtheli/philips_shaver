"""Shared pytest fixtures for the Philips Shaver tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Every capture in tests/fixtures — new device fixtures are picked up
# automatically by the parametrized layout tests.
ALL_FIXTURE_NAMES = sorted(p.name for p in FIXTURES_DIR.glob("*.json"))


def load_json_fixture(name: str) -> dict[str, Any]:
    """Load a captured device snapshot from ``tests/fixtures``.

    These files are produced by ``scripts/shaver_scan.py --fixture`` against
    a real device (MAC and serial anonymized), so they double as golden
    inputs for the parsing tests.
    """
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def chars_as_bytes(snapshot: dict[str, Any]) -> dict[str, bytes]:
    """Flatten a snapshot's readable GATT characteristics into ``{uuid: bytes}``.

    This is the shape the coordinator's ``_process_results`` consumes, so a
    captured snapshot feeds straight in.
    """
    out: dict[str, bytes] = {}
    for service in snapshot["gatt_services"]:
        for char in service["characteristics"]:
            hex_value = char.get("value_hex")
            if hex_value:
                out[char["uuid"].lower()] = bytes.fromhex(hex_value)
    return out


def char_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map ``{char_uuid: (char_entry + parent service uuid)}`` for a snapshot."""
    out: dict[str, dict[str, Any]] = {}
    for service in snapshot["gatt_services"]:
        for char in service["characteristics"]:
            entry = dict(char)
            entry["service_uuid"] = service["uuid"].lower()
            out[char["uuid"].lower()] = entry
    return out


@pytest.fixture
def xp9201() -> dict[str, Any]:
    """Full snapshot of a Philips Shaver XP9201 (i9000 Prestige)."""
    return load_json_fixture("xp9201.json")


@pytest.fixture
def qp4530() -> dict[str, Any]:
    """Full snapshot of a Philips OneBlade QP4530 (captured mid-session)."""
    return load_json_fixture("qp4530.json")
