"""Valve control API — local tinytuya only."""

from __future__ import annotations

import logging
import time

from .const import (
    CONF_DEFAULT_DURATION,
    CONF_DEVICE_ID,
    CONF_DPS_DURATION,
    CONF_DPS_STOP,
    CONF_DPS_TRIGGER,
    CONF_GATEWAY_ID,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_KEY,
    CONF_SUB_CID,
    DEFAULT_DURATION,
    DPS_SET_DELAY,
    SOCKET_TIMEOUT,
    TUYA_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _local_open(valve: dict, seconds: int) -> bool:
    """
    Open valve via local tinytuya.
    Sets DPS duration first, waits briefly, then triggers.
    NEVER calls gw.status() — see CLAUDE.md.
    Returns True on success.
    """
    import tinytuya

    gw_id  = valve[CONF_GATEWAY_ID]
    gw_ip  = valve[CONF_GATEWAY_IP]
    gw_key = valve[CONF_GATEWAY_KEY]

    gw = tinytuya.Device(gw_id, gw_ip, gw_key, version=TUYA_VERSION)
    gw.set_socketTimeout(SOCKET_TIMEOUT)
    gw.set_socketPersistent(True)

    sub = tinytuya.Device(
        valve[CONF_DEVICE_ID], gw_ip, gw_key,
        version=TUYA_VERSION, cid=valve[CONF_SUB_CID], parent=gw,
    )
    sub.set_socketTimeout(SOCKET_TIMEOUT)

    dps_dur  = str(valve.get(CONF_DPS_DURATION, 104))
    dps_trig = str(valve.get(CONF_DPS_TRIGGER, 116))

    r1 = sub.set_multiple_values({dps_dur: seconds})
    # None = sent with no ACK (normal for battery ZigBee end devices); only dict with "Err" is a real failure
    if isinstance(r1, dict) and "Err" in r1:
        _LOGGER.warning("Local: DPS duration set failed: %s", r1)
        return False

    time.sleep(DPS_SET_DELAY)

    r2 = sub.set_multiple_values({dps_trig: True})
    # Same: None is acceptable; only explicit error fails
    if isinstance(r2, dict) and "Err" in r2:
        _LOGGER.warning("Local: DPS trigger failed: %s", r2)
        return False
    return True


def _local_close(valve: dict) -> bool:
    """
    Close valve via local tinytuya.
    Sends both stop DPS and trigger=False for reliability.
    NEVER calls gw.status() — see CLAUDE.md.
    """
    import tinytuya

    gw_id  = valve[CONF_GATEWAY_ID]
    gw_ip  = valve[CONF_GATEWAY_IP]
    gw_key = valve[CONF_GATEWAY_KEY]

    gw = tinytuya.Device(gw_id, gw_ip, gw_key, version=TUYA_VERSION)
    gw.set_socketTimeout(SOCKET_TIMEOUT)
    gw.set_socketPersistent(True)

    sub = tinytuya.Device(
        valve[CONF_DEVICE_ID], gw_ip, gw_key,
        version=TUYA_VERSION, cid=valve[CONF_SUB_CID], parent=gw,
    )
    sub.set_socketTimeout(SOCKET_TIMEOUT)

    dps_stop = str(valve.get(CONF_DPS_STOP, 1))
    dps_trig = str(valve.get(CONF_DPS_TRIGGER, 116))

    r = sub.set_multiple_values({dps_stop: False, dps_trig: False})
    return not (isinstance(r, dict) and "Err" in r)


class ValveAPI:
    """Local-only valve control for a single valve config."""

    def __init__(self, valve: dict) -> None:
        self._valve = valve

    def open(self, duration: int | None = None) -> bool:
        seconds = duration or self._valve.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION)
        name    = self._valve.get("name", self._valve[CONF_DEVICE_ID])

        try:
            ok = _local_open(self._valve, seconds)
            if ok:
                _LOGGER.debug("%s: opened locally (%ds)", name, seconds)
            else:
                _LOGGER.error("%s: local open failed", name)
            return ok
        except Exception as err:
            _LOGGER.error("%s: local open error: %s", name, err)
            return False

    def close(self) -> bool:
        name = self._valve.get("name", self._valve[CONF_DEVICE_ID])

        try:
            ok = _local_close(self._valve)
            if ok:
                _LOGGER.debug("%s: closed locally", name)
            else:
                _LOGGER.warning("%s: local close returned failure", name)
            return ok
        except Exception as err:
            _LOGGER.warning("%s: local close error: %s", name, err)
            return False
