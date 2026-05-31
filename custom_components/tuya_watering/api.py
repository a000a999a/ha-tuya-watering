"""Valve control API — local tinytuya primary, Tuya Cloud fallback."""

from __future__ import annotations

import logging
import time
from typing import Any

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


def _has_local_config(valve: dict) -> bool:
    return bool(
        valve.get(CONF_GATEWAY_IP)
        and valve.get(CONF_GATEWAY_KEY)
        and valve.get(CONF_GATEWAY_ID)
        and valve.get(CONF_SUB_CID)
    )


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
    if r1 is None or "Err" in str(r1):
        _LOGGER.warning("Local: DPS duration set failed: %s", r1)
        return False

    time.sleep(DPS_SET_DELAY)

    r2 = sub.set_multiple_values({dps_trig: True})
    ok = r2 is not None and isinstance(r2, dict) and "dps" in r2
    if not ok:
        _LOGGER.warning("Local: DPS trigger failed: %s", r2)
    return ok


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
    return r is not None and "Err" not in str(r)


def _cloud_open(tuya_client: Any, device_id: str, seconds: int) -> bool:
    """Cloud fallback: open valve via Tuya IoT Platform."""
    try:
        resp = tuya_client.cloudrequest(
            f"/v1.0/iot-03/devices/{device_id}/commands",
            action="POST",
            post={"commands": [
                {"code": "switch",    "value": True},
                {"code": "countdown", "value": seconds},
            ]},
        )
        return bool(resp and resp.get("success"))
    except Exception as err:
        _LOGGER.warning("Cloud open failed: %s", err)
        return False


def _cloud_close(tuya_client: Any, device_id: str) -> bool:
    """Cloud fallback: close valve via Tuya IoT Platform."""
    try:
        resp = tuya_client.cloudrequest(
            f"/v1.0/iot-03/devices/{device_id}/commands",
            action="POST",
            post={"commands": [
                {"code": "switch",    "value": False},
                {"code": "countdown", "value": 0},
            ]},
        )
        return bool(resp and resp.get("success"))
    except Exception as err:
        _LOGGER.warning("Cloud close failed: %s", err)
        return False


class ValveAPI:
    """Orchestrates local + cloud valve control for a single valve config."""

    def __init__(self, valve: dict, tuya_client: Any) -> None:
        self._valve  = valve
        self._client = tuya_client

    def open(self, duration: int | None = None) -> bool:
        seconds  = duration or self._valve.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION)
        dev_id   = self._valve[CONF_DEVICE_ID]
        name     = self._valve.get("name", dev_id)

        if _has_local_config(self._valve):
            try:
                ok = _local_open(self._valve, seconds)
                if ok:
                    _LOGGER.debug("%s: opened locally (%ds)", name, seconds)
                    return True
                _LOGGER.warning("%s: local open failed, trying cloud", name)
            except Exception as err:
                _LOGGER.warning("%s: local open error: %s — trying cloud", name, err)

        ok = _cloud_open(self._client, dev_id, seconds)
        _LOGGER.debug("%s: cloud open %s (%ds)", name, "ok" if ok else "FAILED", seconds)
        return ok

    def close(self) -> bool:
        dev_id = self._valve[CONF_DEVICE_ID]
        name   = self._valve.get("name", dev_id)

        if _has_local_config(self._valve):
            try:
                ok = _local_close(self._valve)
                if ok:
                    _LOGGER.debug("%s: closed locally", name)
            except Exception as err:
                _LOGGER.warning("%s: local close error: %s", name, err)

        # Always also send cloud close as a safety net
        _cloud_close(self._client, dev_id)
        _LOGGER.debug("%s: cloud close sent", name)
        return True
