"""Tests for the async_show_progress two-phase wait_pair flow.

The pairing wait used to block the flow handler for up to ~65 s behind a
blank spinner. It now runs as two background phases (arming → scanning)
surfaced via async_show_progress, and async_step_pair_finish renders the
captured outcome. Ported from the Sonicare integration; the shaver adds
the ``pair_failed`` bridge status (stale bond on the shaver side).
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

    def _create_task(coro, *args, **kwargs):
        coro.close()  # never actually run the coroutine in unit tests
        return _FakeTask(done=False)

    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_create_task),
        services=SimpleNamespace(async_call=AsyncMock()),
    )
    return flow


# --- phase orchestration --------------------------------------------------

async def test_first_call_arms_and_shows_progress() -> None:
    flow = _flow()
    result = await flow.async_step_wait_pair()

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "pair_arming"
    assert flow._pair_arm_task is not None
    assert "atom_s3r / shaver" in result["description_placeholders"]["target"]


async def test_arm_success_transitions_to_scanning() -> None:
    flow = _flow()
    flow._pair_arm_task = _FakeTask(done=True, result=True)

    result = await flow.async_step_wait_pair()

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "pair_scanning"
    assert flow._pair_arm_task is None
    assert flow._pair_scan_task is not None


async def test_arm_failure_routes_to_finish_with_error() -> None:
    flow = _flow()
    flow._pair_arm_task = _FakeTask(done=True, result=False)

    result = await flow.async_step_wait_pair()

    assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
    assert result["step_id"] == "pair_finish"
    assert flow._pair_result == {"error": "service_call_failed"}


async def test_scan_done_routes_to_finish() -> None:
    flow = _flow()
    flow._pair_scan_task = _FakeTask(
        done=True, result={"status": "pair_complete", "mac": "AA:BB:CC:DD:EE:FF"}
    )

    result = await flow.async_step_wait_pair()

    assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
    assert flow._pair_result == {
        "status": "pair_complete", "mac": "AA:BB:CC:DD:EE:FF"
    }
    assert flow._pair_scan_task is None


async def test_running_scan_keeps_progress() -> None:
    flow = _flow()
    flow._pair_scan_task = _FakeTask(done=False)

    result = await flow.async_step_wait_pair()

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "pair_scanning"


# --- pair_finish outcomes -------------------------------------------------

async def test_finish_arm_error_renders_request_pair() -> None:
    flow = _flow()
    flow._pair_result = {"error": "service_call_failed"}

    result = await flow.async_step_pair_finish()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "request_pair"
    assert result["errors"] == {"base": "service_call_failed"}


async def test_finish_timeout_renders_request_pair_and_stands_down() -> None:
    flow = _flow()
    flow._pair_result = {"status": "pair_timeout"}
    flow._pair_svc_name = "atom_s3r_ble_pair_mode_shaver"
    unsub = MagicMock()
    flow._pair_unsub = unsub

    result = await flow.async_step_pair_finish()

    assert result["errors"] == {"base": "pair_timeout"}
    unsub.assert_called_once()
    assert flow._pair_unsub is None
    # Best-effort stand-down so a stray shaver isn't auto-bonded later.
    call = flow.hass.services.async_call.call_args
    assert call.args[1] == "atom_s3r_ble_pair_mode_shaver"
    assert call.args[2]["enabled"] is False
    assert flow._pair_svc_name == ""


async def test_finish_stale_bond_maps_to_dedicated_error() -> None:
    flow = _flow()
    flow._pair_result = {
        "status": "pair_failed", "reason": "auth_max_failures"
    }

    result = await flow.async_step_pair_finish()

    assert result["errors"] == {"base": "pair_failed_stale_bond"}


async def test_finish_generic_pair_failed_maps_to_timeout_text() -> None:
    flow = _flow()
    flow._pair_result = {"status": "pair_failed", "reason": "other"}

    result = await flow.async_step_pair_finish()

    assert result["errors"] == {"base": "pair_timeout"}


async def test_finish_complete_routes_to_status_with_banner() -> None:
    flow = _flow()
    flow._pair_result = {
        "status": "pair_complete",
        "identity_address": "f4:b3:b1:aa:bb:cc",
    }
    flow.fetched_bridge_info = {"paired": "false"}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_already_configured = MagicMock()
    flow._esp_bridge_health_check = AsyncMock(return_value={"type": "next"})

    result = await flow.async_step_pair_finish()

    assert result == {"type": "next"}
    # Refetch the freshly-bound state; banner on the next status render.
    assert flow.fetched_bridge_info is None
    assert flow._just_paired is True
    assert flow.fetched_address == "f4:b3:b1:aa:bb:cc"
    flow.async_set_unique_id.assert_awaited_once_with(
        "F4:B3:B1:AA:BB:CC", raise_on_progress=False
    )
    # Clean completion must NOT stand the bridge down.
    flow.hass.services.async_call.assert_not_called()


async def test_finish_complete_without_identity_still_routes() -> None:
    flow = _flow()
    flow._pair_result = {"status": "pair_complete"}
    flow._esp_bridge_health_check = AsyncMock(return_value={"type": "next"})

    result = await flow.async_step_pair_finish()

    assert result == {"type": "next"}
    assert flow._just_paired is True
