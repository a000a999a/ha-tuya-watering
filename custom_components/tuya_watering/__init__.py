"""Tuya Watering — weather-aware valve control via Tuya/Zigbee."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CORE_ENTRY_ID,
    CONF_SKIP_RECIPIENT,
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SENDER,
    CONF_VALVES,
    DOMAIN,
    DOMAIN_CORE,
)
from .coordinator import WateringCoordinator
from .notify import Notifier

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch"]

_SMTP_KEYS = (CONF_SMTP_HOST, CONF_SMTP_PORT, CONF_SMTP_SENDER, CONF_SMTP_PASSWORD)

_NOTIFY_SKIP_SCHEMA = vol.Schema({
    vol.Required("valve"):              cv.string,
    vol.Required("run"):                cv.string,
    vol.Optional("time", default=""):   cv.string,
    vol.Optional("today_condition", default=""): cv.string,
    vol.Optional("today_rain_pct", default=0):   vol.Coerce(int),
    vol.Optional("tomorrow_rain_pct", default=0): vol.Coerce(int),
}, extra=vol.ALLOW_EXTRA)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    core_entry_id = entry.data[CONF_CORE_ENTRY_ID]

    if DOMAIN_CORE not in hass.data or core_entry_id not in hass.data[DOMAIN_CORE]:
        raise ConfigEntryNotReady("Tuya Home Core is not loaded yet.")

    coordinator = WateringCoordinator(hass)

    notifier: Notifier | None = None
    if all(entry.data.get(k) for k in _SMTP_KEYS):
        notifier = Notifier(entry.data)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "notifier":    notifier,
        "entry":       entry,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    if not hass.services.has_service(DOMAIN, "notify_skip"):
        async def _handle_notify_skip(call: ServiceCall) -> None:
            valve     = call.data["valve"]
            run       = call.data["run"]
            time_str  = call.data.get("time", "")
            condition = call.data.get("today_condition", "")
            today_pct = call.data.get("today_rain_pct", 0)
            tmrw_pct  = call.data.get("tomorrow_rain_pct", 0)

            subject = f"[Watering] {valve} {run} skipped – rain forecast"
            body = (
                f"<p><strong>{valve} {run}</strong> was skipped"
                + (f" at {time_str}" if time_str else "")
                + ".</p>"
                f"<p>Next 6h: {condition}, rain up to {today_pct}%</p>"
                f"<p>Trigger manually if needed: call "
                f"<code>tuya_watering.open_valve</code> on "
                f"<code>switch.{valve.lower()}</code>.</p>"
            )

            for entry_data in hass.data.get(DOMAIN, {}).values():
                notifier = entry_data.get("notifier")
                cfg_entry = entry_data.get("entry")
                if not notifier or not cfg_entry:
                    continue
                recipient = cfg_entry.options.get(CONF_SKIP_RECIPIENT, "").strip()
                if not recipient:
                    continue
                await hass.async_add_executor_job(
                    notifier.send, subject, body, [recipient]
                )

        hass.services.async_register(
            DOMAIN, "notify_skip", _handle_notify_skip, schema=_NOTIFY_SKIP_SCHEMA
        )

    _LOGGER.info(
        "Tuya Watering loaded: %d valve(s)%s",
        len(entry.options.get(CONF_VALVES, [])),
        ", notifier active" if notifier else "",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, "notify_skip")
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (valve added/removed or recipient updated)."""
    await hass.config_entries.async_reload(entry.entry_id)
