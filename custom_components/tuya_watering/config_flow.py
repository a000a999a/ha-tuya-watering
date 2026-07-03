"""Config flow + options flow for Tuya Watering."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CORE_ENTRY_ID,
    CONF_DEFAULT_DURATION,
    CONF_DEVICE_ID,
    CONF_DPS_DURATION,
    CONF_DPS_STOP,
    CONF_DPS_TRIGGER,
    CONF_GATEWAY_ID,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_KEY,
    CONF_SKIP_RECIPIENT,
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SENDER,
    CONF_SUB_CID,
    CONF_VALVE_NAME,
    CONF_VALVES,
    DEFAULT_DURATION,
    DEFAULT_DPS_DURATION,
    DEFAULT_DPS_STOP,
    DEFAULT_DPS_TRIGGER,
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PORT,
    DOMAIN,
    DOMAIN_CORE,
)


def _smtp_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_SMTP_HOST,     default=d.get(CONF_SMTP_HOST, DEFAULT_SMTP_HOST)): str,
        vol.Required(CONF_SMTP_PORT,     default=d.get(CONF_SMTP_PORT, DEFAULT_SMTP_PORT)):
            selector.NumberSelector(selector.NumberSelectorConfig(
                min=1, max=65535, mode=selector.NumberSelectorMode.BOX
            )),
        vol.Required(CONF_SMTP_SENDER,   default=d.get(CONF_SMTP_SENDER, "")): str,
        vol.Required(CONF_SMTP_PASSWORD, default=d.get(CONF_SMTP_PASSWORD, "")):
            selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
    })


def _notifications_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Optional(CONF_SKIP_RECIPIENT, default=d.get(CONF_SKIP_RECIPIENT, "")):
            selector.TextSelector(selector.TextSelectorConfig(
                type=selector.TextSelectorType.EMAIL,
            )),
    })


def _valve_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_VALVE_NAME,       default=d.get(CONF_VALVE_NAME, "")): str,
        vol.Required(CONF_DEVICE_ID,        default=d.get(CONF_DEVICE_ID, "")): str,
        vol.Optional(CONF_GATEWAY_ID,       default=d.get(CONF_GATEWAY_ID, "")): str,
        vol.Optional(CONF_GATEWAY_IP,       default=d.get(CONF_GATEWAY_IP, "")): str,
        vol.Optional(CONF_GATEWAY_KEY,      default=d.get(CONF_GATEWAY_KEY, "")): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_SUB_CID,          default=d.get(CONF_SUB_CID, "")): str,
        vol.Optional(CONF_DEFAULT_DURATION, default=d.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=10, max=3600, unit_of_measurement="s")),
        vol.Optional(CONF_DPS_DURATION,     default=d.get(CONF_DPS_DURATION, DEFAULT_DPS_DURATION)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=999, mode=selector.NumberSelectorMode.BOX)),
        vol.Optional(CONF_DPS_TRIGGER,      default=d.get(CONF_DPS_TRIGGER, DEFAULT_DPS_TRIGGER)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=999, mode=selector.NumberSelectorMode.BOX)),
        vol.Optional(CONF_DPS_STOP,         default=d.get(CONF_DPS_STOP, DEFAULT_DPS_STOP)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=999, mode=selector.NumberSelectorMode.BOX)),
    })


def _clean_valve(raw: dict) -> dict:
    """Normalise selector number outputs (float) to int, strip empty strings."""
    out = {}
    for k, v in raw.items():
        if isinstance(v, float):
            out[k] = int(v)
        elif isinstance(v, str) and v.strip() == "":
            out[k] = ""
        else:
            out[k] = v
    return out


class TuyaWateringConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step flow: pick core entry → add first valve."""

    VERSION = 1

    def __init__(self) -> None:
        self._core_entry_id: str = ""

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        core_entries = self.hass.config_entries.async_entries(DOMAIN_CORE)
        if not core_entries:
            return self.async_abort(reason="no_core_entry")

        errors: dict[str, str] = {}

        if user_input is not None:
            self._core_entry_id = user_input[CONF_CORE_ENTRY_ID]
            return await self.async_step_add_valve()

        # Auto-select if only one core entry exists
        if len(core_entries) == 1:
            self._core_entry_id = core_entries[0].entry_id
            return await self.async_step_add_valve()

        schema = vol.Schema({
            vol.Required(CONF_CORE_ENTRY_ID): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=e.entry_id, label=e.title)
                        for e in core_entries
                    ]
                )
            )
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_add_valve(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            valve = _clean_valve(user_input)
            if not valve.get(CONF_VALVE_NAME) or not valve.get(CONF_DEVICE_ID):
                errors["base"] = "valve_fields_required"
            else:
                return self.async_create_entry(
                    title=valve[CONF_VALVE_NAME],
                    data={CONF_CORE_ENTRY_ID: self._core_entry_id},
                    options={CONF_VALVES: [valve]},
                )

        return self.async_show_form(
            step_id="add_valve",
            data_schema=_valve_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TuyaWateringOptionsFlow(config_entry)


class TuyaWateringOptionsFlow(OptionsFlow):
    """Options flow: add/remove valves, configure SMTP and notification recipient."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry                 = config_entry
        self._valves: list[dict]    = list(config_entry.options.get(CONF_VALVES, []))
        self._remove_index: int | None = None

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_valve", "remove_valve", "edit_smtp", "edit_notifications"],
        )

    async def async_step_edit_smtp(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            new_data = {
                **self._entry.data,
                CONF_SMTP_HOST:     user_input[CONF_SMTP_HOST],
                CONF_SMTP_PORT:     int(user_input[CONF_SMTP_PORT]),
                CONF_SMTP_SENDER:   user_input[CONF_SMTP_SENDER],
                CONF_SMTP_PASSWORD: user_input[CONF_SMTP_PASSWORD],
            }
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(data={**self._entry.options, CONF_VALVES: self._valves})

        defaults = {k: self._entry.data.get(k) for k in (
            CONF_SMTP_HOST, CONF_SMTP_PORT, CONF_SMTP_SENDER, CONF_SMTP_PASSWORD
        )}
        return self.async_show_form(step_id="edit_smtp", data_schema=_smtp_schema(defaults))

    async def async_step_edit_notifications(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={
                **self._entry.options,
                CONF_VALVES:          self._valves,
                CONF_SKIP_RECIPIENT:  user_input.get(CONF_SKIP_RECIPIENT, "").strip(),
            })

        defaults = {CONF_SKIP_RECIPIENT: self._entry.options.get(CONF_SKIP_RECIPIENT, "")}
        return self.async_show_form(
            step_id="edit_notifications",
            data_schema=_notifications_schema(defaults),
        )

    async def async_step_add_valve(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            valve = _clean_valve(user_input)
            if not valve.get(CONF_VALVE_NAME) or not valve.get(CONF_DEVICE_ID):
                errors["base"] = "valve_fields_required"
            else:
                self._valves.append(valve)
                return self.async_create_entry(data={CONF_VALVES: self._valves})

        return self.async_show_form(
            step_id="add_valve",
            data_schema=_valve_schema(),
            errors=errors,
        )

    async def async_step_remove_valve(self, user_input: dict | None = None) -> ConfigFlowResult:
        if not self._valves:
            return self.async_abort(reason="no_valves")

        errors: dict[str, str] = {}

        if user_input is not None:
            idx = int(user_input["valve_index"])
            self._valves.pop(idx)
            return self.async_create_entry(data={CONF_VALVES: self._valves})

        options = [
            selector.SelectOptionDict(value=str(i), label=v[CONF_VALVE_NAME])
            for i, v in enumerate(self._valves)
        ]
        schema = vol.Schema({
            vol.Required("valve_index"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options)
            )
        })
        return self.async_show_form(
            step_id="remove_valve", data_schema=schema, errors=errors
        )
