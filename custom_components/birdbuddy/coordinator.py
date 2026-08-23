"""Data Update coordinator for Bird Buddy."""

from __future__ import annotations

from typing import Any

from birdbuddy.client import BirdBuddy
from birdbuddy.exceptions import (
    CompositeException,
    GraphqlError,
    UnexpectedResponseError,
)
from birdbuddy.feed import FeedNode, FeedNodeType
from birdbuddy.feeder import Feeder
from birdbuddy.media import Collection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, EventOrigin, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_FEEDER_ID,
    ATTR_MEDIA,
    ATTR_POSTCARD_ID,
    ATTR_SHARE,
    ATTR_SPECIES,
    DOMAIN,
    EVENT_NEW_POSTCARD,
    LOGGER,
    POLLING_INTERVAL,
)
from .device import BirdBuddyDevice
from .visitors import RecentVisitors, VisitorCallback


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
        self.feeders = {}
        self.visitors = {}
        self.first_update = True
        super().__init__(
            hass,
            LOGGER,
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
        ``BirdBuddy.identify_postcard`` and fire a slim
        ``birdbuddy_new_postcard`` event carrying the recognized species and
        media. Collecting is left to the user's automations, via the
        ``birdbuddy.collect_postcard`` service.

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
            if not self.hass.bus.async_listeners().get(EVENT_NEW_POSTCARD):
                # No listeners, so skip the identify API call.
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
                feed = await self.client.refresh_feed()
                await self._process_feed(feed)
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
        # collect_postcard raises on failure; reaching here means success.
        collected = await self.client.collect_postcard(postcard_id, share=share)
        LOGGER.info("Collected postcard %s to Media", postcard_id)
        return bool(collected)
