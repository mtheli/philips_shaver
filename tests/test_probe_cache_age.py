"""The slot picker must not render a probe from an earlier lifetime.

The probe cache exists to carry the ESP dropdown's result into the slot
picker a moment later. Without an expiry it also survives far longer: a
zeroconf discovery builds the picker in the background, and the banner it
produces can sit unopened for hours. Home Assistant re-runs the step when
that banner is clicked, so the dialog would be current — except the cache
answers first and shows the bridge state from when the flow was created.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import custom_components.philips_shaver.config_flow as cf
from custom_components.philips_shaver.config_flow import PhilipsShaverConfigFlow

BONDED = {
    "bridge_id": "shaver_1", "friendly_name": "Bathroom Shaver",
    "mac": "EC:EC:66:27:F0:ED", "identity_address": "EC:EC:66:27:F0:ED",
    "paired": "true", "ble_connected": "false", "version": "1.12.0",
}
FREE = {
    "bridge_id": "shaver_1", "friendly_name": "Bathroom Shaver",
    "mac": "00:00:00:00:00:00", "identity_address": "",
    "paired": "false", "ble_connected": "false", "version": "1.12.0",
}
OTHER = {
    "bridge_id": "shaver_2", "friendly_name": "Guest Shaver",
    "mac": "00:00:00:00:00:00", "identity_address": "",
    "paired": "false", "ble_connected": "false", "version": "1.12.0",
}


def _flow(probe_result):
    flow = PhilipsShaverConfigFlow()
    flow.flow_id = "t"
    flow.handler = "philips_shaver"
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(components=set()), data={}
    )
    flow.fetched_esp_device_name = "atom_s3r"
    flow._esp_bridge_ids = ["shaver_1", "shaver_2"]
    flow._async_current_entries = lambda: []
    flow._probe_shaver_bridges = AsyncMock(
        return_value=[("shaver_1", probe_result), ("shaver_2", OTHER)]
    )
    flow._probed_bridges = {
        "atom_s3r": [("shaver_1", BONDED), ("shaver_2", OTHER)]
    }
    flow._probed_at = {"atom_s3r": 0.0}
    return flow


async def test_stale_probe_is_discarded(monkeypatch) -> None:
    flow = _flow(FREE)
    monkeypatch.setattr(
        cf.time, "monotonic", lambda: cf._PROBE_CACHE_MAX_AGE + 1.0
    )

    await flow.async_step_esp_select_device()

    flow._probe_shaver_bridges.assert_awaited_once()


async def test_fresh_probe_is_reused(monkeypatch) -> None:
    flow = _flow(FREE)
    monkeypatch.setattr(
        cf.time, "monotonic", lambda: cf._PROBE_CACHE_MAX_AGE - 1.0
    )

    await flow.async_step_esp_select_device()

    flow._probe_shaver_bridges.assert_not_awaited()


# --- offline ESPs in the dropdown ----------------------------------------

def _esp_entry(title, device_name, *, available, disabled=False):
    return SimpleNamespace(
        title=title,
        data={"device_name": device_name},
        disabled_by="user" if disabled else None,
        runtime_data=SimpleNamespace(available=available),
    )


async def _dropdown(flow):
    return await flow._get_esphome_device_options()


async def test_offline_esp_listed_only_when_it_is_ours(monkeypatch) -> None:
    """An unreachable ESP cannot be probed, so it may only be shown when an
    existing entry proves it is our bridge.

    Both integrations register the same ESPHome service names, so without a
    probe there is nothing to tell them apart — listing every offline node
    would advertise the other integration's hardware.
    """
    flow = PhilipsShaverConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(components=set()), data={},
        config_entries=SimpleNamespace(
            async_entries=lambda domain: [
                _esp_entry("Atom S3R BLE Bridge", "atom-s3r", available=False),
                _esp_entry("Atom Lite BLE Bridge", "atom-lite", available=False),
            ]
        ),
        services=SimpleNamespace(
            has_service=lambda *_: False,
            async_services=lambda: {"esphome": {
                "atom_s3r_ble_get_info_shaver_1": None,
                "atom_lite_ble_get_info_hx742a": None,
            }},
        ),
    )
    # Only the S3R was ever set up as a shaver bridge.
    flow._async_current_entries = lambda: [
        SimpleNamespace(data={"esp_device_name": "atom-s3r"})
    ]

    options = await _dropdown(flow)

    values = [o["value"] for o in options]
    assert values == ["atom-s3r"], values
    assert not any("lite" in v for v in values), (
        "listed another integration's bridge"
    )


async def test_reachable_esp_that_answers_no_probe_is_not_listed() -> None:
    """The case that actually happens: the other integration's bridge.

    A Sonicare bridge is online and registers the same ESPHome service
    names, so it looks reachable — it just never answers on our event
    channel. Without an entry vouching for it, that is indistinguishable
    from our own bridge being unreachable, so it must stay hidden.
    """
    flow = PhilipsShaverConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(components=set()), data={},
        config_entries=SimpleNamespace(
            async_entries=lambda domain: [
                _esp_entry("Atom S3R BLE Bridge", "atom-s3r", available=True),
                _esp_entry("Atom Lite BLE Bridge", "atom-lite", available=True),
            ]
        ),
        services=SimpleNamespace(
            has_service=lambda *_: False,
            async_services=lambda: {"esphome": {
                "atom_s3r_ble_get_info_shaver_1": None,
                "atom_lite_ble_get_info_hx742a": None,
            }},
        ),
    )
    flow._async_current_entries = lambda: [
        SimpleNamespace(data={"esp_device_name": "atom-s3r"})
    ]
    # Neither answers — the S3R because it is genuinely unreachable, the
    # Lite because it belongs to the other integration.
    flow._probe_shaver_bridges = AsyncMock(
        side_effect=lambda dev, dids: [(did, None) for did in dids]
    )

    options = await flow._get_esphome_device_options()

    values = [o["value"] for o in options]
    assert values == ["atom-s3r"], values
    assert options[0]["label"].startswith("⚪"), options
