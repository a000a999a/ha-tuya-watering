# CLAUDE.md — ha-tuya-watering

Extends /home/alex/ha-projects/CLAUDE.md. Read that file first.

## This Repo's Role
Valve control integration. Depends on tuya_home_core for Tuya credentials.
Exposes switch entities and open_valve/close_valve services.
Schedules and weather logic live in blueprints, NOT in this integration.

## Checklist Additions
- [ ] NEVER call gw.status() — see master CLAUDE.md CRITICAL section
- [ ] switch.py unique_id must use config_entry.entry_id + valve index, NOT IP or name
- [ ] Local gateway fields (ip, key, gw_id, sub_cid) are all optional — cloud fallback must work alone
- [ ] DPS codes must come from config entry (defaults: duration=104, trigger=116, stop=1)
- [ ] turn_on() must set duration DPS first, then trigger DPS, with 0.5s sleep between
- [ ] All local tinytuya calls must have socketTimeout(8) set
- [ ] State after turn_on/off is set optimistically — not polled from device
- [ ] services.yaml open_valve must accept optional duration param (overrides config default)

## Default DPS Codes (GIEX GX-02BT)
- DPS 104 → duration in seconds (set before triggering)
- DPS 116 → True = start watering
- DPS 1   → False = stop immediately
