"""Bird Buddy Selectors"""

from __future__ import annotations

from birdbuddy.feeder import PowerProfile
from birdbuddy.exceptions import GraphqlError

from homeassistant.components.select import (
    SelectEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    async_add_entities(BirdBuddyPowerProfileSelector(f, coordinator) for f in feeders)


class BirdBuddyPowerProfileSelector(BirdBuddyMixin, SelectEntity):
    """Select Power Profile"""

    _attr_has_entity_name = True
    _attr_name = "Power Profile"
    _attr_icon = "mdi:power-settings"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "power_profile"
    _attr_options = [
        "frenzy_mode",
        "standard_mode",
        "power_saver_mode",
    ]
    # TODO: remove once it is verified working
    _attr_attribution = "(This entity is incubating)"

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-power-profile"

    @property
    def current_option(self) -> str | None:
        return self.feeder.power_profile.value.lower()

    @property
    def available(self) -> bool:
        return super().available and self.feeder.is_owner

    async def async_select_option(self, option: str) -> None:
        option = PowerProfile(option.upper())
        assert option != PowerProfile.UNKNOWN
        try:
            result = await self.coordinator.client.set_power_profile(
                self.feeder,
                option,
            )
            if result:
                self.feeder.update(result)
                self.async_write_ha_state()
        except GraphqlError as err:
            raise HomeAssistantError(
                f"Cannot set Power Profile for {self.entity_id} to {option}: {err}"
            ) from err
