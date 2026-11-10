"""UI setup, configuration and API-key replacement."""

import re
from datetime import UTC, datetime, timedelta

import probatio
from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import AuthError, NedClient, NedError, RateLimitError
from .const import DEFAULT_INTERVAL, DEFAULT_PROVINCE, DOMAIN, INTERVALS, NAME, PROVINCES

TOKEN = "api_key"


def schema(values: dict, *, token: bool = False, options: bool = False) -> probatio.Schema:
    fields = {}
    if token:
        fields[probatio.Required(TOKEN)] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    if options:
        fields.update(
            {
                probatio.Required(
                    "province", default=values.get("province", DEFAULT_PROVINCE)
                ): probatio.In(PROVINCES),
                probatio.Required(
                    "interval", default=values.get("interval", DEFAULT_INTERVAL)
                ): probatio.In(INTERVALS),
            }
        )
    return probatio.Schema(fields)


class NedConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, token: str) -> dict:
        if not re.fullmatch(r"[!-~]+", token):
            return {"base": "invalid_auth"}
        client = NedClient(async_get_clientsession(self.hass), token)
        today = datetime.now(UTC).date()
        try:
            await client.fetch(
                points=(0,),
                types=(2,),
                activity=1,
                classification=2,
                granularity=5,
                start=today - timedelta(days=1),
                end=today,
            )
        except AuthError:
            return {"base": "invalid_auth"}
        except RateLimitError:
            return {"base": "rate_limit"}
        except NedError:
            return {"base": "cannot_connect"}
        return {}

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            token = user_input[TOKEN].strip()
            errors = await self._validate(token) if token else {"base": "invalid_auth"}
            if not errors:
                return self.async_create_entry(
                    title=NAME,
                    data={TOKEN: token},
                    options={key: user_input[key] for key in ("province", "interval")},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=schema(user_input or {}, token=True, options=True),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._replace_key("reauth_confirm", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._replace_key("reconfigure", user_input)

    async def _replace_key(self, step, user_input):
        errors = {}
        if user_input is not None:
            token = user_input[TOKEN].strip()
            errors = await self._validate(token) if token else {"base": "invalid_auth"}
            if not errors:
                entry = (
                    self._get_reauth_entry()
                    if step == "reauth_confirm"
                    else self._get_reconfigure_entry()
                )
                return self.async_update_reload_and_abort(entry, data_updates={TOKEN: token})
        return self.async_show_form(step_id=step, data_schema=schema({}, token=True), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NedOptionsFlow()


class NedOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=schema(self.config_entry.options, options=True)
        )
