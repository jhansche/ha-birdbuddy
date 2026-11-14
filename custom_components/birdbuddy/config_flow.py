"""Config flow for Bird Buddy password and Google accounts."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
from typing import Any

from aiohttp import ClientError
from birdbuddy.client import BirdBuddy
from birdbuddy.exceptions import AuthenticationFailedError
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.exceptions import OAuth2TokenRequestError
from homeassistant.helpers import config_entry_oauth2_flow
import voluptuous as vol

from .archive import normalize_folder
from .const import (
    AUTH_EMAIL,
    AUTH_GOOGLE,
    CONF_ARCHIVE_FOLDER,
    CONF_AUTH_METHOD,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    DOMAIN,
    LOGGER,
)

STEP_EMAIL_DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
)


class ConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Authenticate the existing Bird Buddy account."""

    DOMAIN = DOMAIN
    VERSION = 2

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004
    ) -> OptionsFlowHandler:
        """Return the options flow.

        Args:
            config_entry: The entry; Home Assistant passes it, and the flow
                reads it from ``self.config_entry``.

        Returns:
            The options flow handler.
        """
        return OptionsFlowHandler()

    @property
    def logger(self) -> logging.Logger:
        """Return the integration logger."""
        return LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, str]:
        """Request only the identity permission Bird Buddy needs."""
        return {
            "scope": "https://www.googleapis.com/auth/userinfo.email",
            "access_type": "online",
            "prompt": "select_account",
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose a sign-in method, accepting legacy password submissions."""
        if user_input and CONF_EMAIL in user_input:
            return await self.async_step_email(user_input)
        return self.async_show_menu(
            step_id="user", menu_options=[AUTH_GOOGLE, AUTH_EMAIL]
        )

    async def async_step_google(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Start or retry Google browser authorization."""
        return await self.async_step_pick_implementation()

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Validate Bird Buddy email and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = BirdBuddy(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            try:
                refreshed = await client.refresh()
            except AuthenticationFailedError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                if refreshed:
                    return await self._async_finish(
                        client, {**user_input, CONF_AUTH_METHOD: AUTH_EMAIL}
                    )
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id=AUTH_EMAIL, data_schema=STEP_EMAIL_DATA_SCHEMA, errors=errors
        )

    async def async_step_creation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Resolve Google authorization without persisting or logging its tokens."""
        try:
            async with asyncio.timeout(30):
                token = await self.flow_impl.async_resolve_external_data(
                    self.external_data
                )
        except OAuth2TokenRequestError, ClientError, TimeoutError:
            return self._google_error("cannot_connect")
        finally:
            self.external_data = None
        return await self.async_oauth_create_entry(
            {"auth_implementation": self.flow_impl.domain, "token": token}
        )

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Exchange Google identity for a durable Bird Buddy session."""
        token = data.pop("token", {})
        google_access_token = token.get("access_token")
        if not isinstance(google_access_token, str) or not google_access_token:
            return self._google_error("invalid_auth")
        client = BirdBuddy()
        try:
            async with asyncio.timeout(30):
                await client.sign_in_google(google_access_token)
        except AuthenticationFailedError:
            return self._google_error("invalid_auth")
        except Exception:  # noqa: BLE001
            return self._google_error("cannot_connect")
        finally:
            token.clear()
        if client.tokens is None:
            return self._google_error("cannot_connect")
        return await self._async_finish(
            client,
            {
                "auth_implementation": data["auth_implementation"],
                CONF_AUTH_METHOD: AUTH_GOOGLE,
                CONF_REFRESH_TOKEN: client.tokens.refresh_token,
            },
        )

    def _google_error(self, reason: str) -> config_entries.ConfigFlowResult:
        """Show a retry action that starts a fresh authorization."""
        return self.async_show_form(
            step_id=AUTH_GOOGLE, data_schema=vol.Schema({}), errors={"base": reason}
        )

    async def _async_finish(
        self, client: BirdBuddy, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Validate account identity and create or repair its existing entry."""
        user = client.user
        email = str((user or {}).get("email") or data.get(CONF_EMAIL, "")).strip()
        if not email or user is None:
            return self.async_abort(reason="cannot_connect")
        data[CONF_EMAIL] = email
        user_id = user.get("id")
        if user_id:
            data[CONF_USER_ID] = user_id
        if self.source == config_entries.SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if expected_id := entry.data.get(CONF_USER_ID):
                same_user = expected_id == user_id
            else:
                same_user = entry.data[CONF_EMAIL].lower() == email.lower()
            if not same_user:
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(entry, data=data)
        if user_id and any(
            entry.data.get(CONF_USER_ID) == user_id
            for entry in self._async_current_entries()
        ):
            return self.async_abort(reason="already_configured")
        await self.async_set_unique_id(email.lower())
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=user.name, data=data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Ask the user to renew this account's authorization."""
        return self.async_show_form(step_id="reauth_confirm")

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Repeat the entry's original authentication method."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        if self._get_reauth_entry().data.get(CONF_AUTH_METHOD) == AUTH_GOOGLE:
            return await self.async_step_google()
        return await self.async_step_email()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Set where every visit's photos, videos and species are kept."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for the archive folder; blank turns the archive off."""
        errors: dict[str, str] = {}
        current = self.config_entry.options.get(CONF_ARCHIVE_FOLDER, "")
        if user_input is not None:
            folder = normalize_folder(user_input.get(CONF_ARCHIVE_FOLDER))
            if folder and not folder.startswith("/"):
                errors[CONF_ARCHIVE_FOLDER] = "not_absolute"
            elif folder and not self.hass.config.is_allowed_path(folder):
                errors[CONF_ARCHIVE_FOLDER] = "not_allowed"
            else:
                return self.async_create_entry(data={CONF_ARCHIVE_FOLDER: folder})
            current = folder
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_ARCHIVE_FOLDER, default=current): str}
            ),
            errors=errors,
        )
