"""Auto-generate/self-heal the 'Tuya Watering' dashboard cards.

Mirrors the pattern used by ha-tuya-cameras's _update_lovelace_views: reads
the Overview ("lovelace") dashboard's raw storage config, patches it
in-place by title (idempotent — safe to call repeatedly, never touches
unrelated cards), and only writes back if something actually changed.

Two cards, matching what a hand-built dashboard for this integration looks
like in production:

- "Tuya Watering": one switch per valve. Fully known to this integration —
  every valve it manages has a `switch.<slug>` entity.
- "Tuya Watering Schedule": any automation / input_number / input_datetime
  entity whose object_id contains a valve's slug as a whole underscore-
  delimited word. This integration does NOT create those entities itself
  (they come from hand-written automations, or from importing the repo's
  blueprints) — this is a best-effort discovery pass over whatever already
  exists, per valve. A valve with none yet (e.g. freshly added, no schedule
  configured) simply doesn't contribute rows; the whole card is omitted if
  no valve has anything to show yet.
"""

from __future__ import annotations

import logging
import re

from homeassistant.core import HomeAssistant

from .const import CONF_VALVES, DOMAIN

_LOGGER = logging.getLogger(__name__)

_TOGGLE_CARD_TITLE   = "Tuya Watering"
_SCHEDULE_CARD_TITLE = "Tuya Watering Schedule"

_SCHEDULE_DOMAINS = ("automation", "input_number", "input_datetime")


def _valve_slugs(hass: HomeAssistant) -> list[str]:
    """Return valve slugs (switch.<slug>) for every loaded entry, in a stable order."""
    slugs: list[str] = []
    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        entry = data.get("entry")
        if not entry:
            continue
        for valve in entry.options.get(CONF_VALVES, []):
            name = valve.get("name", "")
            if name:
                slugs.append(name.lower().replace(" ", "_"))
    return slugs


_RUN_NUMBER_RE = re.compile(r"run_?0*(\d+)")
_DOMAIN_ORDER = {"automation": 0, "input_number": 1, "input_datetime": 2}


def _schedule_sort_key(entity_id: str) -> tuple[int, int]:
    """Group by run number (run_1, run1, ... — no match sorts last), then by
    domain in automation → duration → time order, matching how a hand-built
    card naturally reads: each run's controls together, in a sensible order.
    """
    domain, object_id = entity_id.split(".", 1)
    run_match = _RUN_NUMBER_RE.search(object_id)
    run_num = int(run_match.group(1)) if run_match else 999
    return (run_num, _DOMAIN_ORDER.get(domain, 99))


def _schedule_entities_for_slug(hass: HomeAssistant, slug: str) -> list[str]:
    """Best-effort: any automation/input_number/input_datetime entity that
    mentions this valve's slug as a whole word. Sorted so each run's
    automation/duration/time land together, in run order.
    """
    pattern = re.compile(rf"(^|_){re.escape(slug)}(_|$)")
    matches = [
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.split(".", 1)[0] in _SCHEDULE_DOMAINS
        and pattern.search(state.entity_id.split(".", 1)[1])
    ]
    return sorted(matches, key=_schedule_sort_key)


async def update_watering_view(hass: HomeAssistant) -> None:
    """Patch the 'Tuya Watering' / 'Tuya Watering Schedule' cards into the
    default_view of the Overview dashboard. Purely additive and idempotent —
    never touches any other card, never raises (logs and returns on any
    failure so it can never block integration setup).
    """
    try:
        slugs = _valve_slugs(hass)
        if not slugs:
            return

        toggle_entities = [f"switch.{slug}" for slug in slugs]

        schedule_entities: list[str] = []
        for slug in slugs:
            schedule_entities.extend(_schedule_entities_for_slug(hass, slug))

        lovelace_obj = hass.data.get("lovelace")
        if not lovelace_obj:
            _LOGGER.debug("Lovelace update: no lovelace data in hass.data yet")
            return

        if hasattr(lovelace_obj, "dashboards"):
            dashboard = lovelace_obj.dashboards.get("lovelace") or lovelace_obj.dashboards.get("")
        elif isinstance(lovelace_obj, dict):
            dashboard = lovelace_obj.get("dashboards", {}).get("lovelace")
        else:
            dashboard = None

        if not dashboard or not hasattr(dashboard, "async_load"):
            _LOGGER.debug("Lovelace update: Overview dashboard not accessible yet")
            return

        config_obj = await dashboard.async_load(force=True)
        if isinstance(config_obj, dict):
            config = config_obj
        elif hasattr(config_obj, "config") and isinstance(getattr(config_obj, "config", None), dict):
            config = config_obj.config
        elif hasattr(config_obj, "data") and isinstance(getattr(config_obj, "data", None), dict):
            config = config_obj.data
        else:
            _LOGGER.debug("Lovelace: cannot extract raw config from %s — skipping", type(config_obj).__name__)
            return

        views = config.setdefault("views", [])
        view = next((v for v in views if v.get("path") == "default_view"), None)
        if view is None:
            if not views:
                view = {"title": "Home", "path": "default_view", "cards": []}
                views.append(view)
            else:
                view = views[0]
        cards = view.setdefault("cards", [])

        changed = False

        toggle_card = next((c for c in cards if c.get("title") == _TOGGLE_CARD_TITLE), None)
        if toggle_card is None:
            cards.append({
                "type": "entities",
                "title": _TOGGLE_CARD_TITLE,
                "entities": toggle_entities,
            })
            changed = True
            _LOGGER.info("Lovelace: created '%s' card (%d valve(s))", _TOGGLE_CARD_TITLE, len(toggle_entities))
        elif toggle_card.get("entities") != toggle_entities:
            toggle_card["entities"] = toggle_entities
            changed = True
            _LOGGER.info("Lovelace: updated '%s' card (%d valve(s))", _TOGGLE_CARD_TITLE, len(toggle_entities))

        schedule_card = next((c for c in cards if c.get("title") == _SCHEDULE_CARD_TITLE), None)
        schedule_entity_dicts = [{"entity": eid} for eid in schedule_entities]
        if schedule_entities:
            if schedule_card is None:
                cards.append({
                    "type": "entities",
                    "title": _SCHEDULE_CARD_TITLE,
                    "state_color": False,
                    "show_header_toggle": False,
                    "entities": schedule_entity_dicts,
                })
                changed = True
                _LOGGER.info("Lovelace: created '%s' card (%d entities)", _SCHEDULE_CARD_TITLE, len(schedule_entities))
            elif [e["entity"] for e in schedule_card.get("entities", [])] != schedule_entities:
                schedule_card["entities"] = schedule_entity_dicts
                changed = True
                _LOGGER.info("Lovelace: updated '%s' card (%d entities)", _SCHEDULE_CARD_TITLE, len(schedule_entities))
        elif schedule_card is not None:
            # No schedule entities exist anywhere anymore — leave the card in
            # place rather than deleting it; it may just mean nothing has
            # settled yet after a fresh valve add. Never destructive here.
            pass

        if changed:
            await dashboard.async_save(config)
            _LOGGER.info("Tuya Watering dashboard cards updated")
        else:
            _LOGGER.debug("Lovelace update: no changes needed")

    except Exception as err:  # noqa: BLE001 — never let a dashboard patch break setup
        _LOGGER.error("Tuya Watering dashboard update failed: %s", err)
