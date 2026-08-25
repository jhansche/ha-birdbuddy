"""Tests for the Bird Buddy firmware update entity."""

from unittest.mock import AsyncMock, MagicMock, patch

from birdbuddy.exceptions import GraphqlError, NoFirmwareUpdateAvailableError
from birdbuddy.feeder import FeederUpdateStatus
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.birdbuddy.device import BirdBuddyDevice
from custom_components.birdbuddy.update import MAX_ERRORS, BirdBuddyUpdate

_OWNER = {
    "__typename": "FeederForOwner",
    "id": "f1",
    "name": "BB",
    "state": "READY_TO_STREAM",
    "battery": {"percentage": 80, "charging": False, "state": "HIGH"},
}


def _owner_update(coordinator=None, **extra: object):
    """Build an owner firmware-update entity.

    Args:
        coordinator: The coordinator mock, or a fresh MagicMock.
        **extra: Extra raw feeder fields (e.g. firmwareVersion).

    Returns:
        The update entity.
    """
    feeder = BirdBuddyDevice({**_OWNER, **extra})
    return BirdBuddyUpdate(feeder, coordinator or MagicMock())


def _progress(percent: int | None = None) -> FeederUpdateStatus:
    """Build an in-progress firmware status.

    Args:
        percent: The progress percent, or None to omit it.

    Returns:
        A progress-result update status.
    """
    data: dict[str, object] = {"__typename": "FeederFirmwareUpdateProgressResult"}
    if percent is not None:
        data["progress"] = percent
    return FeederUpdateStatus(data)


_DONE = FeederUpdateStatus({"__typename": "FeederFirmwareUpdateSucceededResult"})


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


def test_versions_and_owner_availability(hass):
    """Version properties read the feeder and updates need ownership."""
    update = _owner_update(firmwareVersion="1.0.0", availableFirmwareVersion="1.1.0")
    assert update.installed_version == "1.0.0"
    assert update.latest_version == "1.1.0"
    assert update.available is True


def test_latest_version_defaults_to_installed(hass):
    """With no update available, latest version equals the installed one."""
    update = _owner_update(firmwareVersion="1.0.0")
    assert update.latest_version == "1.0.0"


def test_update_unavailable_for_member(hass):
    """A member account cannot see the firmware update entity."""
    feeder = BirdBuddyDevice({**_OWNER, "__typename": "FeederForMember"})
    update = BirdBuddyUpdate(feeder, MagicMock())
    assert update.available is False


@pytest.mark.parametrize(
    ("start_progress", "expected"),
    [(50, 50), (0, True), (None, False)],
    ids=["percent", "indeterminate_zero", "no_percent"],
)
async def test_in_progress_reflects_status(hass, start_progress, expected):
    """in_progress maps the tracked status to HA's progress value."""
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(
        return_value=_progress(start_progress)
    )
    coordinator.client.update_firmware_check = AsyncMock(return_value=_DONE)
    update = _owner_update(coordinator)
    seen: list[bool | int | None] = []
    with (
        patch.object(
            update,
            "async_write_ha_state",
            side_effect=lambda: seen.append(update.in_progress),
        ),
        patch("asyncio.sleep", AsyncMock()),
    ):
        assert update.in_progress is False
        await update.async_install(version=None, backup=False)
    assert expected in seen
    assert update.in_progress is False


async def test_concurrent_install_is_rejected(hass):
    """A second install started while one runs raises HomeAssistantError."""
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(return_value=_progress(30))
    coordinator.client.update_firmware_check = AsyncMock(return_value=_DONE)
    update = _owner_update(coordinator)

    async def reenter(_seconds: float) -> None:
        with pytest.raises(HomeAssistantError, match="already in progress"):
            await update.async_install(version=None, backup=False)

    with (
        patch.object(update, "async_write_ha_state"),
        patch("asyncio.sleep", AsyncMock(side_effect=reenter)),
    ):
        await update.async_install(version=None, backup=False)


async def test_install_warns_on_version_mismatch(hass):
    """A requested version other than the latest is ignored with a warning."""
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(
        return_value=MagicMock(is_complete=True, is_failed=False)
    )
    update = _owner_update(
        coordinator, firmwareVersion="1.0.0", availableFirmwareVersion="1.1.0"
    )
    with patch.object(update, "async_write_ha_state"):
        await update.async_install(version="9.9.9", backup=False)
    coordinator.client.update_firmware_start.assert_awaited_once()


async def test_install_graphql_error_on_start(hass):
    """A GraphqlError starting the update surfaces its message."""
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(
        side_effect=GraphqlError({"message": "boom"})
    )
    update = _owner_update(coordinator)
    with pytest.raises(HomeAssistantError, match="boom"):
        await update.async_install(version=None, backup=False)


async def test_install_aborts_after_repeated_check_errors(hass):
    """Repeated GraphqlErrors while polling abort after MAX_ERRORS tries."""
    coordinator = MagicMock()
    coordinator.client.update_firmware_start = AsyncMock(
        return_value=MagicMock(is_complete=False, is_failed=False, progress=10)
    )
    coordinator.client.update_firmware_check = AsyncMock(
        side_effect=GraphqlError({"message": "x"})
    )
    update = _owner_update(coordinator)
    with (
        patch.object(update, "async_write_ha_state"),
        patch("asyncio.sleep", AsyncMock()),
        pytest.raises(GraphqlError),
    ):
        await update.async_install(version=None, backup=False)
    assert coordinator.client.update_firmware_check.await_count == MAX_ERRORS
