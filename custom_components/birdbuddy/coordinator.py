"""Data Update coordinator for Bird Buddy."""

from __future__ import annotations

from birdbuddy.birds import PostcardSighting, SightingFinishStrategy
from birdbuddy.client import BirdBuddy
from birdbuddy.feed import FeedNode, FeedNodeType

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, EventOrigin
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from .const import (
    DOMAIN,
    EVENT_NEW_POSTCARD_SIGHTING,
    LOGGER,
    POLLING_INTERVAL,
)

from .device import BirdBuddyDevice


class BirdBuddyDataUpdateCoordinator(DataUpdateCoordinator[BirdBuddy]):
    """Class to coordinate fetching BirdBuddy data."""

    config_entry: ConfigEntry
    client: BirdBuddy
    feeders: dict[str, BirdBuddyDevice]

    def __init__(
        self,
        hass: HomeAssistant,
        client: BirdBuddy,
        entry: ConfigEntry,
    ) -> None:
        self.client = client
        self.feeders = {}
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=POLLING_INTERVAL,
        )

    async def _process_feed(self, feed: list[FeedNode]) -> bool:
        """Attempt to process new feed items.

        There are some options for how we can process these:
        - If the sighting contains a recognized bird, we can finish it automatically
          using :func:`BirdBuddy.finish_postcard`.
        - For all new postcards, we can simply emit a HA event, and leave it up to
          the user's automations to finish them, however (and if) the user wants.
        """
        LOGGER.debug("Found feed items %s", feed)
        postcards = [
            node for node in feed if node.node_type == FeedNodeType.NewPostcard
        ]

        LOGGER.debug("Found postcards %s", postcards)
        for postcard in postcards:
            LOGGER.debug("A new postcard is ready to process: %s", postcard)
            if not self.hass.bus.async_listeners().get(EVENT_NEW_POSTCARD_SIGHTING):
                # if no one is listening, no sense in getting sighting data
                LOGGER.debug("No event listeners: skipping postcard conversion")
                continue

            # emit a new event with sighting data and postcard data
            # expose services that can:
            # 1. auto-collect a recognized bird
            # 2. manually assign a species
            # 3. auto-collect a best-guess species, using sightingReport confidence
            # 4. assign the sighting as "mystery visitor"
            # 5. all-in-one service that can choose the best option of 1, 3, or 4
            # Automations could use the sighting media URLs to do additional AI processing,
            # such as with Merlin or other AI classifiers, and then do #2 with the results.
            # If this is a viable option, we can supply a Recipe in docs to show how this could
            # be done. Similarly, we can supply some default blueprints to handle this with
            # user input.
            sighting = await self.client.sighting_from_postcard(postcard=postcard)
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
        try:
            await self.client.refresh()
            # refresh_feed() will return only items that are newer than the last seen timestamp
            # if we haven't seen a timestamp, it will return all items.
            feed = await self.client.refresh_feed()
            # Check for any new postcards that we can handle, and handle them:
            await self._process_feed(feed)
        except Exception as exc:
            raise UpdateFailed(exc) from exc

        if not self.client.feeders:
            raise UpdateFailed("No Feeders found")

        feeders = {id: BirdBuddyDevice(f) for (id, f) in self.client.feeders.items()}
        # pylint: disable=invalid-name
        for (i, f) in feeders.items():
            if i in self.feeders:
                self.feeders[i].update(f)
            else:
                self.feeders[i] = f
        return self.client

    async def handle_collect_postcard(self, data: dict[str, any]) -> bool:
        """Handles the `birdbuddy.collect_postcard` service call."""
        sighting = PostcardSighting(data["sighting"])
        postcard_id = data["postcard"]["id"]
        strategy = SightingFinishStrategy(data.get("strategy", "recognized"))
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
        )
        if success:
            LOGGER.info("Postcard collected to Media")
        else:
            # TODO: more info
            LOGGER.warning("Postcard could not be collected")
        return success
