"""Best-effort valve discovery via the official Tuya hub's tuya_sharing manager.

Cloud device-list APIs never expose a Zigbee sub-device's local routing id
(sub_cid / node_id) — it's a gateway-local concept, not a cloud one, regardless
of IoT Core Trial Edition status. tuya_sharing does expose it, because it's the
same SDK the official `tuya` hub integration already runs continuously (also
borrowed by tuya_cameras for SD status — see that repo's
coordinator.py::_fetch_sd_from_tuya_sharing for the same access pattern).

This module is purely additive: on any failure it returns [] and the config
flow falls back to today's manual-entry form unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN_CORE

_LOGGER = logging.getLogger(__name__)

# Category code both known GIEX GX-02BT valves report via tuya_sharing.
# Confirmed live 2026-08-04 against the running account. Broaden this if a
# different valve model surfaces a different category.
_VALVE_CATEGORY = "sfkzq"


def discover_valve_candidates(hass: HomeAssistant, core_entry_id: str) -> list[dict[str, Any]]:
    """Return valve-category Zigbee sub-devices visible to the linked Tuya hub.

    Each item: {"label": str, "device_id": str, "sub_cid": str, "name": str}.
    Returns [] if the hub isn't linked, isn't loaded, or anything else fails —
    never raises, so callers can use it unconditionally before showing a form.
    """
    try:
        core_data = hass.data.get(DOMAIN_CORE, {}).get(core_entry_id)
        if not core_data:
            _LOGGER.debug("Tuya valve discovery: no core data for core_entry_id=%s", core_entry_id)
            return []
        coordinator = core_data.get("coordinator")
        hub_entry_id = getattr(coordinator, "hub_entry_id", "") if coordinator else ""
        if not hub_entry_id:
            _LOGGER.debug("Tuya valve discovery: no linked hub_entry_id on core coordinator")
            return []

        hub_entry = hass.config_entries.async_get_entry(hub_entry_id)
        if not hub_entry:
            _LOGGER.debug("Tuya valve discovery: hub entry %s not found", hub_entry_id)
            return []

        runtime = getattr(hub_entry, "runtime_data", None)
        manager = getattr(runtime, "manager", None)
        device_map = getattr(manager, "device_map", None)
        if not device_map:
            _LOGGER.debug(
                "Tuya valve discovery: hub entry %s has no tuya_sharing manager/device_map yet "
                "(runtime_data=%s, manager=%s)", hub_entry_id, runtime is not None, manager is not None,
            )
            return []

        candidates: list[dict[str, Any]] = []
        for device in device_map.values():
            if getattr(device, "category", None) != _VALVE_CATEGORY:
                continue
            sub_cid = getattr(device, "node_id", None)
            device_id = getattr(device, "id", None)
            name = getattr(device, "name", "") or device_id
            if not sub_cid or not device_id:
                # Skip this one device, not the whole discovery — a valve
                # missing node_id shouldn't hide every other valve.
                continue
            candidates.append({
                "label": f"{name} ({device_id})",
                "device_id": device_id,
                "sub_cid": sub_cid,
                "name": name.strip(),
            })

        _LOGGER.debug("Tuya valve discovery: %d candidate(s) found via hub %s", len(candidates), hub_entry_id)
        return candidates
    except Exception as err:
        _LOGGER.debug("Tuya valve discovery failed, falling back to manual entry: %s", err)
        return []
