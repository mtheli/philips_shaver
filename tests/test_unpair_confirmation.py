"""Tests for the confirmed-unpair helper and the reset_bridge flow steps.

async_unpair_bridge_slot fires ble_unpair and waits for the bridge's
`unpaired` status event, so a silent failure (call returns but the bond
stays) is no longer mistaken for success. The reset_bridge config-flow
step surfaces that as an error instead of dropping the user back onto
the still-bonded status screen.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.data_entry_flow import FlowResultType

from custom_components.philips_shaver.config_flow import PhilipsShaverConfigFlow
from custom_components.philips_shaver.transport import (
    ESP_STATUS_EVENT_NAME,
    UNPAIR_FAILED,
    UNPAIR_OK,
    UNPAIR_UNAVAILABLE,
    UNPAIR_UNCONFIRMED,
    async_unpair_bridge_slot,
)


class _FakeBus:
    def __init__(self) -> None:
        self._cb = None

    def async_listen(self, event_name, cb):
        assert event_name == ESP_STATUS_EVENT_NAME
        self._cb = cb
        return lambda: setattr(self, "_cb", None)

    def emit(self, data: dict) -> None:
        if self._cb is not None:
            self._cb(SimpleNamespace(data=data))


class _FakeServices:
    def __init__(self, *, has: bool, confirm: bool, raises: bool = False) -> None:
        self._has = has
        self._confirm = confirm
        self._raises = raises
        self.bus: _FakeBus | None = None
        self.confirm_bridge_id = "shaver"
        self.calls = 0

    def has_service(self, domain, name) -> bool:
        return self._has

    async def async_call(self, domain, name, data, blocking=False):
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        # A confirming bridge fires the `unpaired` event during the call.
        if self._confirm and self.bus is not None:
            self.bus.emit(
                {"status": "unpaired", "bridge_id": self.confirm_bridge_id}
            )


def _hass(services: _FakeServices):
    bus = _FakeBus()
    services.bus = bus
    return SimpleNamespace(bus=bus, services=services)


# --- helper outcomes ------------------------------------------------------

async def test_unpair_ok_when_bridge_confirms() -> None:
    services = _FakeServices(has=True, confirm=True)
    outcome = await async_unpair_bridge_slot(
        _hass(services), "atom_s3r", "shaver", timeout=0.1
    )
    assert outcome == UNPAIR_OK
    assert services.calls == 1


async def test_unpair_confirm_matches_bridge_id_case_insensitively() -> None:
    services = _FakeServices(has=True, confirm=True)
    services.confirm_bridge_id = "SHAVER"  # bridge echoes original case
    outcome = await async_unpair_bridge_slot(
        _hass(services), "atom_s3r", "shaver", timeout=0.1
    )
    assert outcome == UNPAIR_OK


async def test_unpair_unconfirmed_when_no_event() -> None:
    services = _FakeServices(has=True, confirm=False)
    outcome = await async_unpair_bridge_slot(
        _hass(services), "atom_s3r", "shaver", timeout=0.05
    )
    assert outcome == UNPAIR_UNCONFIRMED


async def test_unpair_unavailable_when_service_missing() -> None:
    services = _FakeServices(has=False, confirm=False)
    outcome = await async_unpair_bridge_slot(
        _hass(services), "atom_s3r", "shaver", timeout=0.05
    )
    assert outcome == UNPAIR_UNAVAILABLE
    assert services.calls == 0


async def test_unpair_failed_when_call_raises() -> None:
    services = _FakeServices(has=True, confirm=False, raises=True)
    outcome = await async_unpair_bridge_slot(
        _hass(services), "atom_s3r", "shaver", timeout=0.05
    )
    assert outcome == UNPAIR_FAILED


async def test_wrong_bridge_id_event_is_ignored() -> None:
    services = _FakeServices(has=True, confirm=True)
    services.confirm_bridge_id = "oneblade"  # other slot's confirmation
    outcome = await async_unpair_bridge_slot(
        _hass(services), "atom_s3r", "shaver", timeout=0.05
    )
    assert outcome == UNPAIR_UNCONFIRMED


# --- reset_bridge flow step -----------------------------------------------

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
        "identity_address": "f4:b3:b1:aa:bb:cc",
        "paired": "true",
        "identity_source": "nvs",
    }

    def _create_task(coro, *args, **kwargs):
        coro.close()  # never actually run the coroutine in unit tests
        return _FakeTask(done=False)

    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_create_task),
        services=SimpleNamespace(async_call=AsyncMock()),
    )
    return flow


async def test_reset_bridge_confirm_form_first() -> None:
    flow = _flow()
    result = await flow.async_step_reset_bridge()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reset_bridge"
    placeholders = result["description_placeholders"]
    assert placeholders["identity_address"] == "F4:B3:B1:AA:BB:CC"
    assert placeholders["error"] == ""
    assert "atom_s3r / shaver" in placeholders["target"]


async def test_reset_bridge_submit_starts_progress() -> None:
    flow = _flow()
    result = await flow.async_step_reset_bridge(user_input={})
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "unpairing"
    assert flow._unpair_task is not None


async def test_reset_bridge_running_task_keeps_progress() -> None:
    flow = _flow()
    flow._unpair_task = _FakeTask(done=False)
    result = await flow.async_step_reset_bridge()
    assert result["type"] == FlowResultType.SHOW_PROGRESS


async def test_reset_bridge_done_task_routes_to_finish() -> None:
    flow = _flow()
    flow._unpair_task = _FakeTask(done=True, result=UNPAIR_OK)
    result = await flow.async_step_reset_bridge()
    assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
    assert result["step_id"] == "reset_finish"
    assert flow._unpair_outcome == UNPAIR_OK
    assert flow._unpair_task is None


async def test_reset_finish_ok_refetches_and_marks_unpaired() -> None:
    flow = _flow()
    flow._unpair_outcome = UNPAIR_OK
    flow._esp_bridge_health_check = AsyncMock(return_value={"type": "next"})

    result = await flow.async_step_reset_finish()

    assert result == {"type": "next"}
    assert flow.fetched_bridge_info is None  # forces a fresh ble_get_info
    assert flow._just_unpaired is True


async def test_reset_finish_unconfirmed_shows_error_alert() -> None:
    flow = _flow()
    flow._unpair_outcome = UNPAIR_UNCONFIRMED

    result = await flow.async_step_reset_finish()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reset_bridge"
    error = result["description_placeholders"]["error"]
    assert 'ha-alert alert-type="error"' in error
    assert "confirm" in error
    # Bond may still be present — the info must stay for the next render.
    assert flow.fetched_bridge_info is not None
    assert flow._just_unpaired is False


async def test_reset_finish_unavailable_shows_offline_error() -> None:
    flow = _flow()
    flow._unpair_outcome = UNPAIR_UNAVAILABLE

    result = await flow.async_step_reset_finish()

    assert result["type"] == FlowResultType.FORM
    error = result["description_placeholders"]["error"]
    assert "online" in error


async def test_request_pair_shows_unpaired_notice_once() -> None:
    flow = _flow()
    flow._just_unpaired = True

    result = await flow.async_step_request_pair()
    notice = result["description_placeholders"]["notice"]
    assert 'ha-alert alert-type="success"' in notice
    assert flow._just_unpaired is False

    # One-shot: the next render is clean.
    result = await flow.async_step_request_pair()
    assert result["description_placeholders"]["notice"] == ""
