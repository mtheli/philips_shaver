"""Tests for the direct-BLE probe as a background progress task.

The capabilities probe used to run inline in the submit handler, freezing
the discovery-confirm / manual-address dialogs on a mute submit button
for up to half a minute. It now runs behind async_show_progress, and
async_step_ble_probe_finish routes the boxed outcome back to the origin
step — including the shaver-specific hard dead-end when a standard
Bluetooth proxy carried the probe (LESC pairing cannot complete there).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.data_entry_flow import FlowResultType

from custom_components.philips_shaver.config_flow import PhilipsShaverConfigFlow

ADDRESS = "F4:B3:B1:AA:BB:CC"


class _FakeTask:
    def __init__(self, done: bool, result=None) -> None:
        self._done = done
        self._result = result

    def done(self) -> bool:
        return self._done

    def result(self):
        return self._result


def _flow(discovery: bool = True) -> PhilipsShaverConfigFlow:
    flow = PhilipsShaverConfigFlow()
    flow.flow_id = "test-flow"
    flow.handler = "philips_shaver"
    if discovery:
        flow.discovery_info = SimpleNamespace(address=ADDRESS, name="Shaver S9000")
    else:
        flow.discovery_info = None

    def _create_task(coro, *args, **kwargs):
        coro.close()  # never actually run the coroutine in unit tests
        return _FakeTask(done=False)

    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_create_task),
        services=SimpleNamespace(async_call=AsyncMock()),
    )
    return flow


# --- progress bookkeeping -------------------------------------------------

async def test_start_probe_shows_progress() -> None:
    flow = _flow()
    result = flow._start_ble_probe("bluetooth_confirm", ADDRESS)

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "ble_probing"
    assert result["description_placeholders"]["name"] == "Shaver S9000"
    assert flow._ble_probe_origin == "bluetooth_confirm"
    assert flow._ble_probe_address == ADDRESS
    assert flow._ble_probe_task is not None


async def test_running_probe_reenters_progress() -> None:
    flow = _flow()
    flow._ble_probe_task = _FakeTask(done=False)
    result = flow._ble_probe_progress("bluetooth_confirm")
    assert result["type"] == FlowResultType.SHOW_PROGRESS


async def test_done_probe_routes_to_finish() -> None:
    flow = _flow()
    flow._ble_probe_task = _FakeTask(done=True, result={"ok": True, "data": {}})
    result = flow._ble_probe_progress("bluetooth_confirm")
    assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
    assert result["step_id"] == "ble_probe_finish"
    assert flow._ble_probe_task is None
    assert flow._ble_probe_result == {"ok": True, "data": {}}


async def test_no_probe_returns_none() -> None:
    flow = _flow()
    assert flow._ble_probe_progress("bluetooth_confirm") is None


# --- finish routing: success ----------------------------------------------

async def test_finish_success_routes_to_capabilities() -> None:
    flow = _flow()
    flow._ble_probe_origin = "bluetooth_confirm"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": True, "data": {"model_number": "S9000"}}
    flow.async_step_show_capabilities = AsyncMock(return_value={"type": "caps"})

    result = await flow.async_step_ble_probe_finish()

    assert result == {"type": "caps"}
    assert flow.fetched_data == {"model_number": "S9000"}
    assert flow.fetched_address == ADDRESS
    assert flow.fetched_name == "Shaver S9000"


# --- finish routing: pairing paths ----------------------------------------

async def test_finish_not_paired_local_routes_to_pairing() -> None:
    flow = _flow()
    flow._ble_probe_origin = "bluetooth_confirm"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "not_paired"}
    flow._probe_via_proxy = False
    flow._route_to_pairing = AsyncMock(return_value={"type": "pairing"})

    result = await flow.async_step_ble_probe_finish()

    assert result == {"type": "pairing"}
    assert flow._pair_address == ADDRESS


async def test_finish_not_paired_proxy_hits_hard_dead_end() -> None:
    flow = _flow()
    flow._ble_probe_origin = "bluetooth_confirm"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "not_paired"}
    flow._probe_via_proxy = True
    flow._probe_proxy_name = "atom-lite"
    flow._route_to_pairing = AsyncMock()  # must NOT be taken

    result = await flow.async_step_ble_probe_finish()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "not_paired_proxy"
    assert result["description_placeholders"]["proxy_name"] == "atom-lite"
    assert result["description_placeholders"]["address"] == ADDRESS
    # The dead-end itself renders as a red alert so it can't be skimmed past.
    alert = result["description_placeholders"]["alert"]
    assert 'ha-alert alert-type="error"' in alert
    assert "<b>atom-lite</b>" in alert
    assert "will not succeed" in alert
    flow._route_to_pairing.assert_not_called()


async def test_finish_stale_bond_routes_like_not_paired() -> None:
    flow = _flow()
    flow._ble_probe_origin = "user_bleak"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "stale_bond"}
    flow._probe_via_proxy = False
    flow._route_to_pairing = AsyncMock(return_value={"type": "pairing"})

    result = await flow.async_step_ble_probe_finish()

    assert result == {"type": "pairing"}
    assert flow._pair_address == ADDRESS


# --- finish routing: errors back to the origin step -----------------------

async def test_finish_asleep_discovery_sets_alert_and_rerenders() -> None:
    flow = _flow()
    flow._ble_probe_origin = "bluetooth_confirm"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "asleep"}
    flow.async_step_bluetooth_confirm = AsyncMock(return_value={"type": "form"})

    result = await flow.async_step_ble_probe_finish()

    assert result == {"type": "form"}
    assert 'ha-alert alert-type="error"' in flow._confirm_status
    assert "asleep" in flow._confirm_status


async def test_finish_generic_discovery_points_at_logs() -> None:
    flow = _flow()
    flow._ble_probe_origin = "bluetooth_confirm"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "unknown"}
    flow.async_step_bluetooth_confirm = AsyncMock(return_value={"type": "form"})

    await flow.async_step_ble_probe_finish()

    assert "Settings → System → Logs" in flow._confirm_status


def _patch_no_discoveries(monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow."
        "async_discovered_service_info",
        lambda hass: [],
    )


async def test_finish_manual_error_renders_on_user_bleak_form(monkeypatch) -> None:
    _patch_no_discoveries(monkeypatch)
    flow = _flow(discovery=False)
    flow._ble_probe_origin = "user_bleak"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "cannot_connect"}
    flow._probe_via_proxy = False

    result = await flow.async_step_ble_probe_finish()

    # user_bleak has a schema, so the error renders as errors["base"].
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user_bleak"
    assert result["errors"] == {"base": "cannot_connect"}
    assert flow._manual_error == ""  # consumed


async def test_finish_manual_asleep_maps_to_device_asleep(monkeypatch) -> None:
    _patch_no_discoveries(monkeypatch)
    flow = _flow(discovery=False)
    flow._ble_probe_origin = "user_bleak"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "asleep"}

    result = await flow.async_step_ble_probe_finish()

    assert result["errors"] == {"base": "device_asleep"}


async def test_finish_pair_origin_maps_errors_onto_pair_form() -> None:
    flow = _flow(discovery=False)
    flow._pair_address = ADDRESS
    flow._ble_probe_origin = "pair"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "pairing_failed"}

    result = await flow.async_step_ble_probe_finish()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pair"
    assert result["errors"] == {"base": "pairing_failed"}


async def test_finish_pair_origin_not_paired_falls_back_to_manual() -> None:
    flow = _flow(discovery=False)
    flow._pair_address = ADDRESS
    flow._ble_probe_origin = "pair"
    flow._ble_probe_address = ADDRESS
    flow._ble_probe_result = {"ok": False, "error": "not_paired"}
    flow._probe_via_proxy = False
    flow.async_step_not_paired = AsyncMock(return_value={"type": "manual"})

    result = await flow.async_step_ble_probe_finish()

    assert result == {"type": "manual"}


# --- step wiring ----------------------------------------------------------

async def test_user_bleak_submit_starts_probe(monkeypatch) -> None:
    flow = _flow(discovery=False)
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_already_configured = MagicMock()
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow.describe_available_paths",
        MagicMock(return_value=[{"name": "hci0", "rssi": -60, "is_local": True}]),
    )
    monkeypatch.setattr(
        "custom_components.philips_shaver.dbus_pairing.is_dbus_available",
        lambda: False,
    )

    result = await flow.async_step_user_bleak({"address": "f4:b3:b1:aa:bb:cc"})

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert flow._ble_probe_origin == "user_bleak"
    assert flow._ble_probe_address == ADDRESS


async def test_user_bleak_skips_dbus_precheck_on_proxy_path(monkeypatch) -> None:
    flow = _flow(discovery=False)
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_already_configured = MagicMock()
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow.describe_available_paths",
        MagicMock(return_value=[{"name": "atom-lite", "rssi": -55, "is_local": False}]),
    )
    precheck = MagicMock(side_effect=AssertionError("must not be called"))
    monkeypatch.setattr(
        "custom_components.philips_shaver.dbus_pairing.is_dbus_available",
        precheck,
    )

    result = await flow.async_step_user_bleak({"address": ADDRESS})

    # The BlueZ bond state says nothing about a proxy-carried connection:
    # go straight to the probe.
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    precheck.assert_not_called()
