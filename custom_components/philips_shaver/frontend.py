"""Serve the bundled Lovelace card (Philips Shaver Card).

The card ships inside this integration (``www/philips_shaver_card.js``) and is
loaded on every dashboard via ``add_extra_js_url`` — users don't need to add a
Lovelace resource. If a leftover standalone installation of the card is still
registered as a Lovelace resource, a repair issue asks the user to remove it:
both copies register the same custom element and the first one to load wins,
so a stale standalone copy would silently shadow the bundled card.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "philips_shaver_card.js"
STATIC_PATH = "/philips_shaver_static"
ISSUE_STANDALONE_CARD = "standalone_card_installed"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled card and schedule the standalone-leftover check."""
    integration = await async_get_integration(hass, DOMAIN)
    www_dir = Path(__file__).parent / "www"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_PATH, str(www_dir), cache_headers=True)]
    )
    # Version query defeats the browser cache when the integration updates.
    add_extra_js_url(hass, f"{STATIC_PATH}/{CARD_FILENAME}?v={integration.version}")

    # Lovelace resources aren't available until HA has fully started.
    if hass.state is CoreState.running:
        await _async_check_standalone_card(hass)
    else:

        @callback
        def _schedule_check(_: Event) -> None:
            hass.async_create_task(_async_check_standalone_card(hass))

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _schedule_check)


async def _async_check_standalone_card(hass: HomeAssistant) -> None:
    """Create/clear a repair issue for leftover standalone card resources."""
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        return

    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
    except Exception:  # noqa: BLE001 - never break setup over a hint
        _LOGGER.debug("Could not load Lovelace resources", exc_info=True)
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
