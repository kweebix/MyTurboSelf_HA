"""Config flow for the MyTurboSelf integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    MyTurboSelfApiError,
    MyTurboSelfAuthError,
    TurboSelfPortalClient,
)
from .const import (
    CONF_MANUAL_MEAL_PRICE,
    CONF_SCHOOL_ZONE,
    CONF_SKIP_HOLIDAYS,
    CONF_SKIP_VACATION,
    DEFAULT_MANUAL_MEAL_PRICE,
    DEFAULT_WEEKDAY_MEALS,
    DOMAIN,
    MEAL_DAY_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, str]:
    """Validate the user input allows us to connect."""

    client = TurboSelfPortalClient(data[CONF_USERNAME], data[CONF_PASSWORD])

    try:
        snapshot = await client.async_fetch_snapshot()
    except MyTurboSelfAuthError as err:
        raise InvalidAuth from err
    except MyTurboSelfApiError as err:
        raise CannotConnect from err

    return {
        "title": _build_title(snapshot.user_data, data[CONF_USERNAME]),
        "unique_id": data[CONF_USERNAME].strip().lower(),
    }


def _build_title(user_data: dict[str, str], username: str) -> str:
    """Build a title from TurboSelf account data."""

    first_name = None
    last_name = None

    for key, value in user_data.items():
        lowered = key.lower()
        if "prenom" in lowered and not first_name:
            first_name = value
        if lowered.startswith("nom") and not last_name:
            last_name = value

    full_name = " ".join(part for part in [first_name, last_name] if part)
    if full_name:
        return full_name

    return username.strip()


class MyTurboSelfConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyTurboSelf."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._setup_data: dict[str, Any] = {}
        self._setup_info: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "MyTurboSelfOptionsFlow":
        """Return the options flow handler."""

        return MyTurboSelfOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}

        if user_input is not None:
            self._setup_data = {
                CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                self._setup_info = await validate_input(self.hass, self._setup_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(self._setup_info["unique_id"])
                self._abort_if_unique_id_configured()
                return await self.async_step_setup_schedule()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_setup_schedule(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the schedule setup step."""

        if user_input is not None:
            options = {
                CONF_MANUAL_MEAL_PRICE: float(user_input[CONF_MANUAL_MEAL_PRICE]),
                CONF_SKIP_HOLIDAYS: bool(user_input[CONF_SKIP_HOLIDAYS]),
                CONF_SKIP_VACATION: bool(user_input[CONF_SKIP_VACATION]),
                CONF_SCHOOL_ZONE: str(user_input[CONF_SCHOOL_ZONE]),
                **{
                    key: user_input[key]
                    for key in MEAL_DAY_OPTIONS
                },
            }
            return self.async_create_entry(
                title=self._setup_info["title"],
                data=self._setup_data,
                options=options,
            )

        data_schema: dict[Any, Any] = {
            vol.Required(
                CONF_MANUAL_MEAL_PRICE,
                default=float(DEFAULT_MANUAL_MEAL_PRICE),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SKIP_HOLIDAYS,
                default=True,
            ): bool,
            vol.Required(
                CONF_SKIP_VACATION,
                default=True,
            ): bool,
            vol.Required(
                CONF_SCHOOL_ZONE,
                default="C",
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "A", "label": "Zone A"},
                        {"value": "B", "label": "Zone B"},
                        {"value": "C", "label": "Zone C"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="school_zone",
                )
            ),
        }

        meal_selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "breakfast", "label": "breakfast"},
                    {"value": "lunch", "label": "lunch"},
                    {"value": "dinner", "label": "dinner"},
                ],
                mode=SelectSelectorMode.LIST,
                multiple=True,
                translation_key="meal_types",
            )
        )

        for key in MEAL_DAY_OPTIONS:
            data_schema[
                vol.Optional(
                    key,
                    default=DEFAULT_WEEKDAY_MEALS[key],
                )
            ] = meal_selector

        return self.async_show_form(
            step_id="setup_schedule",
            data_schema=vol.Schema(data_schema),
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Handle reauthentication."""

        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Prompt for a new password."""

        errors: dict[str, str] = {}

        if user_input is not None and self._reauth_entry is not None:
            data = {
                CONF_USERNAME: self._reauth_entry.data[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }

            try:
                await validate_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data=data,
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class MyTurboSelfOptionsFlow(config_entries.OptionsFlow):
    """Handle MyTurboSelf options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the config entry."""

        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage the integration options."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_MANUAL_MEAL_PRICE: float(user_input[CONF_MANUAL_MEAL_PRICE]),
                    CONF_SKIP_HOLIDAYS: bool(user_input[CONF_SKIP_HOLIDAYS]),
                    CONF_SKIP_VACATION: bool(user_input[CONF_SKIP_VACATION]),
                    CONF_SCHOOL_ZONE: str(user_input[CONF_SCHOOL_ZONE]),
                    **{
                        key: user_input[key]
                        for key in MEAL_DAY_OPTIONS
                    },
                },
            )

        options = self._config_entry.options
        data_schema: dict[Any, Any] = {
            vol.Required(
                CONF_MANUAL_MEAL_PRICE,
                default=float(
                    options.get(
                        CONF_MANUAL_MEAL_PRICE,
                        DEFAULT_MANUAL_MEAL_PRICE,
                    )
                ),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SKIP_HOLIDAYS,
                default=options.get(CONF_SKIP_HOLIDAYS, True),
            ): bool,
            vol.Required(
                CONF_SKIP_VACATION,
                default=options.get(CONF_SKIP_VACATION, True),
            ): bool,
            vol.Required(
                CONF_SCHOOL_ZONE,
                default=options.get(CONF_SCHOOL_ZONE, "C"),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "A", "label": "Zone A"},
                        {"value": "B", "label": "Zone B"},
                        {"value": "C", "label": "Zone C"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="school_zone",
                )
            ),
        }

        meal_selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "breakfast", "label": "breakfast"},
                    {"value": "lunch", "label": "lunch"},
                    {"value": "dinner", "label": "dinner"},
                ],
                mode=SelectSelectorMode.LIST,
                multiple=True,
                translation_key="meal_types",
            )
        )

        for key in MEAL_DAY_OPTIONS:
            data_schema[
                vol.Optional(
                    key,
                    default=options.get(key, DEFAULT_WEEKDAY_MEALS[key]),
                )
            ] = meal_selector

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(data_schema),
        )
