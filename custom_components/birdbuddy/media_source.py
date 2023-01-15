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
from homeassistant.helpers import device_registry as dr
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
        # FIXME: use a real identifier? URL?
        base = [None] * 4
        data = identifier.split("#", 3)
        return cast(
            tuple[Optional[str], Optional[str], Optional[str], Optional[str]],
            tuple(data + base)[:4],  # type: ignore[operator]
        )

    def _get_config_or_raise(self, config_id: str) -> ConfigEntry:
        """Get a config entry from a URL."""
        entry = self.hass.config_entries.async_get_entry(config_id)
        if not entry:
            raise MediaSourceError(f"Unable to find config entry with id: {config_id}")
        return entry

    def _get_device_or_raise(self, device_id: str) -> dr.DeviceEntry:
        """Get a config entry from a URL."""
        device_registry = dr.async_get(self.hass)
        if not (device := device_registry.async_get(device_id)):
            raise MediaSourceError(f"Unable to find device with id: {device_id}")
        return device

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        # MediaSourceItem(hass=<homeassistant.core.HomeAssistant object at 0x7f3182c464f0>, domain='birdbuddy',
        # identifier='55acd4b8067b6a7a12bfde981bc20259#d6c99bbbc73e6438c96352717910fdd9#aabff4b8-d9f5-4511-876b-daccea3f8482#908a67e0-cdf9-465b-97df-40a5b00763d2',
        #  target_media_player=None)
        config_id, device_id, collection_id, media_id = self._parse_identifier(
            item.identifier
        )

        if not config_id or not device_id or not collection_id or not media_id:
            raise Unresolvable(
                f"Incomplete media identifier specified: {item.identifier}"
            )

        # device = self._get_device_or_raise(device_id)
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
            # FIXME: extract id
            config_id, device_id, collection_id, _ = self._parse_identifier(
                item.identifier
            )
            config = device = None
            coordinator: BirdBuddyDataUpdateCoordinator = None
            if config_id:
                config = self._get_config_or_raise(config_id)
                coordinator = self.hass.data[DOMAIN][config_id]
            if device_id:
                device = self._get_device_or_raise(device_id)

            if config and device and collection_id:
                if (
                    not coordinator.client.collections
                    or collection_id not in coordinator.client.collections
                ):
                    # FIXME: cache it at all?
                    await coordinator.client.refresh_collections()
                collection = coordinator.client.collections[collection_id]
                return await self._build_media_collection_entries(
                    config, device, coordinator, collection
                )

            if config and device:
                # Feeder selected: show collections on that feeder
                # TODO: is this right? Are collections feeder based or login based?
                # TODO: pass refresh_collections() to build
                if not coordinator.client.collections:
                    # FIXME: better way to refresh?
                    await coordinator.client.refresh_collections()
                # for a feeder/device, now look up the collections (one per bird?)
                return self._build_media_collections(config, device, coordinator)

            if config:
                # Login selected: show all feeders on that account
                return self._build_media_feeders(config)

        # Root of the media source: show all configured logins
        return self._build_media_configs()

    def _account_media_source(self, config: ConfigEntry) -> BrowseMediaSource:
        # Return one Bird Buddy account source per config entry
        coordinator = self.hass.data[DOMAIN][config.entry_id]
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
    def _build_media_feeder(
        cls,
        config: ConfigEntry,
        device: dr.DeviceEntry,
        full_title: bool = True,
    ) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"{config.entry_id}#{device.id}",
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=f"{config.title} {device.name}" if full_title else device.name,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
        )

    def _build_media_feeders(self, config: ConfigEntry) -> BrowseMediaSource:
        """Build the media sources for device entries."""
        device_registry = dr.async_get(self.hass)
        devices = dr.async_entries_for_config_entry(device_registry, config.entry_id)

        base = self._build_media_config(config)
        base.children = [
            # each child will be one Feeder device
            self._build_media_feeder(config, device, full_title=False)
            for device in devices
        ]
        return base

    @classmethod
    def _build_media_collection(
        cls,
        config: ConfigEntry,
        device: dr.DeviceEntry,
        coordinator: BirdBuddyDataUpdateCoordinator,
        collection: Collection,
        full_title: bool = True,
    ) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"{config.entry_id}#{device.id}#{collection.collection_id}",
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
        device: dr.DeviceEntry,
        coordinator: BirdBuddyDataUpdateCoordinator,
        collection: Collection,
    ) -> BrowseMediaSource:
        base = self._build_media_collection(config, device, coordinator, collection)
        base.children = []
        medias = await coordinator.client.collection(collection.collection_id)
        for (media_id, media) in medias.items():
            relative_title = _best_timedelta_title(media.created_at, dt_util.utcnow())
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{config.entry_id}#{device.id}#{collection.collection_id}#{media_id}",
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
        device: dr.DeviceEntry,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> BrowseMediaSource:
        base = self._build_media_feeder(config, device)
        collections = coordinator.client.collections
        base.children = [
            self._build_media_collection(
                config,
                device,
                coordinator,
                c,
                full_title=False,
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
