"""Tests for the Bird Buddy switches."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.birdbuddy.device import BirdBuddyDevice
from custom_components.birdbuddy.switch import (
    BirdBuddyAudioSwitch,
    BirdBuddyOffGridSwitch,
)


def _feeder(*, owner=True, **extra: object):
    """Build a feeder device for the switch tests.

    Args:
        owner: Whether the account owns the feeder.
        **extra: Extra raw feeder fields (e.g. offGrid, audioEnabled).

    Returns:
        The feeder device.
    """
    typename = "FeederForOwner" if owner else "FeederForMember"
    return BirdBuddyDevice({"__typename": typename, "id": "f1", "name": "BB", **extra})


async def test_offgrid_is_on_reads_state(hass):
    """The off-grid switch reflects the feeder's offGrid flag."""
    switch = BirdBuddyOffGridSwitch(_feeder(offGrid=True), MagicMock())
    assert switch.is_on is True


@pytest.mark.parametrize(("owner", "expected"), [(True, True), (False, False)])
async def test_offgrid_available_only_for_owner(hass, owner, expected):
    """Off-grid is available to owners and hidden for member accounts."""
    switch = BirdBuddyOffGridSwitch(_feeder(owner=owner), MagicMock())
    assert switch.available is expected


async def test_offgrid_turn_on_updates_and_notifies(hass):
    """Turning on off-grid applies the API result and notifies listeners."""
    coordinator = MagicMock()
    coordinator.client.toggle_off_grid = AsyncMock(return_value={"offGrid": True})
    switch = BirdBuddyOffGridSwitch(_feeder(offGrid=False), coordinator)
    await switch.async_turn_on()
    coordinator.client.toggle_off_grid.assert_awaited_once()
    assert switch.is_on is True
    coordinator.async_update_listeners.assert_called_once()


async def test_offgrid_turn_off_without_result_is_noop(hass):
    """A falsy API result leaves state unchanged and skips notifying."""
    coordinator = MagicMock()
    coordinator.client.toggle_off_grid = AsyncMock(return_value=None)
    switch = BirdBuddyOffGridSwitch(_feeder(offGrid=True), coordinator)
    await switch.async_turn_off()
    assert switch.is_on is True
    coordinator.async_update_listeners.assert_not_called()


async def test_offgrid_turn_off_updates_when_result(hass):
    """A successful turn-off applies the result and notifies listeners."""
    coordinator = MagicMock()
    coordinator.client.toggle_off_grid = AsyncMock(return_value={"offGrid": False})
    switch = BirdBuddyOffGridSwitch(_feeder(offGrid=True), coordinator)
    await switch.async_turn_off()
    assert switch.is_on is False
    coordinator.async_update_listeners.assert_called_once()


async def test_audio_is_on_and_icon_track_state(hass):
    """The audio switch state and icon follow the audioEnabled flag."""
    coordinator = MagicMock()
    coordinator.client.toggle_audio_enabled = AsyncMock(
        return_value={"audioEnabled": True}
    )
    switch = BirdBuddyAudioSwitch(_feeder(audioEnabled=False), coordinator)
    assert switch.is_on is False
    assert switch.icon == "mdi:microphone-off"
    await switch.async_turn_on()
    assert switch.is_on is True
    assert switch.icon == "mdi:microphone"
    coordinator.async_update_listeners.assert_called_once()


async def test_audio_turn_off_calls_client(hass):
    """Turning off audio calls the client and reflects the result."""
    coordinator = MagicMock()
    coordinator.client.toggle_audio_enabled = AsyncMock(
        return_value={"audioEnabled": False}
    )
    switch = BirdBuddyAudioSwitch(_feeder(audioEnabled=True), coordinator)
    await switch.async_turn_off()
    coordinator.client.toggle_audio_enabled.assert_awaited_once()
    assert switch.is_on is False
