"""Bird Buddy Media Source"""

from datetime import datetime
from typing import Optional, cast
from birdbuddy.media import Collection, Media

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
import homeassistant.util.dt as dt_util

from .const import DOMAIN
from .coordinator import BirdBuddyDataUpdateCoordinator


class BirdBuddyMediaSource(MediaSource):
    """Provides bird collection previews as media sources."""

    name: str = "Bird Buddy"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize BirdBuddyMediaSource."""
        super().__init__(DOMAIN)
        self.hass = hass

    def _root_media_source(self) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="",
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title="Bird Buddy Media",
            can_play=False,
            can_expand=True,
            children=self._account_media_sources(),
            children_media_class=MediaClass.DIRECTORY,
        )

    @callback
    @classmethod
    def _parse_identifier(cls, identifier: str) -> tuple[str, str, str, str]:
        base = [None] * 3
        data = identifier.split("#", 2)
        return cast(
            tuple[Optional[str], Optional[str], Optional[str]],
            tuple(data + base)[:3],  # type: ignore[operator]
        )

    def _get_config_or_raise(self, config_id: str) -> ConfigEntry:
        """Get a config entry from a URL."""
        entry = self.hass.config_entries.async_get_entry(config_id)
        if not entry:
            raise MediaSourceError(f"Unable to find config entry with id: {config_id}")
        return entry

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        config_id, collection_id, media_id = self._parse_identifier(item.identifier)

        if not config_id or not collection_id or not media_id:
            raise Unresolvable(
                f"Incomplete media identifier specified: {item.identifier}"
            )

        coordinator: BirdBuddyDataUpdateCoordinator = self.hass.data[DOMAIN][config_id]
        medias = await coordinator.client.collection(collection_id)
        media = medias[media_id]

        url = media.content_url
        if not url:
            raise Unresolvable(f"Could not resolve media item: {item.identifier}")

        return PlayMedia(url, _mime_type(media))

    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Return media."""
        if item.identifier:
            config = None
            coordinator: BirdBuddyDataUpdateCoordinator = None
            config_id, collection_id, _ = self._parse_identifier(item.identifier)
            if config_id:
                config = self._get_config_or_raise(config_id)
                coordinator = self.hass.data[DOMAIN][config_id]

            if coordinator and not coordinator.client.collections:
                await coordinator.client.refresh_collections()

            if config and collection_id:
                if (
                    not coordinator.client.collections
                    or collection_id not in coordinator.client.collections
                ):
                    await coordinator.client.refresh_collections()
                collection = coordinator.client.collections[collection_id]
                return await self._build_media_collection_entries(
                    config, coordinator, collection
                )

            if config:
                return self._build_media_collections(config, coordinator)

        # Root of the media source: show all configured logins
        return self._build_media_configs()

    def _account_media_source(self, config: ConfigEntry) -> BrowseMediaSource:
        # Return one Bird Buddy account source per config entry
        coordinator: BirdBuddyDataUpdateCoordinator = self.hass.data[DOMAIN][
            config.entry_id
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=config.entry_id,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=config.title,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            thumbnail=coordinator.client.user.avatar_url,
        )

    def _build_media_config(self, config: ConfigEntry) -> BrowseMediaSource:
        """MediaSource for a configured integration (account): list each feeder in the account."""
        return self._account_media_source(config)

    def _build_media_configs(self) -> BrowseMediaSource:
        """Build the root media source for the whole integration."""
        return self._root_media_source()

    def _account_media_sources(self) -> list[BrowseMediaSource]:
        return [
            self._account_media_source(entry)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        ]

    @classmethod
    def _build_media_collection(
        cls,
        config: ConfigEntry,
        collection: Collection,
    ) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"{config.entry_id}#{collection.collection_id}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title=collection.bird_name,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.IMAGE,
            thumbnail=collection.cover_media.thumbnail_url,
        )

    async def _build_media_collection_entries(
        self,
        config: ConfigEntry,
        coordinator: BirdBuddyDataUpdateCoordinator,
        collection: Collection,
    ) -> BrowseMediaSource:
        base = self._build_media_collection(config, collection)
        base.children = []
        medias = await coordinator.client.collection(collection.collection_id)
        for (media_id, media) in medias.items():
            relative_title = _best_timedelta_title(media.created_at, dt_util.utcnow())
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{config.entry_id}#{collection.collection_id}#{media_id}",
                    media_class=_media_class(media),
                    media_content_type=_mime_type(media),
                    title=relative_title,
                    can_play=media.is_video,
                    can_expand=media.is_video,
                    thumbnail=media.thumbnail_url,
                )
            )
        return base

    def _build_media_collections(
        self,
        config: ConfigEntry,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> BrowseMediaSource:
        base = self._account_media_source(config)
        collections = coordinator.client.collections
        base.children = [
            self._build_media_collection(
                config,
                c,
            )
            for _, c in collections.items()
        ]
        return base


async def async_get_media_source(hass: HomeAssistant) -> BirdBuddyMediaSource:
    """Set up media source."""
    return BirdBuddyMediaSource(hass)


def _media_class(media: Media) -> MediaClass:
    if media.get("__typename") == "MediaVideo":
        return MediaClass.VIDEO
    return MediaClass.IMAGE


def _mime_type(media: Media) -> str:
    # TODO: Media class should expose this
    if media.get("__typename") == "MediaVideo":
        return "video/mp4"
    return "image/jpeg"


def _best_timedelta_title(other: datetime, now: datetime) -> str:
    # TODO: better way to get easily recognizeable, localized, and relative (as needed) datetimes.

    other = other.astimezone(dt_util.DEFAULT_TIME_ZONE).replace(microsecond=0)
    if other > now:
        # whoops?
        return other.strftime("%c")
    delta = now - other

    if delta.days < 1:
        # use "x <units> ago" relative string for < 24 hours
        # possibly "today <time>" or just "<H:m>" time
        return dt_util.get_age(other) + " ago"
    # if days == 1, "yesterday"? "yesterday %X"?

    if delta.days < 7:
        # 1-7 days, use "<dow> <time>"
        return other.strftime("%a, %X")

    if delta.days < 365:
        # within a year, full localized date+time
        return other.strftime("%c")

    # More than a year, show date only
    return other.strftime("%x")
