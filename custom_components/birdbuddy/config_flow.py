"""Config flow for the Bird Buddy integration."""

from __future__ import annotations

from typing import Any

from birdbuddy.client import BirdBuddy
from birdbuddy.exceptions import AuthenticationFailedError
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
import voluptuous as vol

from .const import DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bird Buddy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._client: BirdBuddy | None = None
        super().__init__()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial email/password step.

        Args:
            user_input: The submitted form values, or ``None`` to show the
                empty form.

        Returns:
            The user form to display, or the created config entry once the
            credentials authenticate.
        """
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors: dict[str, str] = {}
        result = await self._async_auth_or_validate(user_input, errors)
        if result is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=result["title"],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _async_auth_or_validate(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> dict[str, str] | None:
        """Sign in with the submitted credentials.

        Args:
            user_input: The submitted email and password.
            errors: Error map, populated with a ``base`` error on failure.

        Returns:
            A mapping with the entry ``title`` on success, or ``None`` on
            failure (with ``errors`` populated).
        """
        # self._client is Optional and pybirdbuddy ships no type hints, so
        # pyright can't narrow it after assignment -- use a local for access.
        client = BirdBuddy(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
        self._client = client
        try:
            result = await client.refresh()
        except AuthenticationFailedError:
            self._client = None
            errors["base"] = "invalid_auth"
            return None
        except Exception:  # noqa: BLE001  # any non-auth failure -> cannot_connect
            self._client = None
            errors["base"] = "cannot_connect"
            return None
        if not result:
            self._client = None
            errors["base"] = "cannot_connect"
            return None
        return {"title": client.user.name}
