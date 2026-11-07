"""Fixed Bluetooth adapter for direct-BLE entries.

With the option set, every connect goes through exactly that local
adapter: a stronger adapter next to it must not take over (its bond is a
different one), and when the fixed adapter does not receive the shaver
the connect fails with a message that names the adapters that do.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.philips_shaver import config_flow as cf
from custom_components.philips_shaver import coordinator as co
from custom_components.philips_shaver import sensor as se
from custom_components.philips_shaver import transport as tr
from custom_components.philips_shaver.const import (
    BLUETOOTH_ADAPTER_AUTO,
    CONF_BLUETOOTH_ADAPTER,
    CONF_TRANSPORT_TYPE,
    TRANSPORT_BLEAK,
)
from custom_components.philips_shaver.exceptions import (
    AdapterNotReceivingException,
)

ADDRESS = "F4:B3:B1:AA:BB:CC"
HCI0 = "00:0A:CD:46:B2:2D"
HCI1 = "58:D8:12:3E:CA:B2"
# Captured at import, before conftest's autouse stub replaces it per test.
_REAL_PAIRED_ADAPTER = tr.BleakTransport._async_paired_adapter


class LocalScanner:
    def __init__(self, name: str, source: str) -> None:
        self.name = name
        self.source = source
        self.connectable = True


def _item(scanner, rssi):
    return SimpleNamespace(
        scanner=scanner,
        advertisement=SimpleNamespace(rssi=rssi),
        ble_device=SimpleNamespace(address=ADDRESS),
    )


@pytest.fixture
def scanners(monkeypatch):
    monkeypatch.setattr(tr, "HaScanner", LocalScanner)
    hci0 = LocalScanner(f"hci0 ({HCI0})", HCI0)
    hci1 = LocalScanner(f"hci1 ({HCI1})", HCI1)
    proxy = SimpleNamespace(name="atom-s3r", source="98:88:E0:0E:DA:D2", connectable=True)
    return SimpleNamespace(hci0=hci0, hci1=hci1, proxy=proxy)


def _client(cls):
    client = object.__new__(cls)
    client._HaBleakClientWrapper__address = ADDRESS  # noqa: SLF001
    return client


# ---------------------------------------------------------------------------
# Pinned client
# ---------------------------------------------------------------------------


def test_fixed_client_ignores_stronger_local_adapter(monkeypatch, scanners) -> None:
    cls = tr.local_bluez_client_class(HCI1.lower())
    chosen = []
    monkeypatch.setattr(
        cls, "_async_get_backend_for_ble_device",
        lambda self, manager, scanner, device: chosen.append(scanner) or object(),
    )
    manager = SimpleNamespace(
        async_scanner_devices_by_address=MagicMock(return_value=[
            _item(scanners.hci0, -50), _item(scanners.hci1, -80),
        ])
    )

    _client(cls)._async_get_best_available_backend_and_device(manager)

    assert chosen == [scanners.hci1]


def test_fixed_client_names_receivers_when_fixed_is_deaf(monkeypatch, scanners) -> None:
    cls = tr.local_bluez_client_class(HCI1)
    monkeypatch.setattr(
        cls, "_async_get_backend_for_ble_device",
        lambda self, manager, scanner, device: object(),
    )
    manager = SimpleNamespace(
        async_scanner_devices_by_address=MagicMock(return_value=[
            _item(scanners.hci0, -60),
            # BlueZ RSSI-invalidation leftover: hci1 does not receive it.
            _item(scanners.hci1, -127),
            _item(scanners.proxy, -40),
        ]),
        async_scanner_by_source=lambda source: scanners.hci1,
    )

    with pytest.raises(BleakError) as err:
        _client(cls)._async_get_best_available_backend_and_device(manager)

    message = str(err.value)
    assert f"hci1 ({HCI1}) does not receive {ADDRESS}" in message
    assert f"hci0 ({HCI0}) (-60 dBm)" in message
    assert "atom-s3r (-40 dBm)" in message
    assert "-127" not in message


def test_fixed_client_never_uses_a_proxy_with_the_same_source(monkeypatch, scanners) -> None:
    # Only local adapters can be fixed; a remote scanner never matches.
    cls = tr.local_bluez_client_class(scanners.proxy.source)
    monkeypatch.setattr(
        cls, "_async_get_backend_for_ble_device",
        lambda self, manager, scanner, device: object(),
    )
    manager = SimpleNamespace(
        async_scanner_devices_by_address=MagicMock(return_value=[
            _item(scanners.proxy, -40),
        ]),
    )
    with pytest.raises(BleakError, match="does not receive"):
        _client(cls)._async_get_best_available_backend_and_device(manager)


def test_client_class_per_source_is_cached(scanners) -> None:
    assert tr.local_bluez_client_class() is tr._LocalBluezHaBleakClient
    assert tr.local_bluez_client_class(BLUETOOTH_ADAPTER_AUTO) is tr._LocalBluezHaBleakClient
    fixed = tr.local_bluez_client_class(HCI0)
    assert fixed is tr.local_bluez_client_class(HCI0.lower())
    assert issubclass(fixed, tr._LocalBluezHaBleakClient)
    assert fixed._fixed_source == HCI0


def test_scanner_device_lookup_honours_fixed_adapter(monkeypatch, scanners) -> None:
    strong, weak = _item(scanners.hci0, -50), _item(scanners.hci1, -80)
    monkeypatch.setattr(
        tr, "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: [strong, weak],
    )
    hass = SimpleNamespace()
    assert tr.local_bluez_scanner_device_from_address(hass, ADDRESS) is strong
    assert tr.local_bluez_scanner_device_from_address(hass, ADDRESS, HCI1) is weak
    assert (
        tr.local_bluez_scanner_device_from_address(hass, ADDRESS, "11:22:33:44:55:66")
        is None
    )


async def test_transport_connect_fails_fast_on_deaf_fixed_adapter(monkeypatch, scanners) -> None:
    monkeypatch.setattr(
        tr, "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: [_item(scanners.hci0, -60)],
    )
    monkeypatch.setattr(tr, "_scanner_name_by_source", lambda hass, source: "hci1")
    establish = AsyncMock()
    monkeypatch.setattr(tr, "bleak_establish", establish)
    transport = tr.BleakTransport(
        SimpleNamespace(), ADDRESS, bluetooth_adapter=lambda: HCI1
    )

    with pytest.raises(tr.TransportError, match="fixed Bluetooth adapter hci1") as err:
        await transport.connect()

    assert f"hci0 ({HCI0}) (-60 dBm)" in str(err.value)
    establish.assert_not_called()


async def test_transport_connect_uses_the_pinned_class(monkeypatch, scanners) -> None:
    item = _item(scanners.hci1, -70)
    monkeypatch.setattr(
        tr, "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: [_item(scanners.hci0, -50), item],
    )
    client = SimpleNamespace(is_connected=True, _connected_scanner=scanners.hci1)
    establish = AsyncMock(return_value=client)
    monkeypatch.setattr(tr, "bleak_establish", establish)
    monkeypatch.setattr(tr, "is_local_bluez_connection", lambda client: True)
    monkeypatch.setattr(tr, "describe_connection_path", lambda *args: "hci1")
    # Read on every connect: a changed option needs no new transport.
    option = {"value": HCI1}
    transport = tr.BleakTransport(
        SimpleNamespace(), ADDRESS, bluetooth_adapter=lambda: option["value"]
    )

    await transport.connect()

    assert establish.await_args.args[0] is tr.local_bluez_client_class(HCI1)
    assert establish.await_args.args[1] is item.ble_device


@pytest.fixture
def real_bond_lookup(monkeypatch):
    """Undo the autouse stub: the real _async_paired_adapter, fake BlueZ."""
    from custom_components.philips_shaver import dbus_pairing as dp

    monkeypatch.setattr(
        tr.BleakTransport, "_async_paired_adapter", _REAL_PAIRED_ADAPTER
    )
    monkeypatch.setattr(dp, "is_dbus_available", lambda: True)
    paired = AsyncMock(return_value=[HCI0])
    monkeypatch.setattr(dp, "async_paired_adapters", paired)
    return paired


def _connect_setup(monkeypatch, items):
    monkeypatch.setattr(
        tr, "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: items,
    )
    client = SimpleNamespace(is_connected=True, _connected_scanner=None)
    establish = AsyncMock(return_value=client)
    monkeypatch.setattr(tr, "bleak_establish", establish)
    monkeypatch.setattr(tr, "is_local_bluez_connection", lambda client: True)
    monkeypatch.setattr(tr, "describe_connection_path", lambda *args: "hciX")
    return establish


async def test_automatic_uses_the_bonded_adapter_not_the_stronger(
    real_bond_lookup, monkeypatch
) -> None:
    # 07.11. live: bond on hci0 only, hci1 stronger — Automatic picked hci1
    # and the shaver dropped the unbonded link every two seconds.
    monkeypatch.setattr(tr, "HaScanner", LocalScanner)
    hci0 = LocalScanner(f"hci0 ({HCI0})", HCI0)
    hci1 = LocalScanner(f"hci1 ({HCI1})", HCI1)
    weak = _item(hci0, -78)
    establish = _connect_setup(monkeypatch, [_item(hci1, -64), weak])
    transport = tr.BleakTransport(
        SimpleNamespace(), ADDRESS, bluetooth_adapter=lambda: BLUETOOTH_ADAPTER_AUTO
    )

    await transport.connect()

    assert establish.await_args.args[0] is tr.local_bluez_client_class(HCI0)
    assert establish.await_args.args[1] is weak.ble_device


async def test_automatic_without_bond_takes_the_strongest(
    real_bond_lookup, monkeypatch
) -> None:
    real_bond_lookup.return_value = []
    monkeypatch.setattr(tr, "HaScanner", LocalScanner)
    hci0 = LocalScanner(f"hci0 ({HCI0})", HCI0)
    hci1 = LocalScanner(f"hci1 ({HCI1})", HCI1)
    strong = _item(hci1, -64)
    establish = _connect_setup(monkeypatch, [strong, _item(hci0, -78)])
    transport = tr.BleakTransport(
        SimpleNamespace(), ADDRESS, bluetooth_adapter=lambda: BLUETOOTH_ADAPTER_AUTO
    )

    await transport.connect()

    assert establish.await_args.args[0] is tr._LocalBluezHaBleakClient
    assert establish.await_args.args[1] is strong.ble_device


async def test_automatic_does_not_fall_back_to_an_unbonded_adapter(
    real_bond_lookup, monkeypatch
) -> None:
    # The bonded adapter does not receive the shaver right now: fail with
    # a reason rather than connecting through the unbonded one.
    monkeypatch.setattr(tr, "HaScanner", LocalScanner)
    monkeypatch.setattr(tr, "_scanner_name_by_source", lambda hass, source: "hci0")
    hci1 = LocalScanner(f"hci1 ({HCI1})", HCI1)
    establish = _connect_setup(monkeypatch, [_item(hci1, -64)])
    monkeypatch.setattr(tr, "describe_available_paths", lambda hass, a: [
        {"name": "hci1", "source": HCI1, "rssi": -64, "is_local": True},
    ])
    transport = tr.BleakTransport(
        SimpleNamespace(), ADDRESS, bluetooth_adapter=lambda: BLUETOOTH_ADAPTER_AUTO
    )

    with pytest.raises(tr.TransportError, match="paired Bluetooth adapter hci0"):
        await transport.connect()
    establish.assert_not_called()


def test_local_adapter_list_skips_proxies(monkeypatch, scanners) -> None:
    monkeypatch.setattr(
        tr, "async_current_scanners",
        lambda hass: [scanners.proxy, scanners.hci0, scanners.hci1],
    )
    monkeypatch.setattr(
        tr, "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: [
            _item(scanners.hci1, -66), _item(scanners.proxy, -40),
        ],
    )
    adapters = tr.describe_local_adapters(SimpleNamespace(), ADDRESS)
    # The one hearing the shaver first, with its RSSI; the rest by name.
    assert adapters == [
        {"name": f"hci1 ({HCI1})", "source": HCI1, "rssi": -66},
        {"name": f"hci0 ({HCI0})", "source": HCI0, "rssi": None},
    ]


# ---------------------------------------------------------------------------
# Wake only on the fixed adapter's packets
# ---------------------------------------------------------------------------


def _coordinator(options):
    coordinator = object.__new__(co.PhilipsShaverCoordinator)
    coordinator.entry = SimpleNamespace(options=options)
    coordinator.address = ADDRESS
    coordinator.transport = SimpleNamespace(is_connected=False)
    coordinator.data = None
    coordinator._wake_event = asyncio.Event()
    coordinator._adv_wake = False
    coordinator._unsub_advertisement = None
    return coordinator


def test_fixed_adapter_wake_listens_to_that_adapter_only(monkeypatch) -> None:
    registered = {}

    def _register(address, source, cb):
        registered.update(address=address, source=source, cb=cb)
        return "unsub"

    monkeypatch.setattr(co, "register_advertisements", _register)
    coordinator = _coordinator({CONF_BLUETOOTH_ADAPTER: HCI1})

    assert coordinator._start_fixed_adapter_callback() is True
    assert registered["source"] == HCI1
    assert coordinator._unsub_advertisement == "unsub"

    registered["cb"](SimpleNamespace(address=ADDRESS, rssi=-127))
    assert not coordinator._wake_event.is_set()
    registered["cb"](SimpleNamespace(address=ADDRESS, rssi=-70))
    assert coordinator._wake_event.is_set() and coordinator._adv_wake


@pytest.mark.parametrize("options", [{}, {CONF_BLUETOOTH_ADAPTER: BLUETOOTH_ADAPTER_AUTO}])
def test_automatic_keeps_ha_callback(monkeypatch, options) -> None:
    monkeypatch.setattr(
        co, "register_advertisements",
        MagicMock(side_effect=AssertionError("not for automatic")),
    )
    assert _coordinator(options)._start_fixed_adapter_callback() is False


def test_fixed_adapter_wake_falls_back_on_old_core(monkeypatch) -> None:
    def _missing(*args):
        raise LookupError("no per-packet callback")

    monkeypatch.setattr(co, "register_advertisements", _missing)
    assert _coordinator({CONF_BLUETOOTH_ADAPTER: HCI1})._start_fixed_adapter_callback() is False


# ---------------------------------------------------------------------------
# Setup flow
# ---------------------------------------------------------------------------


def _setup_flow(monkeypatch, adapters):
    flow = cf.PhilipsShaverConfigFlow()
    flow.flow_id = "test-flow"
    flow.handler = "philips_shaver"
    flow.hass = SimpleNamespace()
    monkeypatch.setattr(cf, "describe_local_adapters", lambda hass, a: adapters)
    return flow


TWO = [
    {"name": f"hci1 ({HCI1})", "source": HCI1, "rssi": -64},
    {"name": f"hci0 ({HCI0})", "source": HCI0, "rssi": None},
]


def test_setup_asks_for_adapter_only_with_a_choice(monkeypatch) -> None:
    assert _setup_flow(monkeypatch, TWO[:1])._bluetooth_adapter_field(ADDRESS) == {}
    field = _setup_flow(monkeypatch, TWO)._bluetooth_adapter_field(ADDRESS)
    (key,) = field
    assert str(key) == "adapter"
    (inner,) = field[key].schema.schema
    assert str(inner) == CONF_BLUETOOTH_ADAPTER
    labels = [o["label"] for o in field[key].schema.schema[inner].config["options"]]
    # No "Automatic": the shaver keeps one pairing, so only adapters.
    assert labels == [f"hci1 ({HCI1}), -64 dBm", f"hci0 ({HCI0})"]
    # Preselected: the strongest adapter receiving the shaver.
    assert inner.default() == HCI1


def test_pair_target_adapter(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    monkeypatch.setattr(cf, "describe_available_paths", lambda hass, a: [
        {"name": "atom-s3r", "source": "98:88:E0:0E:DA:D2", "rssi": -40, "is_local": False},
        {"name": "hci1", "source": HCI1, "rssi": -64, "is_local": True},
    ])
    # Automatic, before any probe: the adapter the automatic pin would pick.
    assert flow._pair_target_adapter(ADDRESS) == HCI1
    # After a probe: the adapter that carried it.
    flow._probe_adapter = HCI0
    assert flow._pair_target_adapter(ADDRESS) == HCI0
    # Fixed: always that one.
    flow._bluetooth_adapter = HCI1
    assert flow._pair_target_adapter(ADDRESS) == HCI1


async def test_probe_reports_deaf_fixed_adapter(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow._bluetooth_adapter = HCI0
    monkeypatch.setattr(
        cf, "async_last_service_info",
        lambda hass, address, connectable=True: SimpleNamespace(
            rssi=-60, time=cf.time.monotonic()
        ),
    )
    monkeypatch.setattr(cf, "local_bluez_device_from_address", lambda h, a, s=None: None)
    monkeypatch.setattr(cf, "describe_available_paths", lambda hass, a: [
        {"name": "hci1", "source": HCI1, "rssi": -64, "is_local": True},
    ])
    with pytest.raises(AdapterNotReceivingException):
        await flow._async_fetch_capabilities(ADDRESS)


async def test_fixed_adapter_lands_in_entry_options(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow.fetched_data = {"capabilities": 0, "services": [], "model_number": "XP9201"}
    flow.fetched_address = ADDRESS
    flow.fetched_transport_type = TRANSPORT_BLEAK
    flow._bluetooth_adapter = HCI0
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    await flow.async_step_show_capabilities({"device_name": "Bathroom"})

    kwargs = flow.async_create_entry.call_args.kwargs
    assert kwargs["options"] == {CONF_BLUETOOTH_ADAPTER: HCI0}


async def test_automatic_leaves_entry_options_empty(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow.fetched_data = {"capabilities": 0, "services": []}
    flow.fetched_address = ADDRESS
    flow.fetched_transport_type = TRANSPORT_BLEAK
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    await flow.async_step_show_capabilities({"device_name": "Bathroom"})

    assert flow.async_create_entry.call_args.kwargs["options"] == {}


# ---------------------------------------------------------------------------
# Diagnostic sensors
# ---------------------------------------------------------------------------


def _entry(options):
    return SimpleNamespace(
        entry_id="entry-1",
        data={"address": ADDRESS, CONF_TRANSPORT_TYPE: TRANSPORT_BLEAK},
        options=options,
    )


def _sensor(cls, options, connection_path=None):
    sensor = object.__new__(cls)
    sensor.hass = SimpleNamespace()
    sensor.coordinator = SimpleNamespace(
        transport=SimpleNamespace(connection_path=connection_path)
    )
    entry = _entry(options)
    sensor._source = entry.options.get(CONF_BLUETOOTH_ADAPTER, BLUETOOTH_ADAPTER_AUTO)
    sensor._fixed_source = sensor._source
    return sensor


def test_adapter_selection_sensor(monkeypatch) -> None:
    monkeypatch.setattr(se, "_scanner_name_by_source", lambda hass, s: "hci1 (x)")
    auto = _sensor(se.PhilipsAdapterSelectionSensor, {})
    assert auto.native_value == "automatic"
    assert auto.extra_state_attributes is None
    fixed = _sensor(se.PhilipsAdapterSelectionSensor, {CONF_BLUETOOTH_ADAPTER: HCI1})
    assert fixed.native_value == "fixed"
    assert fixed.extra_state_attributes == {"fixed_adapter": "hci1 (x)", "source": HCI1}


def test_adapter_sensor_names_fixed_adapter_while_asleep(monkeypatch) -> None:
    monkeypatch.setattr(se, "_scanner_name_by_source", lambda hass, s: None)
    assert _sensor(se.PhilipsAdapterSensor, {}).native_value is None
    fixed = _sensor(se.PhilipsAdapterSensor, {CONF_BLUETOOTH_ADAPTER: HCI1})
    assert fixed.native_value == HCI1
    connected = _sensor(
        se.PhilipsAdapterSensor, {CONF_BLUETOOTH_ADAPTER: HCI1}, connection_path="hci1"
    )
    assert connected.native_value == "hci1"


# ---------------------------------------------------------------------------
# Setup flow: every BlueZ call targets the chosen adapter
#
# A bond check or pairing on the wrong adapter is how a good bond gets
# wiped: async_pair_and_trust removes a "stale" bond before pairing.
# ---------------------------------------------------------------------------


class _Task:
    def done(self) -> bool:
        return False


def _closing_create_task(coro, *args, **kwargs):
    coro.close()
    return _Task()


@pytest.fixture
def bluez_calls(monkeypatch):
    from custom_components.philips_shaver import dbus_pairing as dp

    monkeypatch.setattr(dp, "is_dbus_available", lambda: True)
    paired = AsyncMock(return_value=True)
    monkeypatch.setattr(dp, "async_is_device_paired", paired)
    pair = AsyncMock()
    monkeypatch.setattr(dp, "async_pair_and_trust", pair)
    monkeypatch.setattr(cf, "describe_available_paths", lambda hass, a: [
        {"name": "hci0", "source": HCI0, "rssi": -50, "is_local": True},
        {"name": "hci1", "source": HCI1, "rssi": -70, "is_local": True},
    ])
    return SimpleNamespace(paired=paired, pair=pair)


async def test_confirm_checks_bond_on_chosen_adapter(monkeypatch, bluez_calls) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow.discovery_info = SimpleNamespace(address=ADDRESS, name="Philips Shaver")
    flow._esp_redirect_checked = True
    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_closing_create_task)
    )

    await flow.async_step_bluetooth_confirm({CONF_BLUETOOTH_ADAPTER: HCI1})

    bluez_calls.paired.assert_awaited_once_with(ADDRESS, HCI1)
    assert flow._bluetooth_adapter == HCI1


async def test_retry_without_field_keeps_the_adapter(monkeypatch, bluez_calls) -> None:
    # not_paired / not_paired_proxy re-enter the confirm step with {}:
    # the adapter chosen before must survive, not fall back to automatic.
    flow = _setup_flow(monkeypatch, TWO)
    flow.discovery_info = SimpleNamespace(address=ADDRESS, name="Philips Shaver")
    flow._esp_redirect_checked = True
    flow._bluetooth_adapter = HCI1
    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_closing_create_task)
    )

    await flow.async_step_not_paired({})

    assert flow._bluetooth_adapter == HCI1
    bluez_calls.paired.assert_awaited_once_with(ADDRESS, HCI1)


async def test_manual_entry_checks_bond_on_chosen_adapter(monkeypatch, bluez_calls) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow.discovery_info = None
    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_closing_create_task)
    )
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_already_configured = MagicMock()

    await flow.async_step_user_bleak(
        {"address": ADDRESS, CONF_BLUETOOTH_ADAPTER: HCI1}
    )

    bluez_calls.paired.assert_awaited_once_with(ADDRESS, HCI1)


async def test_pairing_runs_on_chosen_adapter(monkeypatch, bluez_calls) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow._bluetooth_adapter = HCI1
    monkeypatch.setattr(cf.asyncio, "sleep", AsyncMock())
    flow._async_ble_probe = AsyncMock(return_value={"ok": True, "data": {}})
    flow._async_ensure_awake = AsyncMock(return_value="awake")

    await flow._async_pair_and_probe(ADDRESS)

    bluez_calls.pair.assert_awaited_once_with(ADDRESS, HCI1)


async def test_pairing_waits_for_silent_shaver_and_gives_up(monkeypatch, bluez_calls) -> None:
    # Pair() to a shaver that does not advertise only runs into its 30 s
    # timeout: wait for it instead, and report "asleep" if it never wakes.
    flow = _setup_flow(monkeypatch, TWO)
    flow._bluetooth_adapter = HCI1
    flow._async_ble_probe = AsyncMock()
    flow._async_ensure_awake = AsyncMock(return_value="asleep")

    result = await flow._async_pair_and_probe(ADDRESS)

    assert result == {"ok": False, "error": "asleep"}
    bluez_calls.pair.assert_not_awaited()
    flow._async_ble_probe.assert_not_awaited()


def test_adapter_from_input_reads_section_and_flat() -> None:
    assert cf._adapter_from_input({"adapter": {CONF_BLUETOOTH_ADAPTER: HCI1}}, "auto") == HCI1
    assert cf._adapter_from_input({CONF_BLUETOOTH_ADAPTER: HCI0}, "auto") == HCI0
    assert cf._adapter_from_input({}, HCI1) == HCI1


async def test_confirm_takes_adapter_from_section(monkeypatch, bluez_calls) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow.discovery_info = SimpleNamespace(address=ADDRESS, name="Philips Shaver")
    flow._esp_redirect_checked = True
    flow.hass = SimpleNamespace(
        async_create_task=MagicMock(side_effect=_closing_create_task)
    )

    await flow.async_step_bluetooth_confirm({"adapter": {CONF_BLUETOOTH_ADAPTER: HCI1}})

    bluez_calls.paired.assert_awaited_once_with(ADDRESS, HCI1)
    assert flow._bluetooth_adapter == HCI1


async def test_probe_waits_for_wake_on_fixed_adapter(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow._bluetooth_adapter = HCI1
    watched = []

    def _watch(address, source):
        watched.append(source)
        event = asyncio.Event()
        event.set()
        return event, lambda: None

    monkeypatch.setattr(cf, "watch_advertisements", _watch)
    assert await flow._async_wait_for_wake(ADDRESS, "57s ago") == "awake"
    # The fixed adapter, plus any scanner to tell "silent adapter" apart.
    assert watched == [HCI1, None]


async def test_probe_wait_for_wake_any_adapter_and_timeout(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    watched = []

    def _watch(address, source):
        watched.append(source)
        return asyncio.Event(), lambda: None

    monkeypatch.setattr(cf, "watch_advertisements", _watch)
    monkeypatch.setattr(cf, "PAIR_ADVERTISEMENT_WAIT", 0.01)
    assert await flow._async_wait_for_wake(ADDRESS, "never seen") == "none"
    assert watched == [None]  # Automatic: any scanner


async def test_instant_probe_failure_still_takes_a_moment(monkeypatch) -> None:
    # Finishing before the progress dialog is up leaves the frontend on
    # its spinner — the probe task lasts at least _PROBE_MIN_SECONDS.
    flow = _setup_flow(monkeypatch, TWO)
    monkeypatch.setattr(cf, "_PROBE_MIN_SECONDS", 0.05)

    async def _asleep(address):
        raise cf.DeviceAsleepException

    monkeypatch.setattr(flow, "_async_fetch_capabilities", _asleep)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    assert await flow._async_ble_probe(ADDRESS) == {"ok": False, "error": "asleep"}
    assert loop.time() - t0 >= 0.04


def test_discovery_title_names_model_mac_and_adapter(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow.discovery_info = SimpleNamespace(address=ADDRESS, name="Philips QP4530")
    paths = [{"name": f"hci1 ({HCI1})", "source": HCI1, "rssi": -64, "is_local": True}]
    monkeypatch.setattr(cf, "describe_available_paths", lambda hass, a: paths)
    assert flow._discovery_title() == f"Philips QP4530 · {ADDRESS} · via hci1"

    paths[:] = [{"name": "atom-lite", "source": "x", "rssi": -50, "is_local": False}]
    assert flow._discovery_title().endswith("· via atom-lite (proxy)")

    paths.clear()
    assert flow._discovery_title() == f"Philips QP4530 · {ADDRESS}"


async def test_probe_right_after_pairing_skips_the_wake_gate(monkeypatch) -> None:
    # While connected for Pair() the shaver sent no advertisements; the
    # follow-up probe must not read that as "asleep" and wait 45 s.
    flow = _setup_flow(monkeypatch, TWO)
    flow._ble_just_paired = True
    flow._stale_advertisement = lambda address: "17s ago"
    flow._async_wait_for_wake = AsyncMock(return_value="none")

    assert await flow._async_ensure_awake(ADDRESS) == "awake"
    flow._async_wait_for_wake.assert_not_awaited()
    assert flow._ble_just_paired is False  # one-shot


async def test_silent_fixed_adapter_reports_adapter_not_asleep(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow._bluetooth_adapter = HCI1
    flow._stale_advertisement = lambda address: "60s ago"
    flow._async_wait_for_wake = AsyncMock(return_value="other")
    assert await flow._async_ensure_awake(ADDRESS) == "adapter"

    flow._async_wait_for_wake = AsyncMock(return_value="none")
    assert await flow._async_ensure_awake(ADDRESS) == "asleep"


async def test_wait_reports_other_only_when_heard_during_the_wait(monkeypatch) -> None:
    # Old entries of other scanners prove nothing: only an advertisement
    # on another scanner *during* the wait makes it "other".
    flow = _setup_flow(monkeypatch, TWO)
    flow._bluetooth_adapter = HCI1
    monkeypatch.setattr(cf, "PAIR_ADVERTISEMENT_WAIT", 0.01)
    events = {}

    def _watch(address, source):
        events[source] = asyncio.Event()
        return events[source], lambda: None

    monkeypatch.setattr(cf, "watch_advertisements", _watch)
    assert await flow._async_wait_for_wake(ADDRESS, "60s ago") == "none"

    def _watch_other_hears(address, source):
        event = asyncio.Event()
        if source is None:
            event.set()
        return event, lambda: None

    monkeypatch.setattr(cf, "watch_advertisements", _watch_other_hears)
    assert await flow._async_wait_for_wake(ADDRESS, "60s ago") == "other"


async def test_pairing_not_found_maps_to_own_error(monkeypatch, bluez_calls) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow._async_ensure_awake = AsyncMock(return_value="awake")
    from custom_components.philips_shaver import dbus_pairing as dp

    bluez_calls.pair.side_effect = dp.PairingError(
        "Device X not found in BlueZ — ensure it is powered on and in range"
    )
    assert await flow._async_pair_and_probe(ADDRESS) == {
        "ok": False, "error": "pair_not_found",
    }


async def test_manual_sentinel_keeps_the_adapter(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow.discovery_info = None
    flow._ble_probe_task = None
    flow.hass = SimpleNamespace()
    await flow.async_step_user_bleak(
        {"address": cf._MANUAL_ADDRESS, "adapter": {CONF_BLUETOOTH_ADAPTER: HCI1}}
    )
    assert flow._manual_address_entry is True
    assert flow._bluetooth_adapter == HCI1


async def test_at_least_does_not_delay_cancellation() -> None:
    async def _forever():
        await asyncio.sleep(10)

    loop = asyncio.get_running_loop()
    task = loop.create_task(cf._at_least(_forever, seconds=5))
    await asyncio.sleep(0)
    t0 = loop.time()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert loop.time() - t0 < 0.5


async def test_at_least_waits_out_an_instant_failure() -> None:
    async def _fail():
        raise RuntimeError("boom")

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    try:
        await cf._at_least(_fail, seconds=0.05)
    except RuntimeError:
        pass
    assert loop.time() - t0 >= 0.04



async def test_wait_timeout_race_with_both_events_counts_as_awake(monkeypatch) -> None:
    flow = _setup_flow(monkeypatch, TWO)
    flow._bluetooth_adapter = HCI1
    monkeypatch.setattr(cf, "PAIR_ADVERTISEMENT_WAIT", 0.01)
    fixed = asyncio.Event()

    def _watch(address, source):
        if source is None:
            event = asyncio.Event()
            event.set()
            return event, lambda: None
        return fixed, lambda: None

    async def _timeout_then_set(awaitable, timeout):
        awaitable.close()
        fixed.set()  # the fixed adapter's packet lands right at the timeout
        raise TimeoutError

    monkeypatch.setattr(cf, "watch_advertisements", _watch)
    monkeypatch.setattr(cf.asyncio, "wait_for", _timeout_then_set)
    assert await flow._async_wait_for_wake(ADDRESS, "60s ago") == "awake"
