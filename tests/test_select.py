"""Tests for the Bird Buddy power-profile selector."""

from unittest.mock import AsyncMock, MagicMock, patch

from birdbuddy.exceptions import GraphqlError
from birdbuddy.feeder import PowerProfile
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.birdbuddy.device import BirdBuddyDevice
from custom_components.birdbuddy.select import BirdBuddyPowerProfileSelector


def _selector(power_profile=None, coordinator=None):
    data = {"__typename": "FeederForOwner", "id": "feeder1", "name": "BB"}
    if power_profile is not None:
        data["powerProfile"] = power_profile
    feeder = BirdBuddyDevice(data)
    return BirdBuddyPowerProfileSelector(feeder, coordinator or MagicMock())


async def test_current_option_maps_known_profiles(hass):
    """A set profile maps to its lowercased option."""
    assert _selector("STANDARD_MODE").current_option == "standard_mode"
    assert _selector("ULTRA_FRENZY_MODE").current_option == "ultra_frenzy_mode"


async def test_current_option_none_when_unknown(hass):
    """A missing or unrecognized profile yields None, not an invalid option."""
    assert _selector().current_option is None
    assert _selector("SOMETHING_NEW").current_option is None


async def test_select_option_sets_profile(hass):
    """Selecting an option calls set_power_profile with the enum value."""
    coordinator = MagicMock()
    coordinator.client.set_power_profile = AsyncMock(
        return_value={"powerProfile": "FRENZY_MODE"}
    )
    selector = _selector("STANDARD_MODE", coordinator)
    with patch.object(selector, "async_write_ha_state"):
        await selector.async_select_option("frenzy_mode")

    coordinator.client.set_power_profile.assert_awaited_once()
    assert (
        coordinator.client.set_power_profile.await_args.args[1] is PowerProfile.FRENZY
    )


async def test_select_option_graphql_error(hass):
    """A GraphqlError from the API surfaces as HomeAssistantError."""
    coordinator = MagicMock()
    coordinator.client.set_power_profile = AsyncMock(
        side_effect=GraphqlError({"message": "nope"})
    )
    selector = _selector("STANDARD_MODE", coordinator)
    with pytest.raises(HomeAssistantError):
        await selector.async_select_option("frenzy_mode")
