"""Bond handling with more than one local Bluetooth adapter.

BlueZ keeps one device object — and one bond — per adapter. With the
Bluetooth adapter option, an entry may connect through hci0 while the
shaver is bonded on hci1 only (ported from the Sonicare integration,
where every connect over hci0 then ended in "failed to discover
services, device disconnected"). Bond checks, pairing and removal must
therefore target an adapter; a first-match lookup by MAC alone hits
whichever adapter BlueZ lists first.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.philips_shaver import dbus_pairing as dp

MAC = "F4:B3:B1:AA:BB:CC"
HCI0 = "00:0A:CD:46:B2:2D"
HCI1 = "58:D8:12:3E:CA:B2"
DEV = "dev_F4_B3_B1_AA_BB_CC"


def _v(value):
    return SimpleNamespace(value=value)


class FakeBlueZ:
    """Just enough of BlueZ's object tree and calls for dbus_pairing."""

    def __init__(self, paired: dict[str, bool]) -> None:
        self.objects: dict[str, dict] = {
            "/org/bluez/hci0": {"org.bluez.Adapter1": {"Address": _v(HCI0)}},
            "/org/bluez/hci1": {"org.bluez.Adapter1": {"Address": _v(HCI1)}},
        }
        for adapter, is_paired in paired.items():
            self._add_device(adapter, is_paired)
        self.removed: list[str] = []
        self.paired_on: list[str] = []
        # Device objects that reappear after RemoveDevice (shaver awake).
        self.reappear = True
        self.pair_hangs = False
        self.bond_after_timeout = False
        self.cancelled: list[str] = []
        self.disconnected: list[str] = []

    def _add_device(self, adapter: str, is_paired: bool) -> None:
        self.objects[f"/org/bluez/{adapter}/{DEV}"] = {
            "org.bluez.Device1": {
                "Address": _v(MAC),
                "Adapter": _v(f"/org/bluez/{adapter}"),
                "Paired": _v(is_paired),
            }
        }

    def bus(self):
        return _FakeBus(self)


class _FakeBus:
    def __init__(self, bluez: FakeBlueZ) -> None:
        self.bluez = bluez
        self.connected = False

    async def connect(self):
        self.connected = True
        return self

    def disconnect(self) -> None:
        self.connected = False

    def export(self, path, iface) -> None:
        pass

    def unexport(self, path) -> None:
        pass

    async def introspect(self, name, path):
        return None

    def get_proxy_object(self, name, path, intro):
        return _FakeProxy(self.bluez, path)


class _FakeProxy:
    def __init__(self, bluez: FakeBlueZ, path: str) -> None:
        self.bluez = bluez
        self.path = path

    def get_interface(self, iface: str):
        bluez, path = self.bluez, self.path

        async def _noop(*args, **kwargs):
            return None

        if iface == "org.freedesktop.DBus.ObjectManager":
            async def managed():
                return bluez.objects
            return SimpleNamespace(call_get_managed_objects=managed)
        if iface == "org.freedesktop.DBus.Properties":
            async def get(_iface, prop):
                return bluez.objects[path]["org.bluez.Device1"][prop]
            return SimpleNamespace(call_get=get, call_set=_noop)
        if iface == "org.bluez.Adapter1":
            async def remove(device_path):
                bluez.removed.append(device_path)
                bluez.objects.pop(device_path, None)
                if bluez.reappear:
                    bluez._add_device(device_path.split("/")[3], False)
            return SimpleNamespace(call_remove_device=remove)
        if iface == "org.bluez.Device1":
            async def pair():
                bluez.paired_on.append(path)
                if bluez.pair_hangs:
                    # BlueZ finishes the bond, but the reply never comes
                    # within our timeout.
                    bluez.objects[path]["org.bluez.Device1"]["Paired"] = _v(
                        bluez.bond_after_timeout
                    )
                    await asyncio.Event().wait()
                bluez.objects[path]["org.bluez.Device1"]["Paired"] = _v(True)

            async def cancel():
                bluez.cancelled.append(path)
            async def disconnect():
                bluez.disconnected.append(path)
                bluez.objects[path]["org.bluez.Device1"]["Connected"] = _v(False)
            return SimpleNamespace(
                call_pair=pair, call_disconnect=disconnect, call_cancel_pairing=cancel
            )
        if iface == "org.bluez.AgentManager1":
            return SimpleNamespace(
                call_register_agent=_noop,
                call_request_default_agent=_noop,
                call_unregister_agent=_noop,
            )
        raise AssertionError(iface)


@pytest.fixture
def bluez(monkeypatch):
    """hci0 knows the shaver unpaired, hci1 holds the bond."""
    fake = FakeBlueZ({"hci0": False, "hci1": True})
    monkeypatch.setattr(dp, "MessageBus", lambda bus_type=None: fake.bus())

    async def _fast_sleep(_delay):
        return None

    monkeypatch.setattr(dp.asyncio, "sleep", _fast_sleep)
    return fake


async def test_find_device_paths_per_adapter(bluez) -> None:
    bus = bluez.bus()
    assert await dp._find_device_paths(bus, MAC) == [
        f"/org/bluez/hci0/{DEV}", f"/org/bluez/hci1/{DEV}",
    ]
    assert await dp._find_device_paths(bus, MAC, HCI1) == [f"/org/bluez/hci1/{DEV}"]
    # Case of the stored option must not matter.
    assert await dp._find_device_path(bus, MAC.lower(), HCI0.lower()) == (
        f"/org/bluez/hci0/{DEV}"
    )
    # A source that is no local adapter: nothing to find.
    assert await dp._find_device_paths(bus, MAC, "98:88:E0:0E:DA:D2") == []


async def test_bond_check_asks_the_target_adapter(bluez) -> None:
    # The bond on hci1 must not count for a connection over hci0.
    assert await dp.async_is_device_paired(MAC, HCI0) is False
    assert await dp.async_is_device_paired(MAC, HCI1) is True


async def test_pairing_on_hci0_leaves_hci1_bond_alone(bluez) -> None:
    await dp.async_pair_and_trust(MAC, HCI0)

    assert bluez.paired_on == [f"/org/bluez/hci0/{DEV}"]
    assert bluez.removed == []
    assert bluez.objects[f"/org/bluez/hci1/{DEV}"]["org.bluez.Device1"]["Paired"].value


async def test_stale_bond_removal_stays_on_target_adapter(bluez) -> None:
    # hci1's bond is stale: removal and re-discovery must stay on hci1 and
    # never pick up hci0's unrelated device object.
    await dp.async_pair_and_trust(MAC, HCI1)

    assert bluez.removed == [f"/org/bluez/hci1/{DEV}"]
    assert bluez.paired_on == [f"/org/bluez/hci1/{DEV}"]


async def test_pairing_waits_for_device_under_target_adapter(bluez) -> None:
    # hci0 has not heard the shaver yet: no device object there.
    bluez.objects.pop(f"/org/bluez/hci0/{DEV}")
    with pytest.raises(dp.PairingError, match="not found"):
        await dp.async_pair_and_trust(MAC, HCI0)
    # The bond on hci1 was not touched while looking.
    assert bluez.removed == [] and bluez.paired_on == []


async def test_remove_device_without_adapter_clears_all(bluez) -> None:
    bluez.reappear = False
    assert await dp.async_remove_device(MAC) is True
    assert bluez.removed == [f"/org/bluez/hci0/{DEV}", f"/org/bluez/hci1/{DEV}"]


async def test_remove_device_on_one_adapter(bluez) -> None:
    bluez.reappear = False
    assert await dp.async_remove_device(MAC, HCI0) is True
    assert bluez.removed == [f"/org/bluez/hci0/{DEV}"]


async def test_listener_paths(bluez) -> None:
    bus = bluez.bus()
    # Every adapter, also one that has not seen the shaver yet.
    bluez.objects.pop(f"/org/bluez/hci0/{DEV}")
    assert await dp._device_paths_on_adapters(bus, MAC) == [
        f"/org/bluez/hci0/{DEV}", f"/org/bluez/hci1/{DEV}",
    ]
    assert await dp._device_paths_on_adapters(bus, MAC, HCI0) == [
        f"/org/bluez/hci0/{DEV}",
    ]
    # An unknown source (no local adapter): nothing to listen on.
    assert await dp._device_paths_on_adapters(bus, MAC, "98:88:E0:0E:DA:D2") == []


async def test_remove_device_continues_after_one_adapter_refuses(bluez, monkeypatch) -> None:
    # A refusal on hci0 must not leave the bond on hci1 behind.
    bluez.reappear = False
    real = _FakeProxy.get_interface

    def get_interface(self, iface):
        result = real(self, iface)
        if iface == "org.bluez.Adapter1" and self.path == "/org/bluez/hci0":
            async def refuse(device_path):
                raise dp.DBusError("org.bluez.Error.Failed", "busy")
            return SimpleNamespace(call_remove_device=refuse)
        return result

    monkeypatch.setattr(_FakeProxy, "get_interface", get_interface)
    assert await dp.async_remove_device(MAC) is False
    assert bluez.removed == [f"/org/bluez/hci1/{DEV}"]


async def test_paired_adapters_lists_bonded_adapters(bluez) -> None:
    assert await dp.async_paired_adapters(MAC) == [HCI1]
    bluez.objects[f"/org/bluez/hci0/{DEV}"]["org.bluez.Device1"]["Paired"] = _v(True)
    assert await dp.async_paired_adapters(MAC) == [HCI0, HCI1]


async def test_pair_timeout_keeps_a_bond_bluez_finished(bluez, monkeypatch) -> None:
    """Our wait ends, BlueZ's pairing does not: a late bond counts."""
    monkeypatch.setattr(dp, "PAIR_TIMEOUT", 0.01)
    bluez.pair_hangs = True
    bluez.bond_after_timeout = True
    await dp.async_pair_and_trust(MAC, HCI0)
    assert bluez.cancelled == [f"/org/bluez/hci0/{DEV}"]


async def test_pair_timeout_without_bond_still_fails(bluez, monkeypatch) -> None:
    monkeypatch.setattr(dp, "PAIR_TIMEOUT", 0.01)
    bluez.pair_hangs = True
    with pytest.raises(dp.PairingError, match="timed out"):
        await dp.async_pair_and_trust(MAC, HCI0)
    assert bluez.cancelled == [f"/org/bluez/hci0/{DEV}"]


async def test_leftover_link_is_dropped_only_where_connected(bluez) -> None:
    # A connect cancelled mid-setup left a link on hci1 (bonded there);
    # hci0 only knows the shaver. Only hci1 gets a Disconnect.
    bluez.objects[f"/org/bluez/hci1/{DEV}"]["org.bluez.Device1"]["Connected"] = _v(True)
    assert await dp.async_disconnect_device(MAC) == [HCI1]
    assert bluez.disconnected == [f"/org/bluez/hci1/{DEV}"]
    # Nothing connected any more: nothing to do, and no bond touched.
    assert await dp.async_disconnect_device(MAC) == []
    assert bluez.removed == []


async def test_pair_log_names_adapter_and_duration(bluez, caplog) -> None:
    caplog.set_level("INFO", logger=dp.__name__)
    await dp.async_pair_and_trust(MAC, HCI0)
    assert f"Starting BLE pairing with {MAC} via hci0 ({HCI0})" in caplog.text
    assert f"Pairing successful for {MAC} via hci0 ({HCI0}) (" in caplog.text
