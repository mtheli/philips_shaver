"""Tests for the setup-polish round ported from the Sonicare flow review.

Covers: the discovered-device picker in user_bleak, the detailed
already-configured abort, the event-probe based ESP redirect
(_find_esp_bridge_for_mac), the sole-ESP auto-select, and the
BLE-Security row in the capabilities dialog.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.data_entry_flow import AbortFlow, FlowResultType

from custom_components.philips_shaver.config_flow import (
    _MANUAL_ADDRESS,
    PhilipsShaverConfigFlow,
)

ADDRESS = "F4:B3:B1:AA:BB:CC"
SHAVER_UUID = "8d560100-3cb9-4387-a7e8-b79d826a7025"


def _flow() -> PhilipsShaverConfigFlow:
    flow = PhilipsShaverConfigFlow()
    flow.flow_id = "test-flow"
    flow.handler = "philips_shaver"
    flow.discovery_info = None
    flow.hass = SimpleNamespace()
    return flow


# --- user_bleak discovered-device picker ----------------------------------

def _adv(address: str, *, name="Shaver S9000", rssi=-60, age=5.0,
         uuids=(SHAVER_UUID,)):
    return SimpleNamespace(
        address=address,
        name=name,
        rssi=rssi,
        time=time.monotonic() - age,
        service_uuids=list(uuids),
    )


def _patch_discoveries(monkeypatch, infos) -> None:
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow."
        "async_discovered_service_info",
        lambda hass: infos,
    )


def _patch_paths(monkeypatch, paths) -> None:
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow.describe_available_paths",
        MagicMock(return_value=paths),
    )


async def test_picker_lists_shavers_with_via_labels(monkeypatch) -> None:
    _patch_discoveries(monkeypatch, [
        _adv(ADDRESS),
        _adv("11:22:33:44:55:66", name="SomeSpeaker", uuids=["0000fe0f-..."]),
    ])
    _patch_paths(monkeypatch, [
        {"name": "hci0 (00:0A:CD:46:B2:2D)", "rssi": -60, "is_local": True},
    ])
    flow = _flow()

    result = await flow.async_step_user_bleak()

    assert result["type"] == FlowResultType.FORM
    schema_key = next(iter(result["data_schema"].schema))
    options = result["data_schema"].schema[schema_key].config["options"]
    # Only the shaver + the manual sentinel — the speaker is filtered out.
    assert len(options) == 2
    assert options[0]["value"] == ADDRESS
    assert "Shaver S9000" in options[0]["label"]
    assert "dBm" in options[0]["label"]
    assert "via hci0" in options[0]["label"]
    assert options[1]["value"] == _MANUAL_ADDRESS


async def test_picker_marks_proxy_carrier(monkeypatch) -> None:
    _patch_discoveries(monkeypatch, [_adv(ADDRESS)])
    _patch_paths(monkeypatch, [
        {"name": "atom-lite", "rssi": -55, "is_local": False},
    ])
    flow = _flow()

    result = await flow.async_step_user_bleak()
    schema_key = next(iter(result["data_schema"].schema))
    options = result["data_schema"].schema[schema_key].config["options"]
    assert "via atom-lite (proxy)" in options[0]["label"]


async def test_manual_sentinel_switches_to_free_text(monkeypatch) -> None:
    _patch_discoveries(monkeypatch, [_adv(ADDRESS)])
    _patch_paths(monkeypatch, [])
    flow = _flow()

    result = await flow.async_step_user_bleak({"address": _MANUAL_ADDRESS})

    assert flow._manual_address_entry is True
    assert result["type"] == FlowResultType.FORM
    schema_key = next(iter(result["data_schema"].schema))
    # Free-text field, not a selector.
    assert result["data_schema"].schema[schema_key] is str


async def test_no_discoveries_falls_back_to_free_text(monkeypatch) -> None:
    _patch_discoveries(monkeypatch, [])
    flow = _flow()

    result = await flow.async_step_user_bleak()
    schema_key = next(iter(result["data_schema"].schema))
    assert result["data_schema"].schema[schema_key] is str


# --- detailed already-configured abort ------------------------------------

def _existing_entry(*, unique_id=ADDRESS, transport=None, disabled=False):
    return SimpleNamespace(
        unique_id=unique_id,
        data={"transport_type": transport} if transport else {},
        disabled_by="user" if disabled else None,
    )


async def test_abort_detail_names_transport_and_status() -> None:
    flow = _flow()
    flow.context = {"unique_id": ADDRESS}
    flow._async_current_entries = MagicMock(
        return_value=[_existing_entry(transport="esp_bridge", disabled=True)]
    )

    with pytest.raises(AbortFlow) as err:
        flow._abort_if_already_configured()

    assert err.value.reason == "already_configured_detail"
    assert err.value.description_placeholders == {
        "transport": "ESP32 Bridge",
        "status": "disabled",
    }


async def test_abort_detail_direct_ble_active() -> None:
    flow = _flow()
    flow.context = {"unique_id": ADDRESS}
    flow._async_current_entries = MagicMock(return_value=[_existing_entry()])

    with pytest.raises(AbortFlow) as err:
        flow._abort_if_already_configured()

    assert err.value.description_placeholders == {
        "transport": "Direct Bluetooth",
        "status": "active",
    }


async def test_no_abort_for_other_unique_id() -> None:
    flow = _flow()
    flow.context = {"unique_id": "AA:AA:AA:AA:AA:AA"}
    flow._async_current_entries = MagicMock(return_value=[_existing_entry()])

    flow._abort_if_already_configured()  # must not raise


# --- event-probe based ESP redirect ---------------------------------------

def _esp_entry(*, disabled=False, available=True):
    return SimpleNamespace(
        title="Atom S3R",
        disabled_by="user" if disabled else None,
        runtime_data=SimpleNamespace(available=available),
        data={"device_name": "atom-s3r"},
    )


async def test_find_esp_bridge_matches_identity_of_asleep_shaver() -> None:
    flow = _flow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=MagicMock(return_value=[_esp_entry()])
        )
    )
    flow._detect_esp_bridge_ids = MagicMock(return_value=["shaver", "oneblade"])
    flow._probe_shaver_bridges = AsyncMock(return_value=[
        # Asleep: live mac zeroed, but the NVS identity matches.
        ("shaver", {"identity_address": ADDRESS.lower(),
                    "mac": "00:00:00:00:00:00"}),
        ("oneblade", None),  # e.g. a Sonicare slot — never answered
    ])

    match = await flow._find_esp_bridge_for_mac(ADDRESS)

    assert match == {
        "device_name": "atom_s3r",
        "bridge_id": "shaver",
        "info": {"identity_address": ADDRESS.lower(),
                 "mac": "00:00:00:00:00:00"},
    }
    flow._probe_shaver_bridges.assert_awaited_once_with(
        "atom_s3r", ["shaver", "oneblade"]
    )


async def test_find_esp_bridge_skips_unreachable_entries() -> None:
    flow = _flow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=MagicMock(return_value=[
                _esp_entry(disabled=True),
                _esp_entry(available=False),
            ])
        )
    )
    flow._probe_shaver_bridges = AsyncMock()

    assert await flow._find_esp_bridge_for_mac(ADDRESS) is None
    flow._probe_shaver_bridges.assert_not_called()


async def test_find_esp_bridge_no_match_returns_none() -> None:
    flow = _flow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=MagicMock(return_value=[_esp_entry()])
        )
    )
    flow._detect_esp_bridge_ids = MagicMock(return_value=["shaver"])
    flow._probe_shaver_bridges = AsyncMock(return_value=[
        ("shaver", {"identity_address": "", "mac": "00:00:00:00:00:00"}),
    ])

    assert await flow._find_esp_bridge_for_mac(ADDRESS) is None


# --- sole-ESP auto-select --------------------------------------------------

async def test_sole_reachable_esp_skips_dropdown() -> None:
    flow = _flow()
    flow._get_esphome_device_options = AsyncMock(return_value=[
        {"value": "atom-s3r", "label": "Atom S3R (atom-s3r), 1 🔗"},
    ])
    flow._offline_esp_values = set()
    flow._detect_esp_bridge_ids = MagicMock(return_value=["shaver"])
    flow._esp_bridge_health_check = AsyncMock(return_value={"type": "health"})

    result = await flow.async_step_esp_bridge()

    assert result == {"type": "health"}
    assert flow.fetched_esp_device_name == "atom_s3r"
    assert flow.fetched_esp_bridge_id == "shaver"


async def test_sole_offline_esp_still_shows_dropdown() -> None:
    flow = _flow()
    flow._get_esphome_device_options = AsyncMock(return_value=[
        {"value": "atom-s3r", "label": "⚪ Atom S3R (atom-s3r)"},
    ])
    flow._offline_esp_values = {"atom-s3r"}
    flow._esp_bridge_health_check = AsyncMock()

    result = await flow.async_step_esp_bridge()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "esp_bridge"
    flow._esp_bridge_health_check.assert_not_called()


# --- BLE-Security row -------------------------------------------------------

def test_device_info_shows_bonded_security() -> None:
    text = PhilipsShaverConfigFlow._get_device_info_text(
        {"pairing": "bonded", "model_number": "XP9201"}
    )
    assert "BLE Security" in text
    assert "Bonded (encrypted)" in text


def test_device_info_shows_open_gatt() -> None:
    text = PhilipsShaverConfigFlow._get_device_info_text({"pairing": "open_gatt"})
    assert "Unpaired (no encryption)" in text


def test_device_info_no_row_when_indeterminate() -> None:
    text = PhilipsShaverConfigFlow._get_device_info_text({"model_number": "XP9201"})
    assert "BLE Security" not in text
