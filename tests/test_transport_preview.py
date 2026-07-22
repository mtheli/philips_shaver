"""Tests for the connection-path preview on bluetooth_confirm.

habluetooth routes connects through the strongest scanner, so a "Direct
Bluetooth" discovery may in fact ride a stock ESPHome bluetooth_proxy.
``_transport_lines`` names the likely carrier up front and — unlike the
Sonicare integration, where proxy pairing is model-dependent — warns
hard when a standard proxy would carry the connection: Philips shavers
pair via LE Secure Connections, which a standard proxy cannot complete.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.philips_shaver.config_flow import PhilipsShaverConfigFlow

ADDRESS = "F4:B3:B1:AA:BB:CC"


def _flow() -> PhilipsShaverConfigFlow:
    flow = PhilipsShaverConfigFlow()
    flow.flow_id = "test-flow"
    flow.handler = "philips_shaver"
    flow.discovery_info = SimpleNamespace(address=ADDRESS, name="Philips Shaver")
    flow.hass = SimpleNamespace()
    return flow


def _patch_paths(monkeypatch, paths) -> None:
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow.describe_available_paths",
        MagicMock(return_value=paths),
    )


def test_no_paths_yields_empty_lines(monkeypatch) -> None:
    _patch_paths(monkeypatch, [])
    assert _flow()._transport_lines() == ("", "")


def test_local_adapter_via_direct_bluetooth(monkeypatch) -> None:
    _patch_paths(monkeypatch, [
        {"name": "hci0 (00:0A:CD:46:B2:2D)", "rssi": -76, "is_local": True},
    ])
    via, warning = _flow()._transport_lines()
    # Same "via <class> (<detail>)" framing as the capabilities dialog.
    assert via == " via **Direct Bluetooth** (hci0, -76 dBm)"
    assert warning == ""


def test_proxy_via_and_hard_warning(monkeypatch) -> None:
    _patch_paths(monkeypatch, [
        # Remote scanner names may carry a MAC suffix — the label must
        # show the bare name, no doubled parens.
        {"name": "atom-s3r (98:88:E0:0E:DA:D2)", "rssi": -61, "is_local": False},
    ])
    via, warning = _flow()._transport_lines()
    assert via == " via **Bluetooth proxy** (atom-s3r, -61 dBm)"
    assert "98:88" not in via
    assert 'ha-alert alert-type="warning"' in warning
    assert "<b>atom-s3r</b> (-61 dBm)" in warning
    # The shaver warning is unconditional and hard — no "model-dependent"
    # softening: LESC pairing over a standard proxy fails outright.
    assert "cannot pair over a standard Bluetooth proxy" in warning
    assert "will fail" in warning
    # No local adapter in range → point at the working alternatives.
    assert "ESP32 bridge" in warning


def test_proxy_preferred_with_local_fallback_hint(monkeypatch) -> None:
    _patch_paths(monkeypatch, [
        {"name": "atom-lite", "rssi": -64, "is_local": False},
        {"name": "hci0 (00:0A:CD:46:B2:2D)", "rssi": -82, "is_local": True},
    ])
    via, warning = _flow()._transport_lines()
    assert via == " via **Bluetooth proxy** (atom-lite, -64 dBm)"
    assert 'ha-alert alert-type="warning"' in warning
    assert "<b>hci0</b>" in warning
    assert "strongest signal" in warning


def test_local_strongest_wins_over_weaker_proxy(monkeypatch) -> None:
    # Sorting happens in describe_available_paths; the lines trust entry
    # order — strongest first.
    _patch_paths(monkeypatch, [
        {"name": "hci0 (00:0A:CD:46:B2:2D)", "rssi": -60, "is_local": True},
        {"name": "atom-lite", "rssi": -85, "is_local": False},
    ])
    via, warning = _flow()._transport_lines()
    assert via == " via **Direct Bluetooth** (hci0, -60 dBm)"
    assert warning == ""


def test_connection_status_text_success_alert() -> None:
    text = PhilipsShaverConfigFlow._get_connection_status_text(
        "esp_bridge", "atom-s3r / shaver"
    )
    assert 'ha-alert alert-type="success"' in text
    assert "<b>ESP32 Bridge</b> (atom-s3r / shaver)" in text


def test_connection_status_text_marks_proxy_probe() -> None:
    text = PhilipsShaverConfigFlow._get_connection_status_text(
        None, "atom-lite", via_proxy=True
    )
    assert "<b>Bluetooth proxy</b> (atom-lite)" in text


def test_connection_status_text_direct() -> None:
    text = PhilipsShaverConfigFlow._get_connection_status_text(None, "hci0")
    assert "<b>Direct Bluetooth</b> (hci0)" in text


def test_available_paths_drop_stale_rssi_invalidation(monkeypatch) -> None:
    """A BlueZ -127 invalidation entry must not be offered as a carrier.

    Seen live 2026-07-22: a sleeping OneBlade rendered as "via Direct
    Bluetooth (hci0, -127 dBm)" although hci0 did not see the device at
    all — the -127 sentinel is a stale history entry, the same one the
    sleep gate keys on.
    """
    from custom_components.philips_shaver import transport as tr

    class _FakeHaScanner:
        name = "hci0 (00:0A:CD:46:B2:2D)"

    monkeypatch.setattr(tr, "HaScanner", _FakeHaScanner)
    stale = SimpleNamespace(
        scanner=_FakeHaScanner(),
        advertisement=SimpleNamespace(rssi=-127),
    )
    live = SimpleNamespace(
        scanner=SimpleNamespace(name="atom-s3r (98:88:E0:0E:DA:D2)"),
        advertisement=SimpleNamespace(rssi=-61),
    )
    monkeypatch.setattr(
        tr, "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: [stale, live],
    )

    paths = tr.describe_available_paths(SimpleNamespace(), ADDRESS)

    assert len(paths) == 1
    assert paths[0]["name"].startswith("atom-s3r")
    assert paths[0]["is_local"] is False


def test_available_paths_all_stale_yields_empty(monkeypatch) -> None:
    from custom_components.philips_shaver import transport as tr

    stale = SimpleNamespace(
        scanner=SimpleNamespace(name="hci0"),
        advertisement=SimpleNamespace(rssi=-127),
    )
    monkeypatch.setattr(
        tr, "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: [stale],
    )

    assert tr.describe_available_paths(SimpleNamespace(), ADDRESS) == []
