"""Data Update coordinator for ZAMG weather data."""
from __future__ import annotations
from datetime import datetime

from birdbuddy.client import BirdBuddy

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

    _last_feed_item: datetime | None

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

    async def _process_feed(self, feed: dict) -> bool:
        """Attempt to process new feed items.

        There are some options for how we can process these:
        - If the sighting contains a recognized bird, we can finish it automatically
          using :func:`BirdBuddy.finish_postcard`.
        - For all new postcards, we can simply emit a HA event, and leave it up to
          the user's automations to finish them, however (and if) the user wants.
        """
        postcards = [
            edge["node"]
            for edge in feed["edges"]
            if edge["node"]["__typename"] == "FeedItemNewPostcard"
        ]
        for postcard in postcards:
            LOGGER.debug("A new postcard is ready to process: %s", postcard)
            if not self.hass.bus.listeners.get(EVENT_NEW_POSTCARD_SIGHTING):
                # if no one is listening, no sense in getting sighting data
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
            sighting = self.client.sighting_from_postcard(postcard_id=postcard["id"])
            data = {
                "postcard": postcard,
                "sighting": sighting,
            }
            self.hass.bus.fire(
                event_type=EVENT_NEW_POSTCARD_SIGHTING,
                event_data=data,
                origin=EventOrigin.remote,
            )

    async def _async_update_data(self) -> BirdBuddy:
        try:
            await self.client.refresh()
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
