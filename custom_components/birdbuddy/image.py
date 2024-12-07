"""The Bird Buddy image entity."""

from birdbuddy.feed import FeedNodeType
from birdbuddy.media import Media, is_media_expired
from birdbuddy.sightings import PostcardSighting

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_NEW_POSTCARD_SIGHTING
from .coordinator import BirdBuddyDataUpdateCoordinator
from .device import BirdBuddyDevice
from .entity import BirdBuddyMixin
from .util import _find_media_with_species


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    coordinator: BirdBuddyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    async_add_entities(
        BirdBuddyRecentVisitorImageEntity(hass, f, coordinator) for f in feeders
    )


class BirdBuddyRecentVisitorImageEntity(BirdBuddyMixin, ImageEntity):
    """The latest visitor image entity."""

    _attr_has_entity_name = True
    _attr_name = "Recent Visitor Image"

    _latest_media: Media | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the entity."""
        ImageEntity.__init__(self, hass)
        BirdBuddyMixin.__init__(self, feeder, coordinator)
        self._latest_media = None
        self._attr_unique_id = f"{self.feeder.id}-recent-image"

    def image(self) -> bytes | None:
        """Return the image bytes."""
        # See async_image()
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def filter_my_postcards(event: Event) -> bool:
            # FIXME: This signature changed in 2024.4
            data = event if callable(getattr(event, "get", None)) else event.data
            return self.feeder.id == (
                data.get("sighting", {}).get("feeder", {}).get("id")
            )

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
        self._update_url(media)

    async def _update_latest_visitor(self) -> None:
        feed = await self.coordinator.client.feed()

        items = feed.filter(
            of_type=[
                FeedNodeType.SpeciesSighting,
                FeedNodeType.SpeciesUnlocked,
                FeedNodeType.NewPostcard,
                FeedNodeType.CollectedPostcard,
            ],
        )

        my_items = _find_media_with_species(self.feeder.id, items)

        if latest := max(my_items, default=None, key=lambda x: x.created_at):
            self._latest_media = Media(latest["media"])
            self._update_url(self._latest_media)
            self.async_write_ha_state()

    def _update_url(self, media: Media) -> None:
        if (
            media
            and (url := media.content_url or media.thumbnail_url)
            and (created_at := media.created_at)
            and not is_media_expired(url)
        ):
            self._attr_image_url = url
            self._attr_image_last_updated = created_at
            self._attr_entity_picture = url
        elif is_media_expired(self._attr_image_url):
            # Clear it
            self._attr_image_url = None
            self._attr_image_last_updated = None
            self._attr_entity_picture = None
