"""Test the Bird Buddy collect_postcard service."""

from unittest.mock import patch

import aiohttp
from birdbuddy.postcards import CollectedPostcard
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from voluptuous.error import MultipleInvalid

from custom_components.birdbuddy.const import DOMAIN, SERVICE_COLLECT_POSTCARD


async def test_collect_postcard_service(hass):
    """The service validates its schema and calls collect_postcard."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"},
    )
    config_entry.add_to_hass(hass)

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        side_effect=aiohttp.ClientConnectionError("Offline"),
    ):
        assert await async_setup_component(
            hass, DOMAIN, {CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"}
        )

    # postcard_id is required.
    with pytest.raises(MultipleInvalid) as exc_info:
        await hass.services.async_call(
            DOMAIN, SERVICE_COLLECT_POSTCARD, {}, blocking=True
        )
    msgs = [str(e) for e in exc_info.value.errors]
    assert "required key not provided @ data['postcard_id']" in msgs

    # A valid call reaches collect_postcard with the id and the share flag.
    with patch(
        "birdbuddy.client.BirdBuddy.collect_postcard",
        return_value=CollectedPostcard({"id": "feed item id"}),
    ) as collect_postcard:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {"postcard_id": "feed item id", "share": True},
            blocking=True,
        )
    collect_postcard.assert_called_once_with("feed item id", share=True)


async def test_collect_postcard_before_any_entry_loads(hass):
    """The service reports a missing feeder when no entry has loaded yet.

    async_setup registers the service whether or not a config entry exists,
    and only async_setup_entry populates hass.data[DOMAIN], so a call can
    arrive while that key is still absent.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    assert DOMAIN not in hass.data

    with pytest.raises(ValueError, match="not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {"postcard_id": "feed item id"},
            blocking=True,
        )
