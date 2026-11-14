"""Data Update coordinator for Bird Buddy."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from birdbuddy.client import BirdBuddy
from birdbuddy.exceptions import (
    AuthenticationFailedError,
    AuthTokenExpiredError,
    CompositeException,
    GraphqlError,
    UnexpectedResponseError,
)
from birdbuddy.feed import FeedNode, FeedNodeType
from birdbuddy.feeder import Feeder
from birdbuddy.media import Collection
from birdbuddy.postcards import PostcardAnalysis
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, EventOrigin, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .archive import PostcardArchive, get_archive
from .const import (
    ATTR_FEEDER_ID,
    ATTR_MEDIA,
    ATTR_POSTCARD_ID,
    ATTR_SHARE,
    ATTR_SPECIES,
    CONF_ARCHIVE_FOLDER,
    DOMAIN,
    EVENT_NEW_POSTCARD,
    LOGGER,
    POLLING_INTERVAL,
)
from .device import BirdBuddyDevice
from .repairs import async_check_legacy_event_listeners
from .visitors import RecentVisitors, VisitorCallback

FEED_CURSOR_STORE_VERSION = 1
ARCHIVE_RETRY_STORE_VERSION = 1
# How long a postcard whose archive save failed keeps being retried. Bird
# Buddy keeps uncollected postcards in the feed for about this long.
ARCHIVE_RETRY_FOR = timedelta(days=7)


class BirdBuddyDataUpdateCoordinator(DataUpdateCoordinator[BirdBuddy]):
    """Class to coordinate fetching BirdBuddy data."""

    config_entry: ConfigEntry
    client: BirdBuddy
    feeders: dict[str, BirdBuddyDevice]
    visitors: dict[str, RecentVisitors]

    def __init__(
        self,
        hass: HomeAssistant,
        client: BirdBuddy,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the BirdBuddy data coordinator.

        Args:
            hass: The Home Assistant instance.
            client: The authenticated Bird Buddy API client.
            entry: The config entry this coordinator serves.
        """
        self.client = client
        self.archive: PostcardArchive | None = (
            get_archive(hass, folder)
            if (folder := entry.options.get(CONF_ARCHIVE_FOLDER))
            else None
        )
        self.feeders = {}
        self.visitors = {}
        self.first_update = True
        # The newest feed item already handled. Kept on disk so a restart
        # resumes the feed where it left off, rather than firing every
        # uncollected postcard again as if it were new.
        self._feed_since: datetime | None = None
        self._feed_cursor_loaded = False
        self._feed_cursor: Store[dict[str, Any]] = Store(
            hass, FEED_CURSOR_STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.feed_cursor"
        )
        # Postcards whose archive save is incomplete, by id, with when it
        # first failed. Kept apart from the feed cursor, so a retry never
        # fires the postcard event again.
        self._archive_retry: dict[str, str] | None = None
        self._archive_retry_store: Store[dict[str, Any]] = Store(
            hass,
            ARCHIVE_RETRY_STORE_VERSION,
            f"{DOMAIN}.{entry.entry_id}.archive_retry",
        )
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=POLLING_INTERVAL,
        )

    def add_visitor_listener(
        self, feeder: Feeder, listener: VisitorCallback
    ) -> CALLBACK_TYPE:
        """Register a callback fired when a new visitor is detected.

        Args:
            feeder: The feeder to watch for visitors.
            listener: The callback to invoke on each new visitor.

        Returns:
            A callable that unregisters the listener when called.
        """
        if feeder.id not in self.visitors:
            self.visitors[feeder.id] = RecentVisitors(feeder, self.client, self.hass)
        return self.visitors[feeder.id].register_callback(listener)

    async def _process_feed(self, feed: list[FeedNode]) -> None:
        """Process new feed items, emitting an event per new postcard.

        For each new postcard, run the AI identification with
        ``BirdBuddy.identify_postcard``, save the visit to the archive when
        one is set up, and fire a slim ``birdbuddy_new_postcard`` event
        carrying the recognized species and media. Collecting is left to the
        user's automations, via the ``birdbuddy.collect_postcard`` service.

        A postcard the server refuses to identify is logged and skipped, so
        the entities that read the account data stay available.

        Args:
            feed: The feed nodes returned by the latest feed refresh.
        """
        LOGGER.debug("Found feed items %s", feed)
        postcards = [
            node for node in feed if node.node_type == FeedNodeType.NewPostcard
        ]

        for node in feed:
            if (
                node.node_type == FeedNodeType.SpeciesUnlocked
                and (raw := node.get("collection"))
                and (c := Collection(raw))
            ):
                LOGGER.info("Recently unlocked species: %s", c.bird_name)
                self.client.collections.setdefault(c.collection_id, c)

        LOGGER.debug("Found postcards %s", postcards)
        for postcard in postcards:
            LOGGER.debug("A new postcard is ready to process: %s", postcard)
            has_listeners = bool(
                self.hass.bus.async_listeners().get(EVENT_NEW_POSTCARD)
            )
            if not has_listeners and self.archive is None:
                # Nothing would use the result, so skip the identify API call.
                LOGGER.debug("No event listeners: skipping postcard identification")
                continue

            # Identify the visitor (species + media) without collecting, then
            # fire a slim event. Automations collect via the service; the
            # payload stays small enough for HA's 32 KiB event limit.
            try:
                analysis = await self.client.identify_postcard(postcard)
            except CompositeException, GraphqlError, UnexpectedResponseError:
                # The server rejected this one postcard. Every other entity
                # reads the account data the refresh already returned, so keep
                # the poll successful and carry on with the next postcard.
                LOGGER.exception("Could not identify postcard %s", postcard.node_id)
                await self._async_add_retry(postcard.node_id)
                continue
            if self.archive is not None:
                await self.async_archive_postcard(analysis)
            if not has_listeners:
                continue
            media = next(iter(analysis.medias), None)
            data = {
                ATTR_POSTCARD_ID: analysis.id,
                ATTR_FEEDER_ID: (analysis.feeder.id if analysis.feeder else None),
                ATTR_SPECIES: [dict(s) for s in analysis.species],
                ATTR_MEDIA: dict(media) if media else None,
            }
            self.hass.bus.async_fire(
                event_type=EVENT_NEW_POSTCARD,
                event_data=data,
                origin=EventOrigin.remote,
            )

    async def async_archive_postcard(self, analysis: PostcardAnalysis) -> list[str]:
        """Save an identified postcard to the archive.

        A failed save is logged rather than raised, so the poll and the
        event still go ahead.

        Args:
            analysis: The identified postcard.

        Returns:
            The newly written files, relative to the archive folder.
        """
        if self.archive is None:
            return []
        feeder = analysis.feeder
        feeder_name = (
            known.name
            if feeder and (known := self.client.feeders.get(feeder.id))
            else None
        )
        written: list[str] = []
        try:
            written = await self.archive.async_save_postcard(analysis, feeder_name)
        except OSError as err:
            LOGGER.warning("Could not archive postcard %s: %s", analysis.id, err)
        if written:
            LOGGER.debug("Archived postcard %s: %s", analysis.id, written)
        await self._async_track_archive(analysis)
        return written

    async def _async_retry_pending(self) -> dict[str, str]:
        """Load the archive retry list once.

        Returns:
            Postcard id to when its save first failed (ISO time).
        """
        pending = self._archive_retry
        if pending is None:
            stored = await self._archive_retry_store.async_load()
            pending = dict((stored or {}).get("pending") or {})
            self._archive_retry = pending
        return pending

    async def _async_add_retry(self, postcard_id: str) -> None:
        """Put a postcard on the retry list, when the archive is on.

        Args:
            postcard_id: The postcard's feed-item id.
        """
        if self.archive is None:
            return
        pending = await self._async_retry_pending()
        if postcard_id not in pending:
            pending[postcard_id] = dt_util.utcnow().isoformat()
            await self._archive_retry_store.async_save({"pending": pending})

    async def _async_track_archive(self, analysis: PostcardAnalysis) -> None:
        """Add an incompletely saved postcard to the retry list, or clear it.

        Args:
            analysis: The postcard that was just saved.
        """
        if self.archive is None:
            return
        pending = await self._async_retry_pending()
        try:
            complete = await self.archive.async_is_complete(analysis)
        except OSError as err:
            LOGGER.warning("Could not read the archive index: %s", err)
            complete = False
        if not complete:
            await self._async_add_retry(analysis.id)
        elif analysis.id in pending:
            del pending[analysis.id]
            await self._archive_retry_store.async_save({"pending": pending})

    async def _async_retry_archive(self) -> None:
        """Try again to save postcards whose earlier save was incomplete.

        Gives up on a postcard a week after its first failure. Identifying a
        postcard again returns fresh media links and doesn't fire the event.
        """
        if self.archive is None:
            return
        pending = await self._async_retry_pending()
        cutoff = dt_util.utcnow() - ARCHIVE_RETRY_FOR
        for postcard_id, since in list(pending.items()):
            first = dt_util.parse_datetime(since)
            if first is None or first < cutoff:
                LOGGER.warning("Giving up archiving postcard %s", postcard_id)
                del pending[postcard_id]
                await self._archive_retry_store.async_save({"pending": pending})
                continue
            try:
                analysis = await self.client.identify_postcard(postcard_id)
            except CompositeException, GraphqlError, UnexpectedResponseError:
                LOGGER.debug("Could not identify postcard %s for a retry", postcard_id)
                continue
            await self.async_archive_postcard(analysis)

    async def async_archive_history(self) -> dict[str, int]:
        """Save everything Bird Buddy still holds to the archive.

        Covers every species collection and the postcards still in the feed.
        Items already saved are skipped, so this can run again safely.

        Returns:
            How many files were saved from the collections and the feed.

        Raises:
            HomeAssistantError: If the archive isn't set up.
        """
        if self.archive is None:
            msg = "Set an archive folder in the Bird Buddy options first"
            raise HomeAssistantError(msg)
        counts = {"collections": 0, "postcards": 0}
        collections = await self.client.refresh_collections()
        for collection in collections.values():
            medias = await self.client.collection(collection.collection_id)
            try:
                written = await self.archive.async_save_collection(
                    collection, list(medias.values())
                )
            except OSError as err:
                LOGGER.warning(
                    "Could not archive collection %s: %s", collection.bird_name, err
                )
                continue
            counts["collections"] += len(written)
        for postcard in await self.client.new_postcards():
            try:
                analysis = await self.client.identify_postcard(postcard)
            except CompositeException, GraphqlError, UnexpectedResponseError:
                LOGGER.exception("Could not identify postcard %s", postcard.node_id)
                continue
            counts["postcards"] += len(await self.async_archive_postcard(analysis))
        LOGGER.info("Bird Buddy archive backfill saved %s", counts)
        return counts

    async def _refresh_feed(self) -> None:
        """Process the feed items newer than the saved cursor, then advance it.

        With no saved cursor (a new install) only the newest feed page is
        processed, as before.
        """
        if not self._feed_cursor_loaded:
            stored = await self._feed_cursor.async_load()
            if stored and (since := stored.get("since")):
                self._feed_since = FeedNode.parse_datetime(since)
            self._feed_cursor_loaded = True

        feed = await (
            self.client.refresh_feed(since=self._feed_since)
            if self._feed_since
            else self.client.refresh_feed()
        )
        await self._process_feed(feed)

        newest = max((n.created_at for n in feed if n.created_at), default=None)
        if newest is not None and (
            self._feed_since is None or newest > self._feed_since
        ):
            self._feed_since = newest
            await self._feed_cursor.async_save({"since": newest.isoformat()})

    async def _async_update_data(self) -> BirdBuddy:
        """Fetch the latest data from the Bird Buddy API.

        Returns:
            The refreshed BirdBuddy client.

        Raises:
            UpdateFailed: If the API refresh fails or no feeders are found.
        """
        try:
            await self.client.refresh()

            # Skip processing the feed on the first update. This works
            # around a minor issue where the `automation` integration is not
            # loaded yet by the time we make our first update call. If we
            # proceed, we might emit the postcard feed items while nothing is
            # listening; and because refresh_feed() tracks the last seen feed
            # item timestamp, that would prevent seeing that postcard again.
            # This delays the first postcard handling until the next update.
            if not self.first_update:
                await self._refresh_feed()
                await self._async_retry_archive()
        except (AuthenticationFailedError, AuthTokenExpiredError) as exc:
            msg = "Bird Buddy sign-in must be renewed"
            raise ConfigEntryAuthFailed(msg) from exc
        except Exception as exc:
            raise UpdateFailed(exc) from exc

        if not self.client.feeders:
            msg = "No Feeders found"
            raise UpdateFailed(msg)

        feeders = {
            feeder_id: BirdBuddyDevice(f)
            for (feeder_id, f) in self.client.feeders.items()
        }
        for i, f in feeders.items():
            if i in self.feeders:
                self.feeders[i].update(f)
            else:
                self.feeders[i] = f
        self.first_update = False

        # Every poll reads the listener counts, including the first one that
        # skips the feed above, and each repeat clears the issue once the last
        # stale trigger has moved to the new event.
        async_check_legacy_event_listeners(self.hass)

        return self.client

    async def handle_collect_postcard(self, data: dict[str, Any]) -> bool:
        """Handle the ``birdbuddy.collect_postcard`` service call.

        Args:
            data: The service payload with a ``postcard_id`` and an optional
                ``share`` flag.

        Returns:
            True if the postcard was collected to Media.
        """
        postcard_id = data[ATTR_POSTCARD_ID]
        share = data.get(ATTR_SHARE, False)
        LOGGER.debug("Calling collect_postcard: id=%s, share=%s", postcard_id, share)
        collected = await self.client.collect_postcard(postcard_id, share=share)
        # collect_postcard raises on failure, so reaching this line means the
        # postcard was collected.
        LOGGER.info("Collected postcard %s to Media", postcard_id)
        return bool(collected)
