"""Bird Buddy switches"""

from typing import Any

from birdbuddy.feeder import FeederState

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
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
    entities = []
    entities.extend([BirdBuddyAudioSwitch(f, coordinator) for f in feeders])
    entities.extend([BirdBuddyOffGridSwitch(f, coordinator) for f in feeders])
    async_add_entities(entities)


class BirdBuddyOffGridSwitch(BirdBuddyMixin, SwitchEntity):
    """Off-grid switch"""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Off-Grid"
    _attr_has_entity_name = True
    coordinator: BirdBuddyDataUpdateCoordinator

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-offgrid"

    @property
    def available(self) -> bool:
        return super().available and self.feeder.is_owner

    @property
    def is_on(self) -> bool:
        return self.feeder.is_off_grid

    async def async_turn_on(self, **kwargs: Any) -> None:
        result = await self.coordinator.client.toggle_off_grid(self.feeder, True)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()

    async def async_turn_off(self, **kwargs: Any) -> None:
        result = await self.coordinator.client.toggle_off_grid(self.feeder, False)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()


class BirdBuddyAudioSwitch(BirdBuddyMixin, SwitchEntity):
    """Audio switch"""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Audio"
    _attr_icon = "mdi:microphone"
    _attr_has_entity_name = True
    _attr_translation_key = "audio_enabled"
    coordinator: BirdBuddyDataUpdateCoordinator

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-audio"

    @property
    def available(self) -> bool:
        return super().available and self.feeder.is_owner

    @property
    def is_on(self) -> bool:
        return self.feeder.is_audio_enabled

    @property
    def icon(self) -> str | None:
        return "mdi:microphone" if self.is_on else "mdi:microphone-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        result = await self.coordinator.client.toggle_audio_enabled(self.feeder, True)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()

    async def async_turn_off(self, **kwargs: Any) -> None:
        result = await self.coordinator.client.toggle_audio_enabled(self.feeder, False)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()
