from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.philips_shaver import transport as tr
from custom_components.philips_shaver.config_flow import PhilipsShaverConfigFlow

ADDRESS = "F4:B3:B1:AA:BB:CC"


def test_local_selector_ignores_stronger_proxy(monkeypatch) -> None:
    class LocalScanner:
        pass

    local_device = object()
    local = SimpleNamespace(
        scanner=LocalScanner(),
        advertisement=SimpleNamespace(rssi=-82),
        ble_device=local_device,
    )
    proxy = SimpleNamespace(
        scanner=SimpleNamespace(),
        advertisement=SimpleNamespace(rssi=-42),
        ble_device=object(),
    )
    monkeypatch.setattr(tr, "HaScanner", LocalScanner)
    monkeypatch.setattr(
        tr,
        "async_scanner_devices_by_address",
        lambda hass, address, connectable=True: [proxy, local],
    )

    selected = tr.local_bluez_scanner_device_from_address(
        SimpleNamespace(), ADDRESS
    )

    assert selected is local
    assert tr.local_bluez_device_from_address(SimpleNamespace(), ADDRESS) is local_device


def test_direct_preview_prefers_local_over_stronger_proxy(monkeypatch) -> None:
    flow = PhilipsShaverConfigFlow()
    flow.flow_id = "test-flow"
    flow.handler = "philips_shaver"
    flow.discovery_info = SimpleNamespace(address=ADDRESS, name="Philips Shaver")
    flow.hass = SimpleNamespace()
    monkeypatch.setattr(
        "custom_components.philips_shaver.config_flow.describe_available_paths",
        MagicMock(return_value=[
            {"name": "aquarium-multisensor", "rssi": -42, "is_local": False},
            {"name": "hci0", "rssi": -82, "is_local": True},
        ]),
    )

    via, warning, _values = flow._transport_lines()

    assert via == " via **Direct Bluetooth** (hci0, -82 dBm)"
    assert warning == ""


async def test_manual_selection_does_not_abort_for_discovery_flow(monkeypatch) -> None:
    class FakeTask:
        def done(self) -> bool:
            return False

    flow = PhilipsShaverConfigFlow()
    flow.flow_id = "test-flow"
    flow.handler = "philips_shaver"
    flow.discovery_info = None

    def create_task(coro, *args, **kwargs):
        coro.close()
        return FakeTask()

    flow.hass = SimpleNamespace(async_create_task=MagicMock(side_effect=create_task))
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

    result = await flow.async_step_user_bleak({"address": ADDRESS})

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    flow.async_set_unique_id.assert_awaited_once_with(
        ADDRESS, raise_on_progress=False
    )
    flow._abort_if_already_configured.assert_called_once_with()


def test_ha_client_selector_only_considers_local_scanners(monkeypatch) -> None:
    class LocalScanner:
        pass

    local_scanner = LocalScanner()
    proxy_scanner = SimpleNamespace()
    local_device = SimpleNamespace(address=ADDRESS)
    proxy_device = SimpleNamespace(address=ADDRESS)
    local = SimpleNamespace(
        scanner=local_scanner,
        advertisement=SimpleNamespace(rssi=-82),
        ble_device=local_device,
    )
    proxy = SimpleNamespace(
        scanner=proxy_scanner,
        advertisement=SimpleNamespace(rssi=-42),
        ble_device=proxy_device,
    )
    manager = SimpleNamespace(
        async_scanner_devices_by_address=MagicMock(return_value=[proxy, local])
    )
    client = object.__new__(tr._LocalBluezHaBleakClient)
    client._HaBleakClientWrapper__address = ADDRESS  # noqa: SLF001
    backend = object()
    calls = []

    def backend_for_device(self, manager_arg, scanner, device):
        calls.append((manager_arg, scanner, device))
        return backend

    monkeypatch.setattr(tr, "HaScanner", LocalScanner)
    monkeypatch.setattr(
        tr._LocalBluezHaBleakClient,
        "_async_get_backend_for_ble_device",
        backend_for_device,
    )

    selected = client._async_get_best_available_backend_and_device(manager)

    assert selected is backend
    assert calls == [(manager, local_scanner, local_device)]


def test_ha_client_selector_falls_back_if_private_hook_changes(monkeypatch) -> None:
    class LocalScanner:
        pass

    local = SimpleNamespace(
        scanner=LocalScanner(),
        advertisement=SimpleNamespace(rssi=-60),
        ble_device=SimpleNamespace(address=ADDRESS),
    )
    manager = SimpleNamespace(
        async_scanner_devices_by_address=MagicMock(return_value=[local])
    )
    client = object.__new__(tr._LocalBluezHaBleakClient)
    client._HaBleakClientWrapper__address = ADDRESS  # noqa: SLF001
    fallback_backend = object()

    def incompatible_backend_hook(self, manager_arg, scanner, device):
        raise TypeError("changed signature")

    monkeypatch.setattr(tr, "HaScanner", LocalScanner)
    monkeypatch.setattr(
        tr._LocalBluezHaBleakClient,
        "_async_get_backend_for_ble_device",
        incompatible_backend_hook,
    )
    monkeypatch.setattr(
        tr.HaBleakClientWithServiceCache,
        "_async_get_best_available_backend_and_device",
        lambda self, manager_arg: fallback_backend,
    )

    assert (
        client._async_get_best_available_backend_and_device(manager)
        is fallback_backend
    )


def test_ha_client_class_falls_back_if_private_hooks_are_missing(monkeypatch) -> None:
    class FutureHaClient:
        pass

    monkeypatch.setattr(tr, "HaBleakClientWithServiceCache", FutureHaClient)

    assert tr.local_bluez_client_class() is FutureHaClient


async def test_runtime_connect_keeps_local_scanner_for_rssi(monkeypatch) -> None:
    scanner = SimpleNamespace()
    device = SimpleNamespace(address=ADDRESS, name="Philips QP4530")
    scanner_device = SimpleNamespace(scanner=scanner, ble_device=device)
    client = SimpleNamespace(
        is_connected=True,
        _connected_scanner=scanner,
    )
    establish = AsyncMock(return_value=client)

    monkeypatch.setattr(
        tr, "local_bluez_scanner_device_from_address",
        lambda hass, address: scanner_device,
    )
    monkeypatch.setattr(tr, "bleak_establish", establish)
    monkeypatch.setattr(tr, "is_local_bluez_connection", lambda client: True)
    monkeypatch.setattr(tr, "describe_connection_path", lambda *args: "hci0")

    transport = tr.BleakTransport(SimpleNamespace(), ADDRESS)
    await transport.connect()

    assert transport._connected_scanner is scanner
    assert transport.connection_path == "hci0"
    assert establish.await_args.args[0] is tr._LocalBluezHaBleakClient
    assert establish.await_args.args[1] is device


async def test_runtime_connect_rejects_nonlocal_fallback(monkeypatch) -> None:
    scanner = SimpleNamespace()
    device = SimpleNamespace(address=ADDRESS, name="Philips QP4530")
    scanner_device = SimpleNamespace(scanner=scanner, ble_device=device)
    client = SimpleNamespace(
        is_connected=True,
        _connected_scanner=SimpleNamespace(),
        disconnect=AsyncMock(),
    )
    establish = AsyncMock(return_value=client)

    monkeypatch.setattr(
        tr, "local_bluez_scanner_device_from_address",
        lambda hass, address: scanner_device,
    )
    monkeypatch.setattr(tr, "bleak_establish", establish)
    monkeypatch.setattr(tr, "is_local_bluez_connection", lambda client: False)
    monkeypatch.setattr(
        tr, "describe_connection_path", lambda *args: "aquarium-multisensor"
    )

    transport = tr.BleakTransport(SimpleNamespace(), ADDRESS)
    with pytest.raises(tr.TransportError, match="not a local Bluetooth adapter"):
        await transport.connect()

    client.disconnect.assert_awaited_once()
    assert transport._client is None
