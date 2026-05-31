"""State coordinator for Tuya Watering — tracks optimistic valve states."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class WateringCoordinator:
    """
    Lightweight in-memory store for last-known valve states.
    No polling — valves do not reliably report state back over Zigbee.
    State is set optimistically after each open/close command.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._states: dict[str, bool] = {}   # device_id → is_open

    def set_state(self, device_id: str, is_open: bool) -> None:
        self._states[device_id] = is_open

    def get_state(self, device_id: str) -> bool:
        return self._states.get(device_id, False)
