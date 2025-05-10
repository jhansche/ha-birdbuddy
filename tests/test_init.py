"""Test component setup."""
from unittest.mock import patch, PropertyMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.birdbuddy.const import DOMAIN


@pytest.fixture(name="expected_lingering_timers")
def expected_lingering_timers_fixture():
    """Fixture to set expected_lingering_timers."""
    return True


async def test_async_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_setup_entry(hass: HomeAssistant):
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(domain="birdbuddy", data=config, state=ConfigEntryState.NOT_LOADED)
    config_entry.add_to_hass(hass)

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        return_value=True,
    ), patch(
        "birdbuddy.client.BirdBuddy.refresh_feed",
        return_value=[],
    ), patch(
        "birdbuddy.client.BirdBuddy.feeders",
        new_callable=PropertyMock,
        return_value={"feeder1": {"id": "feeder1", "name": "Test Feeder"}}
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)


async def test_setup_entry_no_feeders(hass: HomeAssistant):
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(domain="birdbuddy", data=config, state=ConfigEntryState.NOT_LOADED)
    config_entry.add_to_hass(hass)

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
    config_entry = MockConfigEntry(domain="birdbuddy", data=config, state=ConfigEntryState.NOT_LOADED)
    config_entry.add_to_hass(hass)

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        side_effect=Exception,
    ):
        # Raises UpdateFailed -> return False
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
