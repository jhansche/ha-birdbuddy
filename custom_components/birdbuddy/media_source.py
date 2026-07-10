"""Bird Buddy Media Source."""

from datetime import datetime
from typing import cast

from birdbuddy.media import Collection, Media
from homeassistant.components.media_player.const import MediaClass, MediaType
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
        """Initialize the media source.

        Args:
            hass: The Home Assistant instance.
        """
        super().__init__(DOMAIN)
        self.hass = hass

    def _root_media_source(self) -> BrowseMediaSource:
        """Build the root media source node.

        Returns:
            The root directory listing one node per configured account.
        """
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
    def _parse_identifier(
        cls, identifier: str
    ) -> tuple[str | None, str | None, str | None]:
        """Split a media identifier into its component parts.

        Args:
            identifier: The ``#``-delimited media source identifier.

        Returns:
            A 3-tuple of (config id, collection id, media id); missing
            trailing components are None.
        """
        parts = identifier.split("#", 2)
        padded = [*parts, None, None, None]
        return cast(
            tuple[str | None, str | None, str | None],
            tuple(padded[:3]),
        )

    def _get_config_or_raise(self, config_id: str) -> ConfigEntry:
        """Return the config entry for an id.

        Args:
            config_id: The config entry id to resolve.

        Returns:
            The matching config entry.

        Raises:
            MediaSourceError: If no config entry with the id exists.
        """
        entry = self.hass.config_entries.async_get_entry(config_id)
        if not entry:
            msg = f"Unable to find config entry with id: {config_id}"
            raise MediaSourceError(msg)
        return entry

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media item to a playable URL.

        Args:
            item: The media source item to resolve.

        Returns:
            The resolved playable media.

        Raises:
            Unresolvable: If the identifier is incomplete or the media has
                no content URL.
        """
        config_id, collection_id, media_id = self._parse_identifier(item.identifier)

        if not config_id or not collection_id or not media_id:
            msg = f"Incomplete media identifier specified: {item.identifier}"
            raise Unresolvable(msg)

        coordinator: BirdBuddyDataUpdateCoordinator = self.hass.data[DOMAIN][config_id]
        medias = await coordinator.client.collection(collection_id)
        media = medias[media_id]

        url = media.content_url
        if not url:
            msg = f"Could not resolve media item: {item.identifier}"
            raise Unresolvable(msg)

        return PlayMedia(url, _mime_type(media))

    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Browse the Bird Buddy media tree.

        Args:
            item: The media source item to browse.

        Returns:
            The browse result for the requested item, or the root listing
            when no identifier is supplied.
        """
        if item.identifier:
            config = None
            coordinator: BirdBuddyDataUpdateCoordinator | None = None
            config_id, collection_id, _ = self._parse_identifier(item.identifier)
            if config_id:
                config = self._get_config_or_raise(config_id)
                coordinator = self.hass.data[DOMAIN][config_id]

            if coordinator and not coordinator.client.collections:
                await coordinator.client.refresh_collections()

            if config and collection_id and coordinator:
                if (
                    not coordinator.client.collections
                    or collection_id not in coordinator.client.collections
                ):
                    await coordinator.client.refresh_collections()
                collection = coordinator.client.collections[collection_id]
                return await self._build_media_collection_entries(
                    config, coordinator, collection
                )

            if config and coordinator:
                return await self._build_media_collections(config, coordinator)

        # Root of the media source: show all configured logins
        return self._build_media_configs()

    def _account_media_source(self, config: ConfigEntry) -> BrowseMediaSource:
        """Build the media source node for one account.

        Args:
            config: The config entry (account) to represent.

        Returns:
            A directory node for the account's collections.
        """
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
        """Build the media source for one configured account.

        Args:
            config: The config entry (account) to represent.

        Returns:
            The account directory node listing its feeders.
        """
        return self._account_media_source(config)

    def _build_media_configs(self) -> BrowseMediaSource:
        """Build the root media source for the whole integration.

        Returns:
            The root directory node.
        """
        return self._root_media_source()

    def _account_media_sources(self) -> list[BrowseMediaSource]:
        """Build one media source node per configured account.

        Returns:
            A node for each Bird Buddy config entry.
        """
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
        """Build a media source node for one collection.

        Args:
            config: The config entry (account) the collection belongs to.
            collection: The bird collection to represent.

        Returns:
            An expandable directory node for the collection.
        """
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
        """Build the media entries for one collection.

        Args:
            config: The config entry (account) the collection belongs to.
            coordinator: The coordinator for the account.
            collection: The collection whose media to list.

        Returns:
            The collection node populated with its media children.
        """
        base = self._build_media_collection(config, collection)
        base.children = []
        medias = await coordinator.client.collection(collection.collection_id)
        for media_id, media in medias.items():
            relative_title = _best_timedelta_title(media.created_at, dt_util.utcnow())
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=(
                        f"{config.entry_id}#{collection.collection_id}#{media_id}"
                    ),
                    media_class=_media_class(media),
                    media_content_type=_mime_type(media),
                    title=relative_title,
                    can_play=media.is_video,
                    can_expand=media.is_video,
                    thumbnail=media.thumbnail_url,
                )
            )
        return base

    async def _build_media_collections(
        self,
        config: ConfigEntry,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> BrowseMediaSource:
        """Build the collection nodes for one account.

        Args:
            config: The config entry (account) to list collections for.
            coordinator: The coordinator for the account.

        Returns:
            The account node populated with its collection children.
        """
        base = self._account_media_source(config)
        collections = await coordinator.client.refresh_collections()
        base.children = [
            self._build_media_collection(
                config,
                c,
            )
            for _, c in collections.items()
        ]
        return base


async def async_get_media_source(hass: HomeAssistant) -> BirdBuddyMediaSource:
    """Set up the Bird Buddy media source.

    Args:
        hass: The Home Assistant instance.

    Returns:
        The Bird Buddy media source.
    """
    return BirdBuddyMediaSource(hass)


def _media_class(media: Media) -> MediaClass:
    """Return the media class for a media item.

    Args:
        media: The media item to classify.

    Returns:
        ``MediaClass.VIDEO`` for videos, otherwise ``MediaClass.IMAGE``.
    """
    if media.get("__typename") == "MediaVideo":
        return MediaClass.VIDEO
    return MediaClass.IMAGE


def _mime_type(media: Media) -> str:
    """Return the MIME type for a media item.

    Args:
        media: The media item to inspect.

    Returns:
        ``video/mp4`` for videos, otherwise ``image/jpeg``.
    """
    # TODO(jhansche): Media class should expose this
    if media.get("__typename") == "MediaVideo":
        return "video/mp4"
    return "image/jpeg"


def _best_timedelta_title(other: datetime, now: datetime) -> str:
    """Format a media timestamp relative to now.

    Args:
        other: The media's creation timestamp.
        now: The current time to compare against.

    Returns:
        A human-readable, locally-formatted title for the timestamp.
    """
    # TODO(jhansche): find a better way to produce easily recognizable,
    # localized, and (as needed) relative datetimes.
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
