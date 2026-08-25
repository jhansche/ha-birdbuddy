"""Bird Buddy firmware updates."""

from __future__ import annotations

import asyncio
from typing import Any

from birdbuddy.exceptions import GraphqlError, NoFirmwareUpdateAvailableError
from birdbuddy.feeder import FeederState
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import BirdBuddyDataUpdateCoordinator
from .device import BirdBuddyDevice
from .entity import BirdBuddyMixin

MAX_ERRORS = 4
REJECT_STATES = [
    FeederState.DEEP_SLEEP,
    FeederState.FACTORY_RESET,
    FeederState.OFFLINE,
    FeederState.PENDING_FACTORY_RESET,
    FeederState.PENDING_REMOVAL,
]
"""Reject the update if in a state that would prevent it."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bird Buddy update entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback used to register the new entities.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    async_add_entities(BirdBuddyUpdate(f, coordinator) for f in feeders)


class BirdBuddyUpdate(BirdBuddyMixin, UpdateEntity):
    """Representation of a Bird Buddy firmware update entity."""

    coordinator: BirdBuddyDataUpdateCoordinator

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )
    _attr_has_entity_name = True
    _attr_name = "Firmware Update"

    __update_state = None

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the firmware update entity.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-updater"
        self._attr_entity_registry_enabled_default = self.feeder.is_owner

    @property
    def available(self) -> bool:
        """Return whether the update entity is available.

        Returns:
            True when the base entity is available and the feeder is owned by
            this account; updates are only available to the owner.
        """
        return super().available and self.feeder.is_owner

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed firmware version.

        Returns:
            The feeder's current firmware version, if known.
        """
        return self.feeder.version

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version.

        Returns:
            The available update version, or the current version when no
            update is available.
        """
        # available version will be None if there is no update available,
        # in which case latest version == current version.
        return self.feeder.version_update_available or self.feeder.version

    @property
    def in_progress(self) -> bool | int | None:
        """Return the firmware update progress.

        Returns:
            False when no update is running or it is complete, True for an
            indeterminate start, otherwise the integer percent complete.
        """
        if not self.__update_state:
            return False
        if self.__update_state.is_complete:
            self.__update_state = None
            return False
        if self.__update_state.progress is None:
            return False
        if self.__update_state.progress == 0:
            # Return True to show an indeterminate progress indicator
            return True
        return int(self.__update_state.progress)

    def _raise_if_not_ready(self) -> None:
        """Raise if the feeder cannot start a firmware update.

        Raises:
            HomeAssistantError: If the feeder is in a rejecting state or its
                battery is too low.
        """
        if self.feeder.state in REJECT_STATES:
            msg = f"Cannot perform update when in state {self.feeder.state.value}"
            raise HomeAssistantError(msg)
        if self.feeder.battery.percentage < 10 and not self.feeder.battery.is_charging:
            msg = (
                "Low battery, charge the Feeder first: "
                f"{self.feeder.battery.percentage}%"
            )
            raise HomeAssistantError(msg)

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install a firmware update, blocking until it completes.

        Args:
            version: The requested version; ignored if it is not the latest.
            backup: Whether to back up before installing (unused).
            **kwargs: Additional Home Assistant install options (unused).

        Raises:
            HomeAssistantError: If the feeder is in a state that rejects
                updates, its battery is too low, or the update fails.
        """
        if self.__update_state is not None:
            msg = "A firmware update is already in progress"
            raise HomeAssistantError(msg)

        self._raise_if_not_ready()

        if version and version != self.latest_version:
            LOGGER.warning(
                "Ignoring requested version '%s', installing '%s' instead",
                version,
                self.latest_version,
            )

        try:
            result = await self.coordinator.client.update_firmware_start(self.feeder)
        except NoFirmwareUpdateAvailableError as exc:
            msg = "The feeder is already on the latest firmware"
            raise HomeAssistantError(msg) from exc
        except GraphqlError as exc:
            detail = exc.response.get("message") or str(exc)
            msg = f"Error starting update: {detail}"
            raise HomeAssistantError(msg) from exc
        self.__update_state = result

        errors = 0  # allow periodic transient errors

        while not result.is_complete:
            if result.is_failed:
                self.__update_state = None
                msg = (
                    f"Update failed on {self.feeder.name}: "
                    f"{result.failure_reason};\n{result}"
                )
                raise HomeAssistantError(msg)

            self.async_write_ha_state()
            LOGGER.debug("Current update progress=%s", self.__update_state)

            # Firmware updates tend to be relatively slow...
            await asyncio.sleep(15)

            try:
                result = await self.coordinator.client.update_firmware_check(
                    self.feeder
                )
                # Reset the error counter
                errors = 0
            except GraphqlError as exc:
                errors += 1
                if errors >= MAX_ERRORS:
                    # If we hit 4 errors in a row, abort
                    raise
                LOGGER.warning(
                    "Error checking update progress; will try again (%d/%d): %s",
                    errors,
                    MAX_ERRORS,
                    exc,
                )

            self.__update_state = result

        LOGGER.info("Bird Buddy update complete: %s", self.feeder.name)
        self.__update_state = None
