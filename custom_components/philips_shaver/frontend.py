"""Serve the bundled Lovelace card (Philips Shaver Card).

The card ships inside this integration (``www/philips_shaver_card.js``). In
storage mode (the default) it is registered as a proper Lovelace resource:
resources are loaded dynamically by the frontend, so the card survives the
service worker's cached app shell (which intermittently dropped
``add_extra_js_url`` modules after updates/restarts, issue #14) and also
works on Cast dashboards, which never load extra modules. In YAML mode the
resource list is read-only, so the card falls back to ``add_extra_js_url``.

If a leftover standalone installation of the card is still registered as a
Lovelace resource, a repair issue asks the user to remove it: both copies
register the same custom element and the first one to load wins, so a stale
standalone copy would silently shadow the bundled card.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "philips_shaver_card.js"
STATIC_PATH = "/philips_shaver_static"
CARD_URL = f"{STATIC_PATH}/{CARD_FILENAME}"
ISSUE_STANDALONE_CARD = "standalone_card_installed"
DATA_EXTRA_JS_ADDED = f"{DOMAIN}_extra_js_added"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled card and load it on every dashboard."""
    www_dir = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_PATH, str(www_dir), cache_headers=True)]
    )
    await async_ensure_card_resource(hass)
    await _async_check_standalone_card(hass)


async def async_ensure_card_resource(hass: HomeAssistant) -> None:
    """Make sure the card's Lovelace resource exists and is current.

    Runs on component setup and again on every entry setup: removing the
    last entry deletes the resource, and re-adding one later must bring it
    back without a restart (``async_setup`` only runs once per HA run).
    """
    integration = await async_get_integration(hass, DOMAIN)
    # Version query defeats the browser cache when the integration updates.
    versioned_url = f"{CARD_URL}?v={integration.version}"

    if await _async_register_resource(hass, versioned_url):
        return

    # YAML-mode resources (read-only) or no Lovelace resource registry —
    # inject the module into the app shell instead (once per HA run).
    if not hass.data.get(DATA_EXTRA_JS_ADDED):
        add_extra_js_url(hass, versioned_url)
        hass.data[DATA_EXTRA_JS_ADDED] = True


async def async_remove_card_resource(hass: HomeAssistant) -> None:
    """Remove our Lovelace resource entry (last config entry was removed)."""
    resources = await _async_get_resources(hass)
    if resources is None or not hasattr(resources, "async_delete_item"):
        return
    try:
        for item in list(resources.async_items()):
            if (item.get("url") or "").split("?")[0] == CARD_URL:
                await resources.async_delete_item(item["id"])
                _LOGGER.info("Removed Lovelace resource %s", item["url"])
    except Exception:  # noqa: BLE001 - cleanup must never block removal
        _LOGGER.debug("Could not remove Lovelace resource", exc_info=True)


async def _async_get_resources(hass: HomeAssistant):
    """Return the loaded Lovelace resource collection, or None."""
    lovelace = hass.data.get("lovelace")
    # LovelaceData dataclass on current cores, a plain dict before 2025.2.
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None:
        return None

    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
    except Exception:  # noqa: BLE001 - never break setup over the card
        _LOGGER.debug("Could not load Lovelace resources", exc_info=True)
        return None
    return resources


async def _async_register_resource(hass: HomeAssistant, versioned_url: str) -> bool:
    """Upsert the card into the Lovelace resource registry (storage mode).

    Returns True when the resource is registered (created, updated, or
    already current) — False when the registry isn't writable and the caller
    should fall back to ``add_extra_js_url``.
    """
    resources = await _async_get_resources(hass)
    if resources is None or not hasattr(resources, "async_create_item"):
        return False

    try:
        ours = [
            item
            for item in resources.async_items()
            if (item.get("url") or "").split("?")[0] == CARD_URL
        ]
        if not ours:
            await resources.async_create_item(
                {"res_type": "module", "url": versioned_url}
            )
            _LOGGER.info("Registered Lovelace resource %s", versioned_url)
            return True

        first, *duplicates = ours
        if first["url"] != versioned_url:
            await resources.async_update_item(
                first["id"], {"res_type": "module", "url": versioned_url}
            )
            _LOGGER.info(
                "Updated Lovelace resource %s -> %s", first["url"], versioned_url
            )
        # A manually added workaround entry plus ours, or repeated manual
        # adds: the card only needs to load once.
        for duplicate in duplicates:
            await resources.async_delete_item(duplicate["id"])
            _LOGGER.info("Removed duplicate Lovelace resource %s", duplicate["url"])
    except Exception:  # noqa: BLE001 - fall back rather than lose the card
        _LOGGER.warning(
            "Could not register the card as a Lovelace resource", exc_info=True
        )
        return False
    return True


async def _async_check_standalone_card(hass: HomeAssistant) -> None:
    """Create/clear a repair issue for leftover standalone card resources."""
    resources = await _async_get_resources(hass)
    if resources is None:
        return

    standalone_urls = [
        item.get("url")
        for item in resources.async_items()
        if CARD_FILENAME in (item.get("url") or "")
        and STATIC_PATH not in item["url"]
    ]

    if standalone_urls:
        _LOGGER.warning(
            "Standalone Philips Shaver Card resource(s) found: %s — the card is "
            "bundled with the integration now, remove the standalone installation",
            standalone_urls,
        )
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_STANDALONE_CARD,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_STANDALONE_CARD,
            translation_placeholders={"url": standalone_urls[0]},
            learn_more_url="https://github.com/mtheli/philips_shaver#lovelace-card",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_STANDALONE_CARD)
