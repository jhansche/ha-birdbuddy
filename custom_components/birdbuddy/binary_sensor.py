"""Bird Buddy sensors"""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device import BirdBuddyDevice
from .entity import BirdBuddyMixin
from .const import DOMAIN
from .coordinator import BirdBuddyDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    async_add_entities(BirdBuddyChargingEntity(f, coordinator) for f in feeders)


class BirdBuddyChargingEntity(BirdBuddyMixin, BinarySensorEntity):
    """Whether the Bird Buddy battery is charging."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_name = "Charging"
    _attr_has_entity_name = True

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-charging"

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return self.feeder.battery.is_charging
