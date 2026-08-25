"""Auto-generate/self-heal a dedicated 'Tuya Watering' sidebar dashboard.

Mirrors the pattern used by ha-tuya-cameras's _update_lovelace_views (patch
raw storage config in-place, idempotent, purely additive), but targets its
own dedicated dashboard rather than the user's Overview — so it never
touches anything else on their Home view, works identically whether they
have one existing card or fifty, and shows up as its own entry in the
sidebar the way Map or Energy do.

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

Registering a brand-new dashboard (as opposed to patching an already-loaded
one) needs a Home Assistant restart before it appears in the sidebar — the
dashboard registry is only read at startup. This only affects the very
first setup; once registered, card content updates apply live like normal.
"""

from __future__ import annotations

import logging
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONF_VALVES, DOMAIN

_LOGGER = logging.getLogger(__name__)

_DASHBOARD_URL_PATH = "tuya-watering"
_DASHBOARD_TITLE    = "Tuya Watering"
_DASHBOARD_ICON     = "mdi:sprinkler-variant"
_VIEW_PATH          = "watering"

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


def _build_cards(hass: HomeAssistant) -> list[dict] | None:
    """Build the card list for the current valves, or None if there are no
    valves at all yet (nothing to show)."""
    slugs = _valve_slugs(hass)
    if not slugs:
        return None

    toggle_entities = [f"switch.{slug}" for slug in slugs]
    cards = [{
        "type": "entities",
        "title": _TOGGLE_CARD_TITLE,
        "entities": toggle_entities,
    }]

    schedule_entities: list[str] = []
    for slug in slugs:
        schedule_entities.extend(_schedule_entities_for_slug(hass, slug))

    if schedule_entities:
        cards.append({
            "type": "entities",
            "title": _SCHEDULE_CARD_TITLE,
            "state_color": False,
            "show_header_toggle": False,
            "entities": [{"entity": eid} for eid in schedule_entities],
        })

    return cards


async def _register_dashboard_if_missing(hass: HomeAssistant) -> bool:
    """Add our dashboard to the dashboards registry + create its initial
    storage file, if it isn't there yet. Returns True if it just registered
    (meaning a restart is needed before it shows up in the sidebar) — False
    if it already existed (nothing to do here).

    Writes storage directly via Store rather than any in-memory lovelace API
    — a freshly-registered dashboard's collection entry isn't picked up by
    the running LovelaceManager until Home Assistant restarts anyway,
    same as any other collection-backed registry.
    """
    dashboards_store = Store(hass, 1, "lovelace_dashboards")
    data = await dashboards_store.async_load() or {"items": []}
    items = data.setdefault("items", [])

    if any(item.get("url_path") == _DASHBOARD_URL_PATH for item in items):
        return False

    items.append({
        "id": _DASHBOARD_URL_PATH,
        "icon": _DASHBOARD_ICON,
        "title": _DASHBOARD_TITLE,
        "url_path": _DASHBOARD_URL_PATH,
        "mode": "storage",
        "show_in_sidebar": True,
        "require_admin": False,
    })
    await dashboards_store.async_save(data)

    cards = _build_cards(hass) or []
    view_store = Store(hass, 1, f"lovelace.{_DASHBOARD_URL_PATH}")
    await view_store.async_save({
        "config": {
            "title": _DASHBOARD_TITLE,
            "views": [{
                "title": _DASHBOARD_TITLE,
                "path": _VIEW_PATH,
                "icon": _DASHBOARD_ICON,
                "cards": cards,
            }],
        }
    })

    _LOGGER.info(
        "Tuya Watering: registered new '%s' sidebar dashboard — restart Home "
        "Assistant once for it to appear", _DASHBOARD_TITLE
    )
    return True


async def update_watering_view(hass: HomeAssistant) -> None:
    """Create/self-heal the dedicated Tuya Watering dashboard. Purely
    additive and idempotent — never touches any other dashboard or view,
    never raises (logs and returns on any failure so it can never block
    integration setup).
    """
    try:
        if not _valve_slugs(hass):
            return

        just_registered = await _register_dashboard_if_missing(hass)
        if just_registered:
            # Initial content already written above; nothing more to do
            # until the dashboard is actually loaded post-restart.
            return

        lovelace_obj = hass.data.get("lovelace")
        if not lovelace_obj:
            _LOGGER.debug("Lovelace update: no lovelace data in hass.data yet")
            return

        if hasattr(lovelace_obj, "dashboards"):
            dashboard = lovelace_obj.dashboards.get(_DASHBOARD_URL_PATH)
        elif isinstance(lovelace_obj, dict):
            dashboard = lovelace_obj.get("dashboards", {}).get(_DASHBOARD_URL_PATH)
        else:
            dashboard = None

        if not dashboard or not hasattr(dashboard, "async_load"):
            _LOGGER.debug(
                "Lovelace update: '%s' dashboard registered but not loaded yet "
                "(needs a restart)", _DASHBOARD_URL_PATH
            )
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
        view = next((v for v in views if v.get("path") == _VIEW_PATH), None)
        if view is None:
            view = {"title": _DASHBOARD_TITLE, "path": _VIEW_PATH, "icon": _DASHBOARD_ICON, "cards": []}
            views.append(view)
        cards = view.setdefault("cards", [])

        new_cards = _build_cards(hass) or []
        if cards != new_cards:
            view["cards"] = new_cards
            await dashboard.async_save(config)
            _LOGGER.info("Tuya Watering dashboard updated (%d card(s))", len(new_cards))
        else:
            _LOGGER.debug("Lovelace update: no changes needed")

    except Exception as err:  # noqa: BLE001 — never let a dashboard patch break setup
        _LOGGER.error("Tuya Watering dashboard update failed: %s", err)
