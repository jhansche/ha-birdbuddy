"""Test component setup."""
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.birdbuddy.const import DOMAIN


class MockFeed:
    """Minimal feed stub for RecentVisitors startup refresh."""

    def filter(self, of_type=None):
        """Return no feed items."""
        return []


@pytest.fixture(name="expected_lingering_timers")
def expected_lingering_timers_fixture():
    """Fixture to set expected_lingering_timers."""
    return True


async def test_async_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_setup_entry(hass: HomeAssistant):
    """Test config entry setup."""
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(
        domain="birdbuddy", data=config, state=ConfigEntryState.NOT_LOADED
    )
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
        return_value={"feeder1": {"id": "feeder1", "name": "Test Feeder"}},
    ), patch(
        "birdbuddy.client.BirdBuddy.feed",
        return_value=MockFeed(),
    ), patch(
        "birdbuddy.client.BirdBuddy.refresh_collections",
        return_value={},
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)


async def test_setup_entry_no_feeders(hass: HomeAssistant):
    """Test config entry setup with no feeders."""
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(
        domain="birdbuddy", data=config, state=ConfigEntryState.NOT_LOADED
    )
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
    """Test config entry setup when refresh fails."""
    config = {
        "email": "test@email.com",
        "password": "test-password",
    }
    config_entry = MockConfigEntry(
        domain="birdbuddy", data=config, state=ConfigEntryState.NOT_LOADED
    )
    config_entry.add_to_hass(hass)

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        side_effect=Exception,
    ):
        # Raises UpdateFailed -> return False
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
