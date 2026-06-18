"""Tuya Watering — weather-aware valve control via Tuya/Zigbee."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import CONF_CORE_ENTRY_ID, CONF_VALVES, DOMAIN, DOMAIN_CORE
from .coordinator import WateringCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    core_entry_id = entry.data[CONF_CORE_ENTRY_ID]

    if DOMAIN_CORE not in hass.data or core_entry_id not in hass.data[DOMAIN_CORE]:
        raise ConfigEntryNotReady("Tuya Home Core is not loaded yet.")

    coordinator = WateringCoordinator(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info(
        "Tuya Watering loaded: %d valve(s)",
        len(entry.options.get(CONF_VALVES, [])),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (valve added/removed)."""
    await hass.config_entries.async_reload(entry.entry_id)
