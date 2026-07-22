"""Tests for the ESP capabilities read as a progress task and the
bonded-slot routing.

The "Read capabilities" click used to block the esp_bridge_status handler
for the whole bridge round-trip; it now runs behind async_show_progress
with the outcome rendered by esp_read_finish. A slot that is bonded on
the bridge but not set up in Home Assistant routes through a small action
menu (set up / unpair) instead of dead-ending on the status screen.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.data_entry_flow import FlowResultType

from custom_components.philips_shaver.config_flow import PhilipsShaverConfigFlow


class _FakeTask:
    def __init__(self, done: bool, result=None) -> None:
        self._done = done
        self._result = result

    def done(self) -> bool:
        return self._done

    def result(self):
        return self._result


def _flow() -> PhilipsShaverConfigFlow:
    flow = PhilipsShaverConfigFlow()
    flow.flow_id = "test-flow"
    flow.handler = "philips_shaver"
    flow.fetched_esp_device_name = "atom_s3r"
    flow.fetched_esp_bridge_id = "shaver"
    flow.fetched_bridge_info = {
        "version": "1.11.0",
        "ble_connected": "true",
        "paired": "true",
        "identity_source": "nvs",
        "mac": "F4:B3:B1:AA:BB:CC",
    }

    def _create_task(coro, *args, **kwargs):
        coro.close()  # never actually run the coroutine in unit tests
        return _FakeTask(done=False)

    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_create_task),
        services=SimpleNamespace(async_call=AsyncMock()),
    )
    return flow


# --- esp capabilities read as progress task -------------------------------

async def test_submit_starts_progress() -> None:
    flow = _flow()
    result = await flow.async_step_esp_bridge_status(user_input={})

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "esp_reading"
    assert flow._esp_caps_task is not None
    assert "atom_s3r / shaver" in result["description_placeholders"]["target"]


async def test_running_read_keeps_progress() -> None:
    flow = _flow()
    flow._esp_caps_task = _FakeTask(done=False)
    result = await flow.async_step_esp_bridge_status()
    assert result["type"] == FlowResultType.SHOW_PROGRESS


async def test_done_read_routes_to_finish() -> None:
    flow = _flow()
    flow._esp_caps_task = _FakeTask(done=True, result={"ok": True, "caps": {}})
    result = await flow.async_step_esp_bridge_status()
    assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
    assert result["step_id"] == "esp_read_finish"
    assert flow._esp_caps_result == {"ok": True, "caps": {}}
    assert flow._esp_caps_task is None


async def test_finish_success_routes_to_capabilities() -> None:
    flow = _flow()
    flow._esp_caps_result = {
        "ok": True,
        "caps": {"shaver_mac": "f4:b3:b1:aa:bb:cc", "model_number": "XP9201"},
    }
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_already_configured = MagicMock()
    flow.async_step_show_capabilities = AsyncMock(return_value={"type": "caps"})

    result = await flow.async_step_esp_read_finish()

    assert result == {"type": "caps"}
    flow.async_set_unique_id.assert_awaited_once_with(
        "F4:B3:B1:AA:BB:CC", raise_on_progress=False
    )
    assert flow.fetched_data["bridge_version"] == "1.11.0"
    assert flow.fetched_name == "XP9201"
    assert flow.fetched_transport_type == "esp_bridge"


async def test_finish_error_surfaces_alert_on_status_step() -> None:
    flow = _flow()
    flow._esp_caps_result = {"ok": False, "error": "cannot_connect"}
    flow.async_step_esp_bridge_status = AsyncMock(return_value={"type": "form"})

    result = await flow.async_step_esp_read_finish()

    assert result == {"type": "form"}
    assert "bridge" in flow._esp_read_error


async def test_finish_unknown_error_points_at_logs() -> None:
    flow = _flow()
    flow._esp_caps_result = {"ok": False, "error": "unknown"}
    flow.async_step_esp_bridge_status = AsyncMock(return_value={"type": "form"})

    await flow.async_step_esp_read_finish()

    assert "Settings → System → Logs" in flow._esp_read_error


# --- status render banners ------------------------------------------------

def _patch_transport_refresh(monkeypatch, flow) -> None:
    """Keep the render path's bridge-info refresh from probing anything."""
    fake = MagicMock()
    fake.return_value.connect = AsyncMock(side_effect=RuntimeError("offline"))
    fake.return_value.disconnect = AsyncMock()
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow.EspBridgeTransport", fake
    )


async def test_just_paired_banner_renders_once(monkeypatch) -> None:
    flow = _flow()
    _patch_transport_refresh(monkeypatch, flow)
    flow._just_paired = True

    result = await flow.async_step_esp_bridge_status()

    assert result["type"] == FlowResultType.FORM
    status = result["description_placeholders"]["status"]
    assert 'ha-alert alert-type="success"' in status
    assert flow._just_paired is False

    result = await flow.async_step_esp_bridge_status()
    assert "success" not in result["description_placeholders"]["status"]


async def test_read_error_alert_renders_once(monkeypatch) -> None:
    flow = _flow()
    _patch_transport_refresh(monkeypatch, flow)
    flow._esp_read_error = "Couldn't read the shaver over the bridge."

    result = await flow.async_step_esp_bridge_status()

    status = result["description_placeholders"]["status"]
    assert 'ha-alert alert-type="error"' in status
    assert flow._esp_read_error == ""


# --- bonded-slot action menu ----------------------------------------------

async def test_bonded_nvs_slot_routes_to_action_menu() -> None:
    flow = _flow()  # paired=true, identity_source=nvs
    result = await flow._route_after_health_check()

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "esp_slot_action"
    assert result["menu_options"] == ["slot_setup", "slot_unpair"]


async def test_yaml_pinned_slot_skips_menu() -> None:
    flow = _flow()
    flow.fetched_bridge_info["identity_source"] = "yaml"
    flow.async_step_esp_bridge_status = AsyncMock(return_value={"type": "status"})

    result = await flow._route_after_health_check()

    assert result == {"type": "status"}


async def test_fresh_pairing_skips_menu() -> None:
    flow = _flow()
    flow._just_paired = True
    flow.async_step_esp_bridge_status = AsyncMock(return_value={"type": "status"})

    result = await flow._route_after_health_check()

    assert result == {"type": "status"}


async def test_unpaired_slot_skips_menu() -> None:
    flow = _flow()
    flow.fetched_bridge_info["paired"] = "false"
    flow.async_step_esp_bridge_status = AsyncMock(return_value={"type": "status"})

    result = await flow._route_after_health_check()

    assert result == {"type": "status"}


async def test_menu_choice_setup_marks_slot_and_continues() -> None:
    flow = _flow()
    flow.async_step_esp_bridge_status = AsyncMock(return_value={"type": "status"})

    result = await flow.async_step_slot_setup()

    assert result == {"type": "status"}
    assert flow._slot_action_chosen is True
    # Re-entering the health-check routing must not re-show the menu.
    result = await flow._route_after_health_check()
    assert result == {"type": "status"}


async def test_menu_choice_unpair_routes_to_reset() -> None:
    flow = _flow()
    flow.async_step_reset_bridge = AsyncMock(return_value={"type": "reset"})

    result = await flow.async_step_slot_unpair()

    assert result == {"type": "reset"}
    assert flow._slot_action_chosen is True


# --- target label ---------------------------------------------------------

async def test_target_label_prefers_friendly_name() -> None:
    flow = _flow()
    flow.fetched_bridge_info["friendly_name"] = "Badezimmer Rasierer"
    assert flow._esp_target_label() == "atom_s3r / Badezimmer Rasierer"


async def test_target_label_falls_back_to_bridge_id() -> None:
    flow = _flow()
    assert flow._esp_target_label() == "atom_s3r / shaver"


async def test_target_label_collapses_without_slot() -> None:
    flow = _flow()
    flow.fetched_esp_bridge_id = ""
    assert flow._esp_target_label() == "atom_s3r"
