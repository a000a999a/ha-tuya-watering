"""Valve switch entities for Tuya Watering."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ValveAPI
from .const import (
    CONF_DEVICE_ID,
    CONF_VALVES,
    CONF_VALVE_NAME,
    DOMAIN,
)
from .coordinator import WateringCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data        = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    valves      = entry.options.get(CONF_VALVES, [])

    entities = [
        ValveSwitch(entry, valve, idx, coordinator)
        for idx, valve in enumerate(valves)
    ]
    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "open_valve",
        {vol.Optional("duration"): vol.Coerce(int)},
        "turn_on",
    )
    platform.async_register_entity_service("close_valve", {}, "turn_off")


class ValveSwitch(SwitchEntity):
    """A single watering valve exposed as a HA switch."""

    _attr_should_poll    = False
    _attr_device_class   = SwitchDeviceClass.OUTLET
    _attr_has_entity_name = True
    _attr_name           = None   # uses device name as entity name

    def __init__(
        self,
        entry: ConfigEntry,
        valve: dict,
        index: int,
        coordinator: WateringCoordinator,
    ) -> None:
        self._valve       = valve
        self._coordinator = coordinator
        self._api         = ValveAPI(valve)
        self._attr_unique_id = f"{entry.entry_id}_{index}"
        self._entry_id       = entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._valve[CONF_DEVICE_ID])},
            name=self._valve[CONF_VALVE_NAME],
            manufacturer="Tuya",
            model="Zigbee Water Timer",
        )

    @property
    def is_on(self) -> bool:
        return self._coordinator.get_state(self._valve[CONF_DEVICE_ID])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "device_id":        self._valve[CONF_DEVICE_ID],
            "default_duration": self._valve.get("default_duration"),
            "local_control":    bool(self._valve.get("gateway_ip")),
        }

    def turn_on(self, **kwargs: Any) -> None:
        duration = kwargs.get("duration")
        ok = self._api.open(duration)
        if ok:
            self._coordinator.set_state(self._valve[CONF_DEVICE_ID], True)
            self.schedule_update_ha_state()
        else:
            _LOGGER.error("Failed to open valve %s", self._valve[CONF_VALVE_NAME])

    def turn_off(self, **kwargs: Any) -> None:
        self._api.close()
        self._coordinator.set_state(self._valve[CONF_DEVICE_ID], False)
        self.schedule_update_ha_state()
