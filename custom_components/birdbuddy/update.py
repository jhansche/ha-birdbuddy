"""Bird Buddy firmware updates"""

from __future__ import annotations
import asyncio

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import BirdBuddyDataUpdateCoordinator
from .device import BirdBuddyDevice
from .entity import BirdBuddyMixin


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    async_add_entities(BirdBuddyUpdate(f, coordinator) for f in feeders)


class BirdBuddyUpdate(BirdBuddyMixin, UpdateEntity):
    """Representation of a demo update entity."""

    coordinator: BirdBuddyDataUpdateCoordinator

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL
    _attr_has_entity_name = True
    _attr_name = "Firmware Update"

    __update_state = None

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-updater"

    @property
    def available(self) -> bool:
        """Updates are available only to the owner account."""
        return super().available and self.feeder.is_owner

    @property
    def installed_version(self) -> str | None:
        """Current version"""
        return self.feeder.version

    @property
    def latest_version(self) -> str | None:
        """Latest available version"""
        # available version will be None if there is no update available,
        # in which case latest version == current version.
        return self.feeder.version_update_available or self.feeder.version

    @property
    def in_progress(self) -> bool | int | None:
        if not self.__update_state:
            return None
        if self.__update_state.is_complete:
            return False
        return self.__update_state.progress

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        if version and version != self.latest_version:
            LOGGER.warning(
                "Ignoring requested version '%s', installing '%s' instead",
                version,
                self.latest_version,
            )

        self._attr_in_progress = True
        result = await self.coordinator.client.update_firmware_start(self.feeder)
        self.__update_state = result

        while not result.is_complete:
            if result.failure_reason is not None:
                self.__update_state = None
                raise HomeAssistantError(
                    f"Update failed on {self.feeder.name}: {result.failure_reason};\n"
                    f"{result}"
                )

            self._attr_in_progress = self.in_progress
            self.async_write_ha_state()

            # Firmware updates tend to be relatively slow...
            await asyncio.sleep(15)
            result = await self.coordinator.client.update_firmware_check(self.feeder)
            self.__update_state = result

        assert result.is_complete
        LOGGER.info("Bird Buddy update complete: %s", self.feeder.name)
        self.__update_state = None
        self._attr_in_progress = False
