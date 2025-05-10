"""The Bird Buddy image entity."""

from birdbuddy.media import Media, is_media_expired
from homeassistant.components.image import (
    UNDEFINED,
    ImageEntity,
    Image,
)
from homeassistant.config_entries import ConfigEntry
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

    async def _async_load_image_from_url(self, url: str) -> Image | None:
        """Load an image by url."""
        # Override the parent because cloudfront is returning text/plain
        # and HA requires image/*
        # If there's an HTTP error, fetch_url will still raise that.
        if response := await self._fetch_url(url):
            return Image(
                content=response.content,
                content_type="image/jpeg",
            )
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.add_visitor_listener(
                self.feeder,
                self._on_recent_visitor,
            )
        )

    @callback
    def _on_recent_visitor(self, visitors: RecentVisitors) -> None:
        self._update_url(visitors.latest_media)
        self.async_write_ha_state()

    def _update_url(self, media: Media) -> None:
        if (
            media
            and (url := media.content_url or media.thumbnail_url)
            and (created_at := media.created_at)
            and not is_media_expired(url)
        ):
            LOGGER.debug(
                "Updating latest image for %s: %s",
                self.feeder.name,
                url,
            )
            self._attr_image_url = url
            self._attr_image_last_updated = created_at
            self._attr_entity_picture = url
            self._cached_image = None
        elif (url := self.image_url) and url is not UNDEFINED and is_media_expired(url):
            # Clear it
            self._attr_image_url = None
            self._attr_image_last_updated = None
            self._attr_entity_picture = None
