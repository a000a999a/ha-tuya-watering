"""Auto-write each valve's Run 1/Run 2 automation + duration/time helpers.

The "Tuya Watering Schedule" Lovelace card (see lovelace.py) only *discovers*
pre-existing automation/input_number/input_datetime entities matching a
valve's name — it never creates them. Before this module existed, a new
valve got a working switch but no schedule until someone hand-wrote an
automation and two helpers, copying the Terrasse/Keller pattern by hand
(exactly what never happened for the Garden valve).

This module writes those entities for real, using the same mechanism HA's
own config editor uses for automations.yaml (homeassistant.util.yaml
load_yaml/dump + atomic write, see homeassistant/components/config/view.py)
extended to input_datetime.yaml/input_number.yaml after those were split out
of configuration.yaml specifically so they'd be safe to mutate the same way
(see the repo README/CLAUDE.md for that one-time split). No HA restart is
needed — each domain's `reload` service picks the file change up live.

Idempotent by design: async_ensure_valve_schedule only creates whatever is
missing (checked by id/slug), so it's safe to call on every entry setup —
that's what makes a valve whose weather/threshold/storm options get filled
in later (e.g. Garden, configured after the fact) pick up its schedule on
the very next reload, with no separate backfill code path.

Two options saves in quick succession (e.g. notify target then schedule
defaults) each trigger their own entry reload, and __init__.py fires this
module's calls via hass.async_create_task without awaiting them — so two
reloads' worth of read-modify-write on the same 3 YAML files can genuinely
overlap. _LOCK serialises them, mirroring the mutation_lock HA's own config
editor uses around this exact pattern (homeassistant/components/config/
view.py, BaseEditConfigView) — without it, the second writer's save can
silently clobber fields the first writer had just added, an observed
failure mode (a helper created but its matching automation lost) during
this feature's own testing.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, load_yaml

from .const import (
    CONF_RAIN_THRESHOLD,
    CONF_STORM_CONDITIONS,
    CONF_VALVE_NAME,
    CONF_WEATHER_ENTITY,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_STORM_CONDITIONS,
)
from .lovelace import update_watering_view

_LOGGER = logging.getLogger(__name__)

# Serialises read-modify-write access to the 3 YAML files below across
# concurrent calls (e.g. two reloads fired close together) — see module
# docstring.
_LOCK = asyncio.Lock()

_AUTOMATIONS_FILE    = "automations.yaml"
_INPUT_DATETIME_FILE = "input_datetime.yaml"
_INPUT_NUMBER_FILE   = "input_number.yaml"

# Run label -> (default start time, default duration minutes). Placeholders
# only — the whole point of generating real helper entities (not baked-in
# values) is that the user adjusts these from the dashboard afterward,
# exactly like Terrasse/Keller work today.
_RUNS = [
    (1, "Run 1", "06:00:00"),
    (2, "Run 2", "18:00:00"),
]
_DEFAULT_DURATION_MIN = 2


def slugify(name: str) -> str:
    """Same slug rule lovelace.py uses for valve names, kept here as the
    single source of truth for entity ids this module generates."""
    return name.lower().replace(" ", "_")


def _load(hass: HomeAssistant, filename: str, empty):
    path = hass.config.path(filename)
    if not Path(path).is_file():
        return empty
    data = load_yaml(path)
    return data if data is not None else empty


def _save(hass: HomeAssistant, filename: str, data) -> None:
    path = hass.config.path(filename)
    write_utf8_file_atomic(path, dump(data))


def _build_automation(
    slug: str, valve_name: str, run_num: int, run_label: str,
    weather_entity: str, threshold: int, storm_conditions: list[str],
) -> dict:
    run_key = f"run{run_num}"
    duration_entity = f"input_number.watering_{slug}_{run_key}_duration"
    time_entity = f"input_datetime.watering_{slug}_{run_key}_time"

    rain_check = (
        f"{{% set f = forecast_data['{weather_entity}']['forecast'] %}}\n"
        f"{{% set rainy = {storm_conditions!r} %}}\n"
        "{% set ns = namespace(max_prob=0, any_rainy=false) %}\n"
        "{% for slot in f[:6] %}\n"
        "  {% set p = (slot.get('precipitation_probability') or 0) | int %}\n"
        "  {% if p > ns.max_prob %}{% set ns.max_prob = p %}{% endif %}\n"
        "  {% if slot.get('condition') in rainy %}{% set ns.any_rainy = true %}{% endif %}\n"
        "{% endfor %}\n"
        f"{{{{ not ns.any_rainy and ns.max_prob < {threshold} }}}}\n"
    )
    max_prob_expr = (
        f"{{% set f = forecast_data['{weather_entity}']['forecast'] %}}\n"
        "{% set ns = namespace(v=0) %}\n"
        "{% for slot in f[:6] %}{% set p = (slot.get('precipitation_probability') or 0) | int %}"
        "{% if p > ns.v %}{% set ns.v = p %}{% endif %}{% endfor %}\n"
        "{{ ns.v }}"
    )

    return {
        "id": f"watering_{slug}_{run_key}",
        "alias": f"Watering {valve_name} - {run_label}",
        "description": (
            f"Auto-generated by tuya_watering. Opens {valve_name} at the "
            f"configured {run_label} start time for the configured duration. "
            f"Skips if any of the next 6 hourly forecast slots has >= "
            f"{threshold}% rain probability or a stormy condition. Forecast "
            "is read fresh at trigger time."
        ),
        "triggers": [{"trigger": "time", "at": time_entity}],
        "conditions": [],
        "actions": [
            {
                "action": "weather.get_forecasts",
                "data": {"type": "hourly"},
                "target": {"entity_id": weather_entity},
                "response_variable": "forecast_data",
            },
            {
                "if": [{"condition": "template", "value_template": rain_check}],
                "then": [
                    {
                        "action": "tuya_watering.open_valve",
                        "data": {"duration": f"{{{{ (states('{duration_entity}') | float * 60) | int }}}}"},
                        "target": {"entity_id": f"switch.{slug}"},
                    },
                    {"delay": {"minutes": f"{{{{ states('{duration_entity}') | int }}}}"}},
                    {"action": "tuya_watering.close_valve", "target": {"entity_id": f"switch.{slug}"}},
                ],
                "else": [
                    {
                        "action": "tuya_watering.notify_skip",
                        "data": {
                            "valve": valve_name,
                            "run": run_label,
                            "time": "{{ now().strftime('%H:%M') }}",
                            "today_condition": f"{{{{ forecast_data['{weather_entity}']['forecast'][0].get('condition', '') }}}}",
                            "today_rain_pct": max_prob_expr,
                            "tomorrow_rain_pct": 0,
                        },
                    },
                    {
                        "action": "logbook.log",
                        "data": {
                            "name": f"Watering {valve_name} - {run_label}",
                            "message": "Watering skipped - rain probability too high or stormy conditions in next 6h.",
                        },
                    },
                ],
            },
        ],
        "mode": "single",
    }


async def async_ensure_valve_schedule(hass: HomeAssistant, entry: ConfigEntry, valve: dict) -> None:
    """Create whatever Run 1/Run 2 automation + helper entities are missing
    for this valve. Safe to call repeatedly — never duplicates or overwrites
    an existing entry."""
    weather_entity = entry.options.get(CONF_WEATHER_ENTITY, "").strip()
    if not weather_entity:
        _LOGGER.warning(
            "tuya_watering: skipping schedule generation for %s — no weather "
            "entity configured (Options -> Schedule Defaults)",
            valve.get(CONF_VALVE_NAME, "<unnamed valve>"),
        )
        return

    valve_name = valve[CONF_VALVE_NAME]
    slug = slugify(valve_name)
    threshold = int(entry.options.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))
    storm_conditions = list(entry.options.get(CONF_STORM_CONDITIONS, DEFAULT_STORM_CONDITIONS))

    async with _LOCK:
        automations = await hass.async_add_executor_job(_load, hass, _AUTOMATIONS_FILE, [])
        input_datetimes = await hass.async_add_executor_job(_load, hass, _INPUT_DATETIME_FILE, {})
        input_numbers = await hass.async_add_executor_job(_load, hass, _INPUT_NUMBER_FILE, {})

        existing_automation_ids = {a.get("id") for a in automations}
        changed_automations = changed_datetimes = changed_numbers = False

        for run_num, run_label, default_time in _RUNS:
            run_key = f"run{run_num}"
            automation_id = f"watering_{slug}_{run_key}"
            time_key = f"watering_{slug}_{run_key}_time"
            duration_key = f"watering_{slug}_{run_key}_duration"

            if automation_id not in existing_automation_ids:
                automations.append(_build_automation(
                    slug, valve_name, run_num, run_label,
                    weather_entity, threshold, storm_conditions,
                ))
                changed_automations = True
                _LOGGER.info("tuya_watering: generated automation.%s for %s", automation_id, valve_name)

            if time_key not in input_datetimes:
                input_datetimes[time_key] = {
                    "name": f"{valve_name} {run_label} Start Time",
                    "has_time": True,
                    "has_date": False,
                    "initial": default_time,
                }
                changed_datetimes = True

            if duration_key not in input_numbers:
                input_numbers[duration_key] = {
                    "name": f"{valve_name} {run_label} Duration",
                    "min": 1,
                    "max": 30,
                    "step": 1,
                    "unit_of_measurement": "min",
                    "icon": "mdi:timer",
                    "initial": _DEFAULT_DURATION_MIN,
                }
                changed_numbers = True

        if changed_automations:
            await hass.async_add_executor_job(_save, hass, _AUTOMATIONS_FILE, automations)
            await hass.services.async_call("automation", "reload", blocking=True)
        if changed_datetimes:
            await hass.async_add_executor_job(_save, hass, _INPUT_DATETIME_FILE, input_datetimes)
            await hass.services.async_call("input_datetime", "reload", blocking=True)
        if changed_numbers:
            await hass.async_add_executor_job(_save, hass, _INPUT_NUMBER_FILE, input_numbers)
            await hass.services.async_call("input_number", "reload", blocking=True)

        # Reload services above are blocking, so by this point the new entities
        # already exist in hass.states — safe to refresh the schedule card now.
        # Without this, a dashboard refresh fired concurrently with this
        # function (see __init__.py) could race ahead and build the card before
        # these entities exist, silently omitting them until the next reload.
        if changed_automations or changed_datetimes or changed_numbers:
            await update_watering_view(hass)


async def async_remove_valve_schedule(hass: HomeAssistant, valve_name: str) -> None:
    """Delete this valve's Run 1/Run 2 automation + helper entities, if any
    exist. Symmetric with async_ensure_valve_schedule — a switch that no
    longer exists shouldn't leave a scheduled automation pointing at a dead
    entity_id."""
    slug = slugify(valve_name)

    async with _LOCK:
        automations = await hass.async_add_executor_job(_load, hass, _AUTOMATIONS_FILE, [])
        input_datetimes = await hass.async_add_executor_job(_load, hass, _INPUT_DATETIME_FILE, {})
        input_numbers = await hass.async_add_executor_job(_load, hass, _INPUT_NUMBER_FILE, {})

        ids_to_remove = {f"watering_{slug}_run{n}" for n, _, _ in _RUNS}
        keys_to_remove = {f"watering_{slug}_run{n}_time" for n, _, _ in _RUNS}
        duration_keys_to_remove = {f"watering_{slug}_run{n}_duration" for n, _, _ in _RUNS}

        new_automations = [a for a in automations if a.get("id") not in ids_to_remove]
        removed_automations = len(new_automations) != len(automations)
        removed_datetimes = any(input_datetimes.pop(k, None) is not None for k in keys_to_remove)
        removed_numbers = any(input_numbers.pop(k, None) is not None for k in duration_keys_to_remove)

        if removed_automations:
            _LOGGER.info("tuya_watering: removed generated automation(s) for %s", valve_name)
            await hass.async_add_executor_job(_save, hass, _AUTOMATIONS_FILE, new_automations)
            await hass.services.async_call("automation", "reload", blocking=True)
        if removed_datetimes:
            await hass.async_add_executor_job(_save, hass, _INPUT_DATETIME_FILE, input_datetimes)
            await hass.services.async_call("input_datetime", "reload", blocking=True)
        if removed_numbers:
            await hass.async_add_executor_job(_save, hass, _INPUT_NUMBER_FILE, input_numbers)
            await hass.services.async_call("input_number", "reload", blocking=True)

        if removed_automations or removed_datetimes or removed_numbers:
            await update_watering_view(hass)
