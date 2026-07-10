"""The Bird Buddy image entity."""

from birdbuddy.media import Media, is_media_expired
from homeassistant.components.image import Image, ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED

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
    """Set up the Bird Buddy image entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback used to register the new entities.
    """
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
        """Initialize the recent-visitor image entity.

        Args:
            hass: The Home Assistant instance.
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        ImageEntity.__init__(self, hass)
        BirdBuddyMixin.__init__(self, feeder, coordinator)
        self._latest_media = None
        self._attr_unique_id = f"{self.feeder.id}-recent-image"

    def image(self) -> bytes | None:
        """Return the image bytes.

        Returns:
            None; image data is served from a URL via ``async_image()``.
        """
        # See async_image()
        return None

    async def _async_load_image_from_url(self, url: str) -> Image | None:
        """Load an image by URL, ensuring compatibility with Home Assistant.

        This method overrides the parent implementation because cloudfront
        sometimes returns a `text/plain` content type for image data, which
        is incompatible with Home Assistant's requirement for `image/*`.
        To address this, the content type is explicitly set to `image/jpeg`.

        Args:
            url: The image URL to fetch.

        Returns:
            The fetched image tagged as `image/jpeg`, or None if the fetch
            returned no content.

        Raises:
            HomeAssistantError: If ``_fetch_url`` encounters an HTTP error.
        """
        if response := await self._fetch_url(url):
            return Image(
                content=response.content,
                content_type="image/jpeg",
            )
        return None

    async def async_added_to_hass(self) -> None:
        """Register the recent-visitor listener when added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.add_visitor_listener(
                self.feeder,
                self._on_recent_visitor,
            )
        )

    @callback
    def _on_recent_visitor(self, visitors: RecentVisitors) -> None:
        """Update the image from the latest recorded visitor.

        Args:
            visitors: The recent-visitors tracker for this feeder.
        """
        self._update_url(visitors.latest_media)
        self.async_write_ha_state()

    def _update_url(self, media: Media | None) -> None:
        """Update the cached image URL from a media item.

        Sets the image URL when the media has an unexpired content or
        thumbnail URL; otherwise clears the cached URL if it has expired.

        Args:
            media: The latest media for this feeder, if any.
        """
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
