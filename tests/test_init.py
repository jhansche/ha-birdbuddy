"""Test component setup."""
from unittest.mock import patch, PropertyMock
from birdbuddy.user import BirdBuddyUser

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.birdbuddy.const import DOMAIN


async def test_async_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_setup_entry(hass: HomeAssistant):
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(domain="birdbuddy", data=config)
    config_entry.add_to_hass(hass)
    config_entry.state = ConfigEntryState.NOT_LOADED

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        return_value=True,
    ), patch(
        "birdbuddy.client.BirdBuddy.refresh_feed",
        return_value=[],
    ), patch(
        "birdbuddy.client.BirdBuddy.feeders",
        new_callable=PropertyMock,
        return_value={"feeder1": {"id": "feeder1", "name": "Test Feeder"}},
    ), patch(
        "birdbuddy.client.BirdBuddy.user",
        new_callable=PropertyMock,
        return_value=BirdBuddyUser({"name": "Test Account"}),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)


async def test_setup_entry_no_feeders(hass: HomeAssistant):
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(domain="birdbuddy", data=config)
    config_entry.add_to_hass(hass)
    config_entry.state = ConfigEntryState.NOT_LOADED

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        return_value=True,
    ), patch(
        "birdbuddy.client.BirdBuddy.refresh_feed",
        return_value=[],
    ):
        # Raises UpdateFailed -> return False
        assert not await hass.config_entries.async_setup(config_entry.entry_id)


async def test_setup_entry_refresh_fails(hass: HomeAssistant):
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(domain="birdbuddy", data=config)
    config_entry.add_to_hass(hass)
    config_entry.state = ConfigEntryState.NOT_LOADED

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        side_effect=Exception,
    ):
        # Raises UpdateFailed -> return False
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
