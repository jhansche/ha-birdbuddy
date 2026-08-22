"""Tests for the Bird Buddy firmware update entity."""

from unittest.mock import AsyncMock, MagicMock, patch

from birdbuddy.exceptions import NoFirmwareUpdateAvailableError
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.birdbuddy.device import BirdBuddyDevice
from custom_components.birdbuddy.update import BirdBuddyUpdate

_OWNER = {
    "__typename": "FeederForOwner",
    "id": "f1",
    "name": "BB",
    "state": "READY_TO_STREAM",
    "battery": {"percentage": 80, "charging": False, "state": "HIGH"},
}


async def test_install_already_on_latest(hass):
    """Already-on-latest raises a clean HomeAssistantError."""
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(
        side_effect=NoFirmwareUpdateAvailableError("latest")
    )
    update = BirdBuddyUpdate(BirdBuddyDevice(_OWNER), coordinator)
    with pytest.raises(HomeAssistantError, match="latest firmware"):
        await update.async_install(version=None, backup=False)


@pytest.mark.parametrize(
    "override",
    [{"state": "OFFLINE"}, {"battery": {"percentage": 5, "charging": False}}],
    ids=["rejected_state", "low_battery"],
)
async def test_install_rejected_before_api_call(hass, override):
    """A rejecting state or low battery raises before any API call."""
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock()
    update = BirdBuddyUpdate(BirdBuddyDevice({**_OWNER, **override}), coordinator)
    with pytest.raises(HomeAssistantError):
        await update.async_install(version=None, backup=False)
    coordinator.client.update_firmware_start.assert_not_awaited()


async def test_install_polls_until_complete(hass):
    """async_install polls update_firmware_check until the update completes."""
    in_progress = MagicMock(is_complete=False, is_failed=False, progress=50)
    done = MagicMock(is_complete=True, is_failed=False, progress=100)
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(return_value=in_progress)
    coordinator.client.update_firmware_check = AsyncMock(return_value=done)
    update = BirdBuddyUpdate(BirdBuddyDevice(_OWNER), coordinator)
    with (
        patch.object(update, "async_write_ha_state"),
        patch("asyncio.sleep", AsyncMock()),
    ):
        await update.async_install(version=None, backup=False)
    coordinator.client.update_firmware_check.assert_awaited_once()


async def test_install_failed(hass):
    """A failed update status during polling raises HomeAssistantError."""
    in_progress = MagicMock(is_complete=False, is_failed=False, progress=0)
    failed = MagicMock(is_complete=False, is_failed=True)
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(return_value=in_progress)
    coordinator.client.update_firmware_check = AsyncMock(return_value=failed)
    update = BirdBuddyUpdate(BirdBuddyDevice(_OWNER), coordinator)
    with (
        patch.object(update, "async_write_ha_state"),
        patch("asyncio.sleep", AsyncMock()),
        pytest.raises(HomeAssistantError),
    ):
        await update.async_install(version=None, backup=False)
