"""Tests for the bridge firmware update entity.

An unreachable bridge cannot say which firmware it runs. The entity must
then be unavailable instead of comparing a stored, possibly stale version
against the latest one and showing an update that is not pending.
"""

from types import SimpleNamespace

from custom_components.philips_shaver.update import ShaverBridgeUpdate


def _update(alive: bool, version: str | None, latest: str | None) -> ShaverBridgeUpdate:
    entity = ShaverBridgeUpdate.__new__(ShaverBridgeUpdate)
    entity.coordinator = SimpleNamespace(
        transport=SimpleNamespace(is_bridge_alive=alive, bridge_version=version)
    )
    entity._latest_version = latest
    return entity


def test_offline_bridge_is_unavailable() -> None:
    assert _update(False, None, "1.14.2").available is False
    assert _update(False, "1.12.0", "1.14.2").available is False


def test_online_without_reported_version_shows_no_update() -> None:
    entity = _update(True, None, "1.14.2")
    assert entity.available is True
    assert entity.installed_version is None


def test_online_with_older_version_shows_update() -> None:
    entity = _update(True, "1.12.0", "1.14.2")
    assert entity.installed_version == "1.12.0"
    assert entity.latest_version == "1.14.2"


def test_online_with_same_or_newer_version_is_up_to_date() -> None:
    assert _update(True, "1.14.2", "1.14.2").latest_version == "1.14.2"
    assert _update(True, "1.15.0", "1.14.2").latest_version == "1.15.0"
