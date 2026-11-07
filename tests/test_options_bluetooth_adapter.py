"""Bluetooth adapter option for direct-BLE shaver entries.

Bonds are per adapter. Moving a shaver to another local adapter without
a bond there would end every connect in an auth failure, so the options
flow pairs on the new adapter before saving — ported from the Sonicare
integration, where exactly that was seen live (2026-10-29). Unlike the
toothbrush, a shaver is always bonded and Bluetooth proxies are never
offered (they cannot complete its LE Secure Connections pairing).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.philips_shaver import config_flow as cf
from custom_components.philips_shaver import dbus_pairing as dp
from custom_components.philips_shaver.const import (
    BLUETOOTH_ADAPTER_AUTO,
    CONF_BLUETOOTH_ADAPTER,
    CONF_NOTIFY_THROTTLE,
    CONF_PIPELINED_READS,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_BLEAK,
    TRANSPORT_ESP_BRIDGE,
)

ADDRESS = "F4:B3:B1:AA:BB:CC"
HCI0 = "00:0A:CD:46:B2:2D"
HCI1 = "58:D8:12:3E:CA:B2"

TWO_ADAPTERS = [
    {"name": "hci1 (58:D8:12:3E:CA:B2)", "source": HCI1, "rssi": -64},
    {"name": "hci0 (00:0A:CD:46:B2:2D)", "source": HCI0, "rssi": -74},
]


def _flow(monkeypatch, *, options=None, transport=TRANSPORT_BLEAK):
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Bathroom",
        data={"address": ADDRESS, CONF_TRANSPORT_TYPE: transport},
        options={CONF_BLUETOOTH_ADAPTER: HCI1} if options is None else options,
    )
    monkeypatch.setattr(
        cf.PhilipsShaverOptionsFlow, "config_entry", property(lambda self: entry)
    )
    flow = cf.PhilipsShaverOptionsFlow()
    flow.flow_id = "options-flow"
    flow.handler = "philips_shaver"
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_unload=AsyncMock(return_value=True),
            async_schedule_reload=MagicMock(),
            async_update_entry=MagicMock(),
        ),
        async_create_task=lambda coro: asyncio.get_running_loop().create_task(coro),
        data={},
    )
    return flow


def _live_via(flow, adapter: str) -> None:
    """The running entry is connected through ``adapter``."""
    transport = SimpleNamespace(
        is_connected=True, connection_path=f"hciX ({adapter})"
    )
    flow.hass.data[cf.DOMAIN] = {
        "entry-1": {"coordinator": SimpleNamespace(transport=transport)}
    }


@pytest.fixture
def adapters(monkeypatch):
    """hci0 and hci1 local; the shaver is bonded on hci1."""
    monkeypatch.setattr(cf, "describe_local_adapters", lambda hass, a: TWO_ADAPTERS)
    monkeypatch.setattr(dp, "is_dbus_available", lambda: True)
    paired = AsyncMock(return_value=[HCI1])
    monkeypatch.setattr(dp, "async_paired_adapters", paired)
    pair = AsyncMock()
    monkeypatch.setattr(dp, "async_pair_and_trust", pair)
    remove = AsyncMock(return_value=True)
    monkeypatch.setattr(dp, "async_remove_device", remove)

    async def _blocks(hass, category="config"):
        keys = [
            "pair_paired", "pair_already",
            "pair_unknown", "drop_done", "drop_failed",
            "drop_none", "drop_unknown", "drop_unverified", "reload",
        ]
        blocks = {f"error.summary_{k}": f"{k}:{{adapter}}" for k in keys}
        blocks["error.headline_adapter"] = "fixed:{adapter}"
        blocks["error.headline_adapter_same"] = "same:{adapter}"
        blocks["error.pair_adapter_failed"] = "{error}"
        return blocks

    monkeypatch.setattr(cf, "_async_text_blocks", _blocks)

    real_sleep = asyncio.sleep

    async def _fast_sleep(delay, *args):
        await real_sleep(0)

    monkeypatch.setattr(cf.asyncio, "sleep", _fast_sleep)

    # The new adapter hears the shaver right away, unless a test says not.
    watch = SimpleNamespace(heard=True, events=[], stopped=0)

    def _watch(address, source):
        event = asyncio.Event()
        if watch.heard:
            event.set()
        watch.events.append(event)

        def _stop():
            watch.stopped += 1

        return event, _stop

    monkeypatch.setattr(cf, "watch_advertisements", _watch)
    rssi = SimpleNamespace(value=None)
    monkeypatch.setattr(cf, "scanner_rssi", lambda hass, a, s: rssi.value)
    disconnect = AsyncMock(return_value=[])
    monkeypatch.setattr(dp, "async_disconnect_device", disconnect)
    # The pause timer: recorded, fired by the test when needed.
    timer = SimpleNamespace(armed=[], cancelled=0)

    def _call_later(hass, delay, action):
        timer.armed.append((delay, action))

        def _cancel():
            timer.cancelled += 1

        return _cancel

    monkeypatch.setattr(cf, "async_call_later", _call_later)
    return SimpleNamespace(
        paired=paired, pair=pair, remove=remove, watch=watch, rssi=rssi,
        disconnect=disconnect, timer=timer,
    )


async def _run_pairing(flow):
    result = await flow.async_step_pair_adapter({})
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    await flow._pair_task
    result = await flow.async_step_pair_adapter()
    assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
    return await flow.async_step_pair_adapter_finish()


async def test_switch_to_unbonded_local_adapter_asks_to_pair(monkeypatch, adapters):
    flow = _flow(monkeypatch)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pair_adapter"
    assert result["description_placeholders"]["adapter"] == "hci0"
    assert result["description_placeholders"]["paired_on"] == "hci1"
    assert result["description_placeholders"]["alert"] == ""
    # The shaver holds one pairing only: the dialog links the reset guide.
    assert result["description_placeholders"]["unpairing_url"].endswith(
        "UNPAIRING.md#step-2-unpair-on-the-device-itself"
    )
    # Paused before the user resets the shaver: left running, the entry
    # would grab the freshly reset shaver over the old adapter.
    flow.hass.config_entries.async_unload.assert_awaited_once_with("entry-1")
    adapters.disconnect.assert_awaited_once_with(ADDRESS)
    assert [d for d, _ in adapters.timer.armed] == [cf.PAIR_PAUSE_TIMEOUT]


def _checklist(result) -> list[str]:
    """Row keys of the closing checklist (test text blocks are 'key:…')."""
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "adapter_changed"
    return [
        line.split(". ", 1)[1].split(":")[0]
        for line in result["description_placeholders"]["summary"].split("\n")
    ]


async def test_automatic_entry_fixed_to_its_bonded_adapter(monkeypatch, adapters):
    # An older entry on automatic, bonded on hci1: choosing hci1 just
    # saves it as the fixed adapter — no pairing, nothing removed.
    flow = _flow(monkeypatch, options={})
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI1})
    assert _checklist(result) == ["pair_already", "drop_none", "reload"]
    adapters.pair.assert_not_called()
    adapters.remove.assert_not_called()
    saved = flow.hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert saved[CONF_BLUETOOTH_ADAPTER] == HCI1


async def test_unchanged_adapter_saves_normally(monkeypatch, adapters):
    flow = _flow(monkeypatch)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI1})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    adapters.pair.assert_not_called()


async def test_shaver_without_any_bond_gets_pair_step(monkeypatch, adapters):
    # Shavers are always bonded: no bond anywhere still means pairing.
    adapters.paired.return_value = []
    flow = _flow(monkeypatch)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    assert result["step_id"] == "pair_adapter"
    assert result["description_placeholders"]["paired_on"] == "—"


async def test_offline_adapter_is_not_paired(monkeypatch, adapters):
    # A saved adapter that is unplugged right now: nothing can be checked.
    flow = _flow(monkeypatch, options={})
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: "11:22:33:44:55:66"})
    assert _checklist(result) == ["pair_unknown", "drop_unknown", "reload"]
    adapters.pair.assert_not_called()


async def test_successful_pairing_saves_and_reloads(monkeypatch, adapters):
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    result = await _run_pairing(flow)

    assert _checklist(result) == ["pair_paired", "drop_done", "reload"]
    assert "hci1" in result["description_placeholders"]["summary"]
    headline = result["description_placeholders"]["headline"]
    assert 'alert-type="success"' in headline and "hci0" in headline
    saved = flow.hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert saved[CONF_BLUETOOTH_ADAPTER] == HCI0
    flow.hass.config_entries.async_unload.assert_awaited_once_with("entry-1")
    adapters.pair.assert_awaited_once_with(ADDRESS, HCI0)
    # Only after the new bond exists: the old adapter's bond goes.
    adapters.remove.assert_awaited_once_with(ADDRESS, HCI1)
    # Exactly one reload brings the paused entry back — also after the
    # dialog closes.
    flow.async_remove()
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with("entry-1")


async def test_unchanged_bonded_adapter_just_saves(monkeypatch, adapters):
    flow = _flow(monkeypatch, options={CONF_BLUETOOTH_ADAPTER: HCI1})
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI1})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    flow.hass.config_entries.async_unload.assert_not_called()


async def test_unchanged_adapter_without_bond_offers_pairing(monkeypatch, adapters):
    # Fixed on hci0 without a bond there (an earlier switch saved it while
    # it could not be checked): choosing it again leads to the pairing.
    flow = _flow(monkeypatch, options={CONF_BLUETOOTH_ADAPTER: HCI0})
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pair_adapter"
    flow.hass.config_entries.async_unload.assert_awaited_once_with("entry-1")


async def test_failed_pairing_shows_reason_and_close_restores(monkeypatch, adapters):
    adapters.pair.side_effect = dp.PairingError("Pairing timed out after 30s")
    monkeypatch.setattr(
        cf, "_async_text_blocks",
        AsyncMock(return_value={
            "error.pair_adapter_failed": "Pairing with {adapter} failed: {error}",
        }),
    )
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    result = await _run_pairing(flow)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pair_adapter"
    alert = result["description_placeholders"]["alert"]
    assert "ha-alert" in alert and "hci0" in alert and "timed out" in alert
    # The entry stays paused while the form waits for the next reset —
    # paused once, not unloaded again by the retry form.
    flow.hass.config_entries.async_schedule_reload.assert_not_called()
    flow.hass.config_entries.async_unload.assert_awaited_once_with("entry-1")

    # User gives up and closes the dialog: the entry comes back once.
    flow.async_remove()
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with("entry-1")
    flow.async_remove()
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with("entry-1")


async def test_dialog_left_open_resumes_the_entry(monkeypatch, adapters):
    # A closed browser tab never ends the flow: the timer brings the entry
    # back, and a later Submit pauses it again before pairing.
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    _, expire = adapters.timer.armed[-1]

    expire(None)
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with("entry-1")

    result = await _run_pairing(flow)
    assert _checklist(result) == ["pair_paired", "drop_done", "reload"]
    assert flow.hass.config_entries.async_unload.await_count == 2
    adapters.pair.assert_awaited_once_with(ADDRESS, HCI0)


async def test_submit_stops_the_pause_timer(monkeypatch, adapters):
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    await _run_pairing(flow)
    assert adapters.timer.cancelled >= 1
    # A late timer callback while nothing is paused does nothing.
    _, expire = adapters.timer.armed[-1]
    reloads = flow.hass.config_entries.async_schedule_reload.call_count
    expire(None)
    assert flow.hass.config_entries.async_schedule_reload.call_count == reloads


async def test_auto_to_fixed_drops_bonds_on_other_adapters(monkeypatch, adapters):
    # Bonded on both; fixing hci0 needs no pairing but removes hci1's bond,
    # with the entry unloaded first (it may be connected through hci1).
    adapters.paired.return_value = [HCI0, HCI1]
    flow = _flow(monkeypatch, options={})
    _live_via(flow, HCI0)  # proves hci0's bond is the valid one
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    assert _checklist(result) == ["pair_already", "drop_done", "reload"]
    adapters.pair.assert_not_called()
    flow.hass.config_entries.async_unload.assert_awaited_once_with("entry-1")
    adapters.remove.assert_awaited_once_with(ADDRESS, HCI1)
    flow.async_remove()
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with("entry-1")


async def test_failed_removal_is_reported(monkeypatch, adapters):
    adapters.paired.return_value = [HCI0, HCI1]
    adapters.remove.return_value = False
    flow = _flow(monkeypatch, options={})
    _live_via(flow, HCI0)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    assert _checklist(result) == ["pair_already", "drop_failed", "reload"]
    assert 'alert-type="warning"' in result["description_placeholders"]["headline"]


@pytest.mark.parametrize(
    ("current", "chosen"),
    [
        (HCI1, HCI1),                    # no change
    ],
)
async def test_bonds_kept(monkeypatch, adapters, current, chosen):
    adapters.paired.return_value = [HCI0, HCI1]
    flow = _flow(monkeypatch, options={CONF_BLUETOOTH_ADAPTER: current})
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: chosen})

    assert result["type"] in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT)
    adapters.remove.assert_not_called()
    flow.hass.config_entries.async_unload.assert_not_called()


async def test_failed_pairing_keeps_old_bond(monkeypatch, adapters):
    adapters.pair.side_effect = dp.PairingError("timed out")
    monkeypatch.setattr(
        cf, "_async_text_blocks",
        AsyncMock(return_value={"error.pair_adapter_failed": "{error}"}),
    )
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    await _run_pairing(flow)
    adapters.remove.assert_not_called()


async def test_one_row_per_removed_adapter(monkeypatch, adapters):
    # Three local adapters, the shaver bonded on all: fixing hci0 lists
    # each removed bond on its own line, led by the adapter.
    hci2 = "11:22:33:44:55:66"
    monkeypatch.setattr(cf, "describe_local_adapters", lambda hass, a: [
        {"name": "hci0 (00:0A:CD:46:B2:2D)", "source": HCI0, "rssi": -74},
        {"name": "hci1 (58:D8:12:3E:CA:B2)", "source": HCI1, "rssi": -64},
        {"name": "hci2 (11:22:33:44:55:66)", "source": hci2, "rssi": None},
    ])
    adapters.paired.return_value = [HCI0, HCI1, hci2]
    flow = _flow(monkeypatch, options={})
    _live_via(flow, HCI0)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    lines = result["description_placeholders"]["summary"].split("\n")
    assert lines == [
        "1. pair_already:hci0",
        "2. drop_done:hci1",
        "3. drop_done:hci2",
        "4. reload:{adapter}",  # row without values; test text keeps the marker
    ]


async def test_pairs_only_after_fresh_advertisement(monkeypatch, adapters):
    # Silent shaver after the disconnect: no pairing until the new adapter
    # receives an advertisement (Sonicare live 2026-10-30, Pair() timed out).
    adapters.watch.heard = False
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    await flow.async_step_pair_adapter({})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    adapters.pair.assert_not_called()

    adapters.watch.events[0].set()  # shaver switched on
    await flow._pair_task

    adapters.pair.assert_awaited_once_with(ADDRESS, HCI0)
    assert adapters.watch.stopped == 1


async def test_no_advertisement_asks_to_switch_on(monkeypatch, adapters):
    adapters.watch.heard = False
    monkeypatch.setattr(cf, "PAIR_ADVERTISEMENT_WAIT", 0)
    monkeypatch.setattr(
        cf, "_async_text_blocks",
        AsyncMock(return_value={
            "error.pair_adapter_no_advertisement": "{adapter} silent for {seconds}s",
        }),
    )
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    result = await _run_pairing(flow)

    assert result["step_id"] == "pair_adapter"
    assert "hci0</b> silent for 0s" in result["description_placeholders"]["alert"]
    adapters.pair.assert_not_called()
    assert adapters.watch.stopped == 1


async def test_retry_keeps_bond_from_late_first_attempt(monkeypatch, adapters):
    # 1st Pair() timed out on our side, BlueZ finished it later; the
    # retry found the bond and removed it as "stale" (Sonicare live 2026-10-30).
    adapters.pair.side_effect = dp.PairingError("Pairing timed out after 30s")
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    result = await _run_pairing(flow)
    assert result["step_id"] == "pair_adapter"

    adapters.paired.return_value = [HCI1, HCI0]
    result = await _run_pairing(flow)

    assert result["reason"] == "adapter_changed"
    adapters.pair.assert_awaited_once()  # no second Pair() over the bond
    adapters.remove.assert_awaited_once_with(ADDRESS, HCI1)


async def test_first_attempt_never_trusts_an_existing_bond(monkeypatch, adapters):
    # Without an earlier attempt in this dialog a bond on the new adapter
    # is not ours — the normal pairing (with its stale-bond check) runs.
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    adapters.paired.return_value = [HCI1, HCI0]

    await _run_pairing(flow)

    adapters.pair.assert_awaited_once_with(ADDRESS, HCI0)


@pytest.mark.parametrize(("rssi", "warned"), [(-96, True), (-74, False), (None, False)])
async def test_weak_signal_warning(monkeypatch, adapters, rssi, warned):
    adapters.rssi.value = rssi
    monkeypatch.setattr(
        cf, "_async_text_blocks",
        AsyncMock(return_value={"error.pair_adapter_weak": "{adapter} weak {rssi}"}),
    )
    flow = _flow(monkeypatch)

    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    assert result["step_id"] == "pair_adapter"
    alert = result["description_placeholders"]["alert"]
    assert ("weak -96" in alert) is warned
    assert ('alert-type="warning"' in alert) is warned


@pytest.mark.parametrize("late_bond", [True, False])
async def test_timeout_cancels_and_takes_late_bond(late_bond):
    device = SimpleNamespace(call_cancel_pairing=AsyncMock())
    props = SimpleNamespace(
        call_get=AsyncMock(return_value=SimpleNamespace(value=late_bond))
    )

    assert await dp._async_cancel_and_check_paired(device, props, ADDRESS) is late_bond
    device.call_cancel_pairing.assert_awaited_once()


async def test_pairs_without_waiting_when_core_cannot_tell(monkeypatch, adapters):
    # No per-address advertisement callback (older habluetooth): pair as
    # before instead of waiting 45 s for a signal that can never come.
    def _unknown(address, source):
        raise LookupError("no async_register_advertisement_callback")

    monkeypatch.setattr(cf, "watch_advertisements", _unknown)
    flow = _flow(monkeypatch)
    await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    result = await _run_pairing(flow)

    assert result["reason"] == "adapter_changed"
    adapters.pair.assert_awaited_once_with(ADDRESS, HCI0)


# ---------------------------------------------------------------------------
# Routing of the options dialog
# ---------------------------------------------------------------------------


async def test_two_adapters_open_the_adapter_step(monkeypatch, adapters):
    flow = _flow(monkeypatch, options={})
    result = await flow.async_step_init()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "adapter"
    schema = result["data_schema"].schema
    (key,) = schema
    assert str(key) == CONF_BLUETOOTH_ADAPTER
    values = [o["value"] for o in schema[key].config["options"]]
    assert values == [HCI1, HCI0]
    # An older entry on automatic: the bonded adapter is preselected, so
    # one click fixes it.
    assert key.default() == HCI1


async def test_automatic_entry_preselects_the_bonded_adapter(monkeypatch, adapters):
    # Bond on hci0 although hci1 is listed first (stronger).
    adapters.paired.return_value = [HCI0]
    flow = _flow(monkeypatch, options={})
    result = await flow.async_step_init()
    (key,) = result["data_schema"].schema
    assert key.default() == HCI0


async def test_single_adapter_on_automatic_has_nothing_to_change(monkeypatch, adapters):
    monkeypatch.setattr(cf, "describe_local_adapters", lambda hass, a: TWO_ADAPTERS[:1])
    flow = _flow(monkeypatch, options={})
    result = await flow.async_step_init()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {}


async def test_fixed_adapter_keeps_the_way_back(monkeypatch, adapters):
    # Fixed to an adapter that has since been unplugged: still offered
    # (and preselected), next to the one that is there.
    monkeypatch.setattr(cf, "describe_local_adapters", lambda hass, a: TWO_ADAPTERS[:1])
    gone = "11:22:33:44:55:66"
    flow = _flow(monkeypatch, options={CONF_BLUETOOTH_ADAPTER: gone})
    result = await flow.async_step_init()
    assert result["step_id"] == "adapter"
    (key,) = result["data_schema"].schema
    values = [o["value"] for o in result["data_schema"].schema[key].config["options"]]
    assert values == [HCI1, gone]
    assert key.default() == gone


async def test_fixed_to_the_only_adapter_has_nothing_to_change(monkeypatch, adapters):
    monkeypatch.setattr(cf, "describe_local_adapters", lambda hass, a: TWO_ADAPTERS[:1])
    flow = _flow(monkeypatch, options={CONF_BLUETOOTH_ADAPTER: HCI1})
    result = await flow.async_step_init()
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_esp_bridge_keeps_its_settings_form(monkeypatch, adapters):
    flow = _flow(monkeypatch, options={}, transport=TRANSPORT_ESP_BRIDGE)
    result = await flow.async_step_init()
    assert result["step_id"] == "init"
    result = await flow.async_step_init(
        {CONF_NOTIFY_THROTTLE: 300, CONF_PIPELINED_READS: False}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_NOTIFY_THROTTLE: 300, CONF_PIPELINED_READS: False}



async def test_unverifiable_bonds_are_kept(monkeypatch, adapters):
    # Bonds on both adapters, not connected: which one is valid is unknown,
    # so nothing is removed and the box turns yellow.
    adapters.paired.return_value = [HCI0, HCI1]
    flow = _flow(monkeypatch, options={})
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    assert _checklist(result) == ["pair_already", "drop_unverified", "reload"]
    adapters.remove.assert_not_called()
    assert 'alert-type="warning"' in result["description_placeholders"]["headline"]


async def test_live_through_other_adapter_means_target_bond_is_stale(monkeypatch, adapters):
    # Connected through hci1 right now: hci1 holds the valid bond, so the
    # one BlueZ still has on hci0 is stale — pair hci0 again.
    adapters.paired.return_value = [HCI0, HCI1]
    flow = _flow(monkeypatch, options={})
    _live_via(flow, HCI1)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pair_adapter"
    assert result["description_placeholders"]["paired_on"] == "hci1"



async def test_retry_does_not_trust_the_stale_target_bond(monkeypatch, adapters):
    # Valid bond on hci1 (live), stale one on hci0. The first attempt fails
    # before Pair(); on retry the old hci0 bond must not pass for the
    # result of our pairing — or the valid hci1 bond would be removed.
    bonds = [HCI0, HCI1]  # BlueZ state, kept in step with removals
    adapters.paired.side_effect = lambda address: list(bonds)

    async def _remove(address, adapter):
        bonds.remove(adapter)
        return True

    adapters.remove.side_effect = _remove
    flow = _flow(monkeypatch, options={})
    _live_via(flow, HCI1)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})
    assert result["step_id"] == "pair_adapter"

    adapters.watch.heard = False  # first attempt: shaver silent
    monkeypatch.setattr(cf, "PAIR_ADVERTISEMENT_WAIT", 0)
    result = await _run_pairing(flow)
    assert result["step_id"] == "pair_adapter"
    adapters.pair.assert_not_called()

    adapters.watch.heard = True
    await _run_pairing(flow)
    assert adapters.pair.await_count == 1
    # The stale target bond was removed by us before pairing, the valid
    # hci1 bond only after the new one exists.
    assert adapters.remove.await_args_list[0].args == (ADDRESS, HCI0)


async def test_same_adapter_again_removes_proven_stale_bonds(monkeypatch, adapters):
    # Fixed on hci0 with leftover bonds elsewhere (kept earlier as
    # unverified); now connected through hci0: choosing it again tidies up.
    adapters.paired.return_value = [HCI0, HCI1]
    flow = _flow(monkeypatch, options={CONF_BLUETOOTH_ADAPTER: HCI0})
    _live_via(flow, HCI0)
    result = await flow.async_step_adapter({CONF_BLUETOOTH_ADAPTER: HCI0})

    assert _checklist(result) == ["pair_already", "drop_done", "reload"]
    adapters.remove.assert_awaited_once_with(ADDRESS, HCI1)
    # Not "changed" — the adapter stays the same.
    assert "same:hci0" in result["description_placeholders"]["headline"]
