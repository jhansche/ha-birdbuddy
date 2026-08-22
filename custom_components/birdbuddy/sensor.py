"""Bird Buddy sensors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from birdbuddy.media import Media, is_media_expired
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
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import BirdBuddyDataUpdateCoordinator
from .device import BirdBuddyDevice
from .entity import BirdBuddyMixin
from .visitors import RecentVisitors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bird Buddy sensors from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback used to register the new entities.
    """
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
        """Initialize the battery sensor.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-battery"

    @property
    def native_value(self) -> int:
        """Return the battery charge.

        Returns:
            The battery level as a percentage.
        """
        return self.feeder.battery.percentage

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return extra state attributes.

        Returns:
            A mapping exposing the qualitative battery ``level``.
        """
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
        """Initialize the wifi signal sensor.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-signal"

    @property
    def native_value(self) -> int:
        """Return the wifi signal strength.

        Returns:
            The signal strength in dBm (RSSI).
        """
        return self.feeder.signal.rssi

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return extra state attributes.

        Returns:
            A mapping exposing the qualitative signal ``level``.
        """
        return {"level": self.feeder.signal.state.value}


class BirdBuddyRecentVisitorEntity(BirdBuddyMixin, RestoreSensor):
    """Bird Buddy recent visitors."""

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
        """Initialize the recent-visitor sensor.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-recent-visitor"

    async def async_added_to_hass(self) -> None:
        """Register the recent-visitor listener when added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.add_visitor_listener(
                self.feeder,
                self._on_recent_visitor,
            )
        )

    @property
    def entity_picture(self) -> str | None:
        """Return the recent visitor's image URL.

        Returns:
            The restored or most recent media URL while it is still valid, or
            None when there is no unexpired image.
        """
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
    def native_value(self) -> str | None:
        """Return the most recent visitor's species name.

        Returns:
            The species name recorded by the postcard listener, or None when
            no visitor has been seen yet.
        """
        # The postcard listener sets _attr_native_value directly.
        value = super().native_value
        if isinstance(value, str) and value:
            return value
        return None

    @callback
    def _on_recent_visitor(self, visitors: RecentVisitors) -> None:
        """Update the entity from the latest recorded visitor.

        Species and picture are updated together from the same detection, so
        the state never lags its ``entity_picture``.

        Args:
            visitors: The recent-visitors tracker for this feeder.
        """
        media = visitors.latest_media
        species = visitors.latest_species
        self._latest_media = media
        self._attr_entity_picture = media.content_url if media else None
        self._attr_native_value = species.name if species else None
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
        """Initialize the feeder-state sensor.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-state"

    @property
    def native_value(self) -> str:
        """Return the feeder state.

        Returns:
            The feeder state as a lowercase enum string (see options above).
        """
        return self.feeder.state.value.lower()


class BirdBuddyTemperatureEntity(BirdBuddyMixin, SensorEntity):
    """Bird Buddy feeder temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False  # Incubating
    _attr_entity_category = EntityCategory.DIAGNOSTIC  # Incubating
    _attr_has_entity_name = True
    _attr_name = "Temperature"
    # TODO(jhansche): remove once it is verified working
    _attr_attribution = "(This entity is incubating)"
    # FIXME: value is always 0, cannot tell unit
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the temperature sensor.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-temperature"

    @property
    def native_value(self) -> int:
        """Return the feeder temperature.

        Returns:
            The temperature reported by the feeder, in degrees Celsius.
        """
        return self.feeder.temperature

    async def add_to_platform_finish(self) -> None:
        """Warn that this incubating entity was enabled, then finish setup."""
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
    # TODO(jhansche): remove once it is verified working
    _attr_attribution = "(This entity is incubating)"

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the food-level sensor.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-food-state"

    @property
    def native_value(self) -> str:
        """Return the food level.

        Returns:
            The food level as a lowercase enum string (see ``_attr_options``).
        """
        return self.feeder.food.value.lower()

    async def add_to_platform_finish(self) -> None:
        """Warn that this incubating entity was enabled, then finish setup."""
        await super().add_to_platform_finish()
        if self.enabled:
            LOGGER.warning("Bird Buddy Food Level entity is incubating")
