"""Data Update coordinator for Bird Buddy."""

from __future__ import annotations

from typing import Any

from birdbuddy.client import BirdBuddy
from birdbuddy.exceptions import GraphqlError
from birdbuddy.feed import FeedNode, FeedNodeType
from birdbuddy.feeder import Feeder
from birdbuddy.media import Collection
from birdbuddy.sightings import PostcardSighting, SightingFinishStrategy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, EventOrigin, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, EVENT_NEW_POSTCARD_SIGHTING, LOGGER, POLLING_INTERVAL
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
        """Process new feed items, emitting an event for each new postcard.

        There are options for how these can be processed:
        - If the sighting contains a recognized bird, it can be finished
          automatically via :func:`BirdBuddy.finish_postcard`.
        - For all new postcards, emit a HA event and leave it to the user's
          automations to finish them, however (and if) they want.

        Args:
            feed: The feed nodes returned by the latest feed refresh.
        """
        LOGGER.debug("Found feed items %s", feed)
        postcards = [
            node for node in feed if node.node_type == FeedNodeType.NewPostcard
        ]

        for node in feed:
            if node.node_type == FeedNodeType.SpeciesUnlocked and (
                c := Collection(node.get("collection"))
            ):
                LOGGER.info("Recently unlocked species: %s", c.bird_name)
                self.client.collections.setdefault(c.collection_id, c)

        LOGGER.debug("Found postcards %s", postcards)
        for postcard in postcards:
            LOGGER.debug("A new postcard is ready to process: %s", postcard)
            if not self.hass.bus.async_listeners().get(EVENT_NEW_POSTCARD_SIGHTING):
                # if no one is listening, no sense in getting sighting data
                LOGGER.debug("No event listeners: skipping postcard conversion")
                continue

            # Emit a new event with sighting + postcard data, and expose
            # services that can:
            # 1. auto-collect a recognized bird
            # 2. manually assign a species
            # 3. auto-collect a best-guess species, using the report's
            #    confidence
            # 4. assign the sighting as "mystery visitor"
            # 5. all-in-one service choosing the best of 1, 3, or 4
            # Automations could use the sighting media URLs for extra AI
            # processing (e.g. Merlin or other classifiers), then do #2 with
            # the results. If viable, we can supply a Recipe in docs showing
            # how, plus default blueprints to handle it with user input.
            try:
                sighting = await self.client.sighting_from_postcard(postcard=postcard)
            except GraphqlError as exc:
                # The Bird Buddy cloud API occasionally returns a server error
                # (e.g. INTERNAL_SERVER_ERROR) for this specific mutation.
                # Don't let one bad postcard fail the entire coordinator
                # update -- that would also mark unrelated data (e.g. feeder
                # battery/food level) stale for this cycle. Log and move on
                # to the next postcard instead; it'll be retried on the next
                # update if it's still present in the feed.
                LOGGER.error(
                    "Failed to convert postcard to sighting; skipping this postcard: %s",
                    exc,
                )
                continue
            data = {
                "postcard": postcard.data,
                "sighting": sighting.data,
            }
            self.hass.bus.fire(
                event_type=EVENT_NEW_POSTCARD_SIGHTING,
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
            data: The service payload with ``postcard`` and ``sighting`` keys
                plus optional ``strategy``, ``best_guess_confidence``, and
                ``share_media`` options.

        Returns:
            True if the postcard was collected to Media.
        """
        sighting = PostcardSighting(data["sighting"])
        postcard_id = data["postcard"]["id"]
        strategy = SightingFinishStrategy(data.get("strategy", "recognized"))
        confidence = data.get("best_guess_confidence")
        share_media = data.get("share_media", False)

        LOGGER.debug(
            "Calling collect_postcard: id=%s, sighting=%s, strategy=%s",
            postcard_id,
            sighting,
            strategy,
        )
        success = await self.client.finish_postcard(
            postcard_id,
            sighting,
            strategy,
            confidence_threshold=confidence,
            share_media=share_media,
        )
        if success:
            LOGGER.info("Postcard collected to Media")
        else:
            # TODO(jhansche): more info
            LOGGER.warning("Postcard could not be collected")
        return success
