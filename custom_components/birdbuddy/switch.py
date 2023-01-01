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
    async_add_entities(BirdBuddyOffGridSwitch(f, coordinator) for f in feeders)


class BirdBuddyOffGridSwitch(BirdBuddyMixin, SwitchEntity):
    """Off-grid switch"""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_name = "Bird Buddy Off-Grid"
    coordinator: BirdBuddyDataUpdateCoordinator

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_name = f"{self.feeder.name} Off-Grid"
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
