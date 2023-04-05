"""Config flow for Bird Buddy integration."""
from __future__ import annotations

from birdbuddy.client import BirdBuddy
from birdbuddy.exceptions import AuthenticationFailedError
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_EMAIL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    LOGGER,
)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bird Buddy."""

    VERSION = 1

    def __init__(self):
        self._client = None
        super().__init__()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}
        if user_input is not None:
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

    async def _async_auth_or_validate(self, user_input, errors):
        self._client = BirdBuddy(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
        try:
            result = await self._client.refresh()
        except AuthenticationFailedError:
            self._client = None
            errors["base"] = "invalid_auth"
            return None
        except Exception:
            self._client = None
            errors["base"] = "cannot_connect"
            return None
        if not result:
            self._client = None
            errors["base"] = "cannot_connect"
            return None
        return {
            "title": self._client.user.name,
        }

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get option flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlowWithConfigEntry):
    """Options flow handler"""

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Display option dialog."""
        return self.async_show_menu(
            step_id="options_menu",
            menu_options=["camera_options"],
        )

    async def async_step_camera_options(self, user_input=None) -> FlowResult:
        """Display the Recent Visitor camera settings"""
        if user_input is not None:
            self.options.update(user_input)
            LOGGER.info(
                "Saving camera options: %s; merged=%s", user_input, self.options
            )
            return self.async_create_entry(title="", data=self.options)
        return self.async_show_form(
            step_id="camera_options",
            data_schema=vol.Schema(
                {
                    # Enable the recent visitor camera entity
                    vol.Optional(
                        "recent_visitor_camera",
                        default=self.options.get("recent_visitor_camera", False),
                    ): bool,
                    # Play the video media as the camera footage
                    # TODO: figure out how to loop the video
                    vol.Optional(
                        "recent_visitor_video",
                        # default=self.options.get("recent_visitor_video", False),
                        description={
                            "suggested_value": self.options.get(
                                "recent_visitor_video", False
                            )
                        },
                    ): bool,
                    # Fallback to snapshot slideshow
                    # TODO: figure out how to cycle through snapshots (1 is easy)
                    vol.Optional(
                        "recent_visitor_snapshot_limit",
                        description={
                            "suggested_value": self.options.get(
                                "recent_visitor_snapshot_limit", 1
                            )
                        },
                    ): vol.All(vol.Range(min=0, min_included=True), cv.positive_int),
                }
            ),
            last_step=True,
        )
