"""Tests for the bundled-card registration (frontend.py).

The card must end up in the Lovelace resource registry in storage mode
(dynamic loading — survives the service worker's cached app shell, issue
#14) and fall back to ``add_extra_js_url`` when the registry is read-only
(YAML mode) or unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.philips_shaver.const import DOMAIN
from custom_components.philips_shaver.frontend import (
    CARD_URL,
    ISSUE_STANDALONE_CARD,
    async_register_card,
    async_remove_card_resource,
)

VERSION = json.loads(
    (
        Path(__file__).parents[1]
        / "custom_components"
        / "philips_shaver"
        / "manifest.json"
    ).read_text(encoding="utf-8")
)["version"]
VERSIONED_URL = f"{CARD_URL}?v={VERSION}"


class FakeStorageResources:
    """Writable resource collection mimicking ResourceStorageCollection."""

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []
        self.loaded = False
        self._next_id = 1000

    async def async_load(self) -> None:
        pass

    def async_items(self) -> list[dict]:
        return self.items

    async def async_create_item(self, data: dict) -> dict:
        item = {"id": str(self._next_id), "type": data["res_type"], "url": data["url"]}
        self._next_id += 1
        self.items.append(item)
        return item

    async def async_update_item(self, item_id: str, data: dict) -> dict:
        for item in self.items:
            if item["id"] == item_id:
                item.update({"url": data["url"]})
                return item
        raise KeyError(item_id)

    async def async_delete_item(self, item_id: str) -> None:
        self.items[:] = [item for item in self.items if item["id"] != item_id]


class FakeYamlResources:
    """Read-only resource collection mimicking ResourceYAMLCollection."""

    loaded = True

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []

    def async_items(self) -> list[dict]:
        return self.items


@pytest.fixture(autouse=True)
def mock_static_paths(hass):
    """hass.http isn't set up in these tests — stub the static path API."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()


@pytest.fixture(autouse=True)
def mock_integration_version():
    """Resolve the integration version without the loader machinery."""
    with patch(
        "custom_components.philips_shaver.frontend.async_get_integration",
        return_value=SimpleNamespace(version=VERSION),
    ):
        yield


@pytest.fixture
def mock_extra_js():
    with patch(
        "custom_components.philips_shaver.frontend.add_extra_js_url"
    ) as mock:
        yield mock


def _set_resources(hass, resources) -> None:
    hass.data["lovelace"] = SimpleNamespace(resources=resources)


async def test_resource_created(hass, mock_extra_js) -> None:
    """Storage mode, fresh install: one versioned resource, no extra JS."""
    resources = FakeStorageResources()
    _set_resources(hass, resources)

    await async_register_card(hass)

    assert [item["url"] for item in resources.items] == [VERSIONED_URL]
    mock_extra_js.assert_not_called()
    hass.http.async_register_static_paths.assert_awaited_once()


async def test_resource_updated_in_place_and_deduped(hass, mock_extra_js) -> None:
    """A manual workaround entry is adopted; duplicates are removed."""
    resources = FakeStorageResources(
        [
            {"id": "1", "type": "module", "url": CARD_URL},
            {"id": "2", "type": "module", "url": f"{CARD_URL}?v=0.1.0"},
        ]
    )
    _set_resources(hass, resources)

    await async_register_card(hass)

    assert [(item["id"], item["url"]) for item in resources.items] == [
        ("1", VERSIONED_URL)
    ]
    mock_extra_js.assert_not_called()


async def test_resource_already_current(hass, mock_extra_js) -> None:
    """Same version registered again: nothing changes, nothing is created."""
    resources = FakeStorageResources(
        [{"id": "1", "type": "module", "url": VERSIONED_URL}]
    )
    _set_resources(hass, resources)
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()

    await async_register_card(hass)

    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_not_awaited()
    mock_extra_js.assert_not_called()


async def test_yaml_mode_falls_back_to_extra_js(hass, mock_extra_js) -> None:
    """Read-only YAML resources: the module is injected into the app shell."""
    _set_resources(hass, FakeYamlResources())

    await async_register_card(hass)

    mock_extra_js.assert_called_once_with(hass, VERSIONED_URL)


async def test_no_lovelace_falls_back_to_extra_js(hass, mock_extra_js) -> None:
    """No Lovelace data at all: fall back rather than lose the card."""
    await async_register_card(hass)

    mock_extra_js.assert_called_once_with(hass, VERSIONED_URL)


async def test_registry_error_falls_back_to_extra_js(hass, mock_extra_js) -> None:
    """A failing registry write must not lose the card."""
    resources = FakeStorageResources()
    resources.async_create_item = AsyncMock(side_effect=OSError("storage broken"))
    _set_resources(hass, resources)

    await async_register_card(hass)

    mock_extra_js.assert_called_once_with(hass, VERSIONED_URL)


async def test_standalone_leftover_creates_repair_issue(hass, mock_extra_js) -> None:
    """A leftover standalone card resource raises the repair issue."""
    standalone = "/hacsfiles/philips-shaver-card/philips_shaver_card.js"
    resources = FakeStorageResources(
        [{"id": "1", "type": "module", "url": standalone}]
    )
    _set_resources(hass, resources)

    await async_register_card(hass)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_STANDALONE_CARD)
    assert issue is not None
    # Our own resource was still registered alongside the repair issue.
    assert VERSIONED_URL in [item["url"] for item in resources.items]


async def test_own_resource_does_not_trigger_repair_issue(hass, mock_extra_js) -> None:
    """Our static-path resource (or a manual copy of it) is not a leftover."""
    resources = FakeStorageResources(
        [{"id": "1", "type": "module", "url": CARD_URL}]
    )
    _set_resources(hass, resources)

    await async_register_card(hass)

    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_STANDALONE_CARD) is None


async def test_remove_card_resource(hass) -> None:
    """Removal drops our entries and leaves foreign ones untouched."""
    other = "/hacsfiles/some-other-card/card.js"
    resources = FakeStorageResources(
        [
            {"id": "1", "type": "module", "url": VERSIONED_URL},
            {"id": "2", "type": "module", "url": CARD_URL},
            {"id": "3", "type": "module", "url": other},
        ]
    )
    _set_resources(hass, resources)

    await async_remove_card_resource(hass)

    assert [item["url"] for item in resources.items] == [other]


async def test_remove_card_resource_yaml_mode_is_noop(hass) -> None:
    """Read-only YAML resources: removal must not blow up."""
    _set_resources(hass, FakeYamlResources([{"id": "1", "url": VERSIONED_URL}]))

    await async_remove_card_resource(hass)


async def test_real_lovelace_storage_roundtrip(hass, mock_extra_js) -> None:
    """End-to-end against core's real ResourceStorageCollection.

    Guards our create/update payloads against core schema changes
    (``res_type`` vs ``type``) that the fakes above can't catch.
    """
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})

    await async_register_card(hass)
    lovelace = hass.data["lovelace"]
    resources = (
        lovelace["resources"] if isinstance(lovelace, dict) else lovelace.resources
    )
    assert [item["url"] for item in resources.async_items()] == [VERSIONED_URL]

    # Second run (restart with same version): still exactly one entry.
    await async_register_card(hass)
    assert [item["url"] for item in resources.async_items()] == [VERSIONED_URL]

    # Version bump: updated in place.
    with patch(
        "custom_components.philips_shaver.frontend.async_get_integration",
        return_value=SimpleNamespace(version="99.0.0"),
    ):
        await async_register_card(hass)
    items = resources.async_items()
    assert [item["url"] for item in items] == [f"{CARD_URL}?v=99.0.0"]

    await async_remove_card_resource(hass)
    assert resources.async_items() == []
    mock_extra_js.assert_not_called()


async def test_resource_restored_after_remove_and_readd(hass, mock_extra_js) -> None:
    """Delete all entries, then add one again: the resource must come back.

    ``async_setup`` runs only once per HA run, so the entry-setup path has
    to re-create the resource (found in live testing 2026-07-16).
    """
    from custom_components.philips_shaver.frontend import async_ensure_card_resource

    resources = FakeStorageResources()
    _set_resources(hass, resources)

    await async_register_card(hass)
    await async_remove_card_resource(hass)
    assert resources.items == []

    await async_ensure_card_resource(hass)

    assert [item["url"] for item in resources.items] == [VERSIONED_URL]
    mock_extra_js.assert_not_called()


async def test_yaml_fallback_registered_once_per_run(hass, mock_extra_js) -> None:
    """Repeated entry setups must not stack extra JS URLs."""
    from custom_components.philips_shaver.frontend import async_ensure_card_resource

    _set_resources(hass, FakeYamlResources())

    await async_register_card(hass)
    await async_ensure_card_resource(hass)
    await async_ensure_card_resource(hass)

    mock_extra_js.assert_called_once_with(hass, VERSIONED_URL)
