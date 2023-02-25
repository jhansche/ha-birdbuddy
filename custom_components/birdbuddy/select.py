"""Bird Buddy Selectors"""

from __future__ import annotations

from birdbuddy.feeder import MetricState

from homeassistant.components.select import (
    SelectEntity,
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
    coordinator: BirdBuddyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    async_add_entities(BirdBuddyFrequencySelector(f, coordinator) for f in feeders)


class BirdBuddyFrequencySelector(BirdBuddyMixin, SelectEntity):
    """Select Frequency"""

    _attr_has_entity_name = True
    _attr_name = "Frequency"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "metric_state"
    _attr_options = [
        "low",
        "medium",
        "high",
    ]
    # TODO: remove once it is verified working
    _attr_attribution = "(This entity is incubating)"

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-frequency"

    @property
    def current_option(self) -> str | None:
        return self.feeder.frequency.value.lower()

    async def async_select_option(self, option: str) -> None:
        option = MetricState(option.upper())
        assert option != MetricState.UNKNOWN
        result = await self.coordinator.client.set_frequency(
            self.feeder,
            option,
        )
        if result:
            self.feeder.update(result)
            self.async_write_ha_state()
