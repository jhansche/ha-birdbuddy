"""Bird Buddy sensors"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from birdbuddy.feed import FeedNodeType
from birdbuddy.media import Collection, Media, is_media_expired
from birdbuddy.sightings import PostcardSighting

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_NEW_POSTCARD_SIGHTING, LOGGER
from .coordinator import BirdBuddyDataUpdateCoordinator
from .entity import BirdBuddyMixin
from .device import BirdBuddyDevice


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
    async_add_entities(BirdBuddyFoodStateEntity(f, coordinator) for f in feeders)


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

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:bird"
    _attr_name = "Recent Visitor"
    _attr_extra_state_attributes = {}

    _latest_collection: Collection | None = None
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

        @callback
        def filter_my_postcards(event: Event) -> bool:
            return self.feeder.id == event.data.get("sighting", {}).get(
                "feeder", {}
            ).get("id")

        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_NEW_POSTCARD_SIGHTING,
                self._on_new_postcard,
                event_filter=filter_my_postcards,
            )
        )

        await self._update_latest_visitor()

    async def _on_new_postcard(self, event: Event | None = None) -> None:
        """ """
        postcard = PostcardSighting(event.data["sighting"])

        assert postcard.report.sightings
        assert postcard.medias

        # media has created_at
        # but sightings[] does not.
        media = next(iter(postcard.medias), None)

        if media:
            self._latest_media = media
            self._attr_entity_picture = media.content_url
            # self._attr_extra_state_attributes["last_visit"] = media.created_at

        if unlocked := [
            s for s in postcard.report.sightings if s.sighting_type.is_unlocked
        ]:
            # NOTE: this might not be correct - if one sighting has multiple recognized
            # species, and one unlocked species, it's highly probably that the one unlocked
            # species is a mis-identification!
            # It's a little unusual for a single sighting to contain multiple bird species.
            self._attr_native_value = unlocked[0].species.name
            LOGGER.debug(
                "Reporting recent visitor from unlocked: %s", self._attr_native_value
            )
        elif recognized := [
            s for s in postcard.report.sightings if s.sighting_type.is_recognized
        ]:
            # Next best, select a recognized species
            self._attr_native_value = recognized[0].species.name
            LOGGER.debug(
                "Reporting recent visitor from recognized: %s", self._attr_native_value
            )
        elif guessable := [s for s in postcard.report.sightings if s.suggestions]:
            # Else, select one that has a list of suggestions
            suggested = guessable[0].suggestions[0]
            self._attr_native_value = suggested.species.name
            self._latest_collection = suggested
            LOGGER.info(
                "Reporting recent visitor from unrecognized suggestion: %s", suggested
            )
        else:
            # We don't know what it was. Instead of reporting a bogus "cannot decide"
            # type, just clear the value.
            self._attr_native_value = None
            LOGGER.info("Cannot decide species: %s", postcard.report.sightings[0])

        self.async_write_ha_state()

    async def _update_latest_visitor(self) -> None:
        feed = await self.coordinator.client.feed()
        items = feed.filter(
            of_type=[FeedNodeType.SpeciesSighting, FeedNodeType.SpeciesUnlocked]
        )
        my_items = [
            item
            for item in items
            if item
            and item.get("media")
            and item.get("collection")  # collection=None if it's been removed
            and (self.feeder.id in item["media"].get("thumbnailUrl", ""))
            and (item["collection"].get("species", None))
        ]

        if latest := max(my_items, default=None, key=lambda x: x.created_at):
            self._latest_media = Media(latest["media"])
            self._latest_collection = Collection(latest["collection"])

            self._attr_native_value = self._latest_collection.species.name
            self._attr_entity_picture = self._latest_media.thumbnail_url
            self.async_write_ha_state()

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

        if self._latest_collection:
            picture = self._latest_collection.cover_media.content_url
            if not is_media_expired(picture):
                return picture
        return None

    @property
    def native_value(self) -> str:
        if attr := super().native_value:
            # Postcard listener set the attribute directly, use it
            return attr
        if self._latest_collection:
            # If not set, get the most recent collection
            return self._latest_collection.bird_name
        return None


class BirdBuddyStateEntity(BirdBuddyMixin, SensorEntity):
    """Bird Buddy Feeder state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
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


class BirdBuddyFoodStateEntity(BirdBuddyMixin, SensorEntity):
    """Bird Buddy Food/Seed level."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_entity_registry_visible_default = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:food-turkey"
    _attr_name = "Food Level"
    _attr_translation_key = "metric_state"
    _attr_options = [
        "low",
        "medium",
        "high",
    ]
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
