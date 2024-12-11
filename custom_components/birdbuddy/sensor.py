"""Bird Buddy sensors"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from birdbuddy.birds import Species
from birdbuddy.feed import FeedNodeType
from birdbuddy.media import Media, is_media_expired
from birdbuddy.sightings import PostcardSighting

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_NEW_POSTCARD_SIGHTING, LOGGER
from .coordinator import BirdBuddyDataUpdateCoordinator
from .entity import BirdBuddyMixin
from .device import BirdBuddyDevice
from .util import _find_media_with_species
from .visitors import RecentVisitors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities from a config entry."""
    coordinator: BirdBuddyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    async_add_entities(BirdBuddyBatteryEntity(f, coordinator) for f in feeders)
    async_add_entities(BirdBuddySignalEntity(f, coordinator) for f in feeders)
    async_add_entities(BirdBuddyStateEntity(f, coordinator) for f in feeders)
    async_add_entities(BirdBuddyRecentVisitorEntity(f, coordinator) for f in feeders)
    # Incubating: Food level always reports LOW
    async_add_entities(BirdBuddyFoodStateEntity(f, coordinator) for f in feeders)
    # Incubating: Temperature always reports 0
    async_add_entities(BirdBuddyTemperatureEntity(f, coordinator) for f in feeders)


class BirdBuddyBatteryEntity(BirdBuddyMixin, SensorEntity):
    """Representation of a Bird Buddy battery."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Battery"

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-battery"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return self.feeder.battery.percentage

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return {"level": self.feeder.battery.state.value}


class BirdBuddySignalEntity(BirdBuddyMixin, SensorEntity):
    """Bird Buddy wifi signal strength."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_name = "Signal Strength"

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-signal"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return self.feeder.signal.rssi

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return {"level": self.feeder.signal.state.value}


class BirdBuddyRecentVisitorEntity(BirdBuddyMixin, RestoreSensor):
    """Bird Buddy recent visitors"""

    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:bird"
    _attr_name = "Recent Visitor"
    _attr_extra_state_attributes = {}

    _latest_media: Media | None = None

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-recent-visitor"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.add_visitor_listener(
                self.feeder,
                self._on_recent_visitor,
            )
        )

    @property
    def entity_picture(self) -> str | None:
        if picture := super().entity_picture:
            if not is_media_expired(picture):
                return picture
            self._attr_entity_picture = None

        # FIXME: no good way to refresh if the picture url is expired

        if self._latest_media:
            picture = self._latest_media.content_url or self._latest_media.thumbnail_url
            if not is_media_expired(picture):
                return picture
            self._latest_media = None

        return None

    @property
    def native_value(self) -> str:
        if attr := super().native_value:
            # Postcard listener set the attribute directly, use it
            return attr
        return None

    @callback
    def _on_recent_visitor(self, visitors: RecentVisitors) -> None:
        media = visitors.latest_media
        species = visitors.latest_species
        if media:
            self._latest_media = media
            self._attr_entity_picture = media.content_url
        if species:
            self._attr_native_value = species.name
        self.async_write_ha_state()


class BirdBuddyStateEntity(BirdBuddyMixin, SensorEntity):
    """Bird Buddy Feeder state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_has_entity_name = True
    _attr_icon = "mdi:bird"
    _attr_name = "Feeder State"
    _attr_options = [
        # See birdbuddy/feeder.py, FeederState enum values
        "deep_sleep",
        "factory_reset",
        "firmware_update",
        "offline",
        "off_grid",
        "online",
        "out_of_feeder",
        "pending_factory_reset",
        "pending_removal",
        "ready_to_stream",
        "streaming",
        "taking_postcards",
        # anything unexpected
        "unknown",
    ]
    _attr_translation_key = "feeder_state"

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-state"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return self.feeder.state.value.lower()


class BirdBuddyTemperatureEntity(BirdBuddyMixin, SensorEntity):
    """Bird Buddy feeder temperature"""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False  # Incubating
    _attr_entity_category = EntityCategory.DIAGNOSTIC  # Incubating
    _attr_has_entity_name = True
    _attr_name = "Temperature"
    # TODO: remove once it is verified working
    _attr_attribution = "(This entity is incubating)"
    # FIXME: value is always 0, cannot tell unit
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-temperature"

    @property
    def native_value(self) -> int:
        """Temperature reported by the feeder"""
        return self.feeder.temperature

    async def add_to_platform_finish(self) -> None:
        await super().add_to_platform_finish()
        if self.enabled:
            LOGGER.warning("Bird Buddy Temperature entity is incubating")


class BirdBuddyFoodStateEntity(BirdBuddyMixin, SensorEntity):
    """Bird Buddy Food/Seed level."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False  # Incubating
    _attr_has_entity_name = True
    _attr_icon = "mdi:food-turkey"
    _attr_name = "Food Level"
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
        self._attr_unique_id = f"{self.feeder.id}-food-state"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return self.feeder.food.value.lower()

    async def add_to_platform_finish(self) -> None:
        await super().add_to_platform_finish()
        if self.enabled:
            LOGGER.warning("Bird Buddy Food Level entity is incubating")
