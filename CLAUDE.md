# CLAUDE.md — ha-tuya-watering

Extends /home/alex/Projects/CLAUDE.md. Read that file first.

## This Repo's Role
Valve control integration. Depends on tuya_home_core for Tuya credentials.
Exposes switch entities and open_valve/close_valve services.
The `blueprints/` weather-based automation is a template a user can import
by hand. As of v0.4.0, the integration itself can also auto-generate a
valve's Run 1/Run 2 schedule (automation + input_number/input_datetime
helpers) directly into automations.yaml/input_number.yaml/input_datetime.yaml
— see schedule_generator.py. Both paths produce structurally identical,
independent automations; neither depends on the other.

## Checklist Additions
- [ ] NEVER call gw.status() — see master CLAUDE.md CRITICAL section
- [ ] switch.py unique_id must use config_entry.entry_id + valve index, NOT IP or name
- [ ] Local gateway fields (ip, key, gw_id, sub_cid) are required — no cloud fallback (Tuya Cloud API cannot trigger DPS 116; returns error 2008)
- [ ] DPS codes must come from config entry (defaults: duration=104, trigger=116, stop=1)
- [ ] turn_on() must set duration DPS first, then trigger DPS, with 0.5s sleep between
- [ ] All local tinytuya calls must have socketTimeout(8) set
- [ ] State after turn_on/off is set optimistically — not polled from device
- [ ] services.yaml open_valve must accept optional duration param (overrides config default)
- [ ] `tuya_discovery.py::discover_valve_candidates()` must never raise — wrap in try/except and return `[]` on any failure, so Add/Edit Valve always fall back to manual entry
- [ ] Do NOT auto-fill `gateway_key`/`gateway_ip` from `tuya_sharing` — validated 2026-08-04 that Zigbee gateway devices don't expose `local_key` via that SDK path (only valve/sensor sub-devices do); only `device_id`/`sub_cid`/`name` are safe to auto-fill
- [ ] Edit Valve (`async_step_edit_valve_form`) must always show the valve's *current* values via `_valve_schema(defaults=...)` — the whole point of the step is visibility into what's configured, don't regress to a blank form
- [ ] Any options-flow step that calls `self.async_create_entry(data=...)` MUST spread `**self._entry.options` first (`{**self._entry.options, CONF_X: ...}`) — `data` *replaces* the entire options dict, it does not merge. `add_valve`/`edit_valve_form`/`remove_valve` got this wrong from the start (silently wiped `notify_entity` on every valve add/edit/remove, unnoticed until `weather_entity`/`rain_probability_threshold`/`storm_conditions` were added in v0.4.0 and a live test wiped Garden's settings). Fixed in v0.4.0 — don't reintroduce a bare `data={CONF_VALVES: ...}` in a new step.
- [ ] Any code that reads-modifies-writes `automations.yaml`/`input_number.yaml`/`input_datetime.yaml` (schedule_generator.py) MUST hold `schedule_generator._LOCK` for the whole read→mutate→save→reload sequence. Two options saves in quick succession (e.g. notify target then schedule defaults) each fire their own reload; without the lock, two concurrent writers can race and silently lose each other's changes — reproduced live in v0.4.0 testing (a helper entity was created but its matching automation was lost).

## Default DPS Codes (GIEX GX-02BT)
- DPS 104 → duration in seconds (set before triggering)
- DPS 116 → True = start watering
- DPS 1   → False = stop immediately
