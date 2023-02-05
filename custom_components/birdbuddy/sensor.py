"""Bird Buddy sensors"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from birdbuddy.birds import PostcardSighting
from birdbuddy.feed import FeedNodeType
from birdbuddy.media import Collection, Media, is_media_expired

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

from .const import DOMAIN, EVENT_NEW_POSTCARD_SIGHTING
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

        # find the more recent of report.sightings[], and use that for species & media
        sighting = postcard.report.sightings[0]
        if sighting.sighting_type.is_recognized:
            self._attr_native_value = sighting.species.name
        else:
            self._attr_native_value = sighting.sighting_type.value

        self.async_write_ha_state()

    async def _update_latest_visitor(self) -> None:
        feed = await self.coordinator.client.feed()
        items = feed.filter(
            of_type=[FeedNodeType.SpeciesSighting, FeedNodeType.SpeciesUnlocked]
        )
        my_items = [
            item
            for item in items
            if (self.feeder.id in item.get("media", {}).get("thumbnailUrl", ""))
            and (item.get("collection", {}).get("species", None))
        ]

        if latest := max(my_items, default=None, key=lambda x: x.created_at):
            self._latest_media = Media(latest["media"])
            self._latest_collection = Collection(latest["collection"])

            self._attr_native_value = self._latest_collection.bird_name
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
