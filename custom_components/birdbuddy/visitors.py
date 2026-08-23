"""Helpers for managing recent visitors."""

from collections.abc import Callable, Mapping
from typing import Any

from birdbuddy.birds import Species
from birdbuddy.client import BirdBuddy
from birdbuddy.feed import FeedNodeType
from birdbuddy.feeder import Feeder
from birdbuddy.media import Media, is_media_expired
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback

from .const import ATTR_FEEDER_ID, ATTR_MEDIA, ATTR_SPECIES, EVENT_NEW_POSTCARD, LOGGER
from .util import _find_media_with_species

type VisitorCallback = Callable[[RecentVisitors], None]


class RecentVisitors:
    """Class to manage recent visitors to this Feeder."""

    def __init__(
        self,
        feeder: Feeder,
        client: BirdBuddy,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the recent visitors manager.

        Args:
            feeder: The feeder whose visitors are tracked.
            client: The authenticated Bird Buddy API client.
            hass: The Home Assistant instance.
        """
        self.hass = hass
        self.client = client
        self.feeder = feeder
        self._listeners: set[VisitorCallback] = set()
        self._disposable: Callable[[], None] | None = None
        self._latest_media: Media | None = None
        self._latest_species: Species | None = None

    @property
    def latest_media(self) -> Media | None:
        """Return the latest visitor media.

        Returns:
            The most recent media, or None if none has been recorded.
        """
        return self._latest_media

    @property
    def latest_species(self) -> Species | None:
        """Return the latest visitor species.

        Returns:
            The most recent species, or None if none has been recorded.
        """
        return self._latest_species

    def register_callback(self, listener: VisitorCallback) -> CALLBACK_TYPE:
        """Register a callback fired when a new visitor is detected.

        Starts listening on the first registration and immediately notifies
        the listener if there is already unexpired media.

        Args:
            listener: The callback to invoke on each new visitor.

        Returns:
            A callable that unregisters the listener when called.
        """
        if not self._listeners:
            self._disposable = self._start()
        if self._latest_media and not is_media_expired(
            self._latest_media.content_url or self._latest_media.thumbnail_url
        ):
            listener(self)
        self._listeners.add(listener)
        return lambda: self.unregister_callback(listener)

    def unregister_callback(self, listener: VisitorCallback) -> None:
        """Unregister a callback, stopping listening once none remain.

        Args:
            listener: The previously registered callback to remove.
        """
        self._listeners.remove(listener)
        if not self._listeners:
            self._stop()

    def _stop(self) -> None:
        """Stop listening for new postcards."""
        if self._disposable:
            self._disposable()
            self._disposable = None
        LOGGER.info("Stopped listening for new visitors to feeder %s", self.feeder.name)

    def _start(self) -> Callable[[], None]:
        """Start listening for new postcards.

        Returns:
            A callable that removes the event listener when called.
        """

        @callback
        def filter_my_postcards(event_data: Mapping[str, Any]) -> bool:
            """Return whether an event belongs to this feeder.

            Args:
                event_data: The fired event's data payload.

            Returns:
                True if the event's feeder id matches this feeder.
            """
            return self.feeder.id == event_data.get(ATTR_FEEDER_ID)

        LOGGER.info("Listening for new visitors to feeder %s", self.feeder.name)
        self.hass.async_create_task(self._update_latest_visitor())
        return self.hass.bus.async_listen(
            EVENT_NEW_POSTCARD,
            self._on_new_postcard,
            event_filter=filter_my_postcards,
        )

    async def _update_latest_visitor(self) -> None:
        """Seed the latest visitor from the feed or the collections."""
        feed = await self.client.feed()

        items = feed.filter(
            of_type=[
                FeedNodeType.SpeciesSighting,
                FeedNodeType.SpeciesUnlocked,
                FeedNodeType.CollectedPostcard,
            ],
        )

        my_items = _find_media_with_species(self.feeder.id, items)

        dated = [
            (created, item)
            for item in my_items
            if (created := item.created_at) is not None
        ]
        if dated:
            latest = max(dated, key=lambda pair: pair[0])[1]
            media = Media(latest["media"])
            self._latest_media = media
            species = [Species(s) for s in latest.get("species", [])]
            self._latest_species = next(iter(species), None)
            LOGGER.debug(
                "Setting recent visitor on %s from feed: %s, %s: %s",
                self.feeder.name,
                (
                    self._latest_species.name
                    if self._latest_species
                    else "Unknown species"
                ),
                media.created_at,
                media.content_url,
            )

        if not self._latest_species:
            # Did not find media in the feed.
            c = await self.client.refresh_collections()
            c = [c for c in c.values() if c.feeder_name == self.feeder.name]
            if (c := max(c, default=None, key=lambda x: x.last_visit)) and (
                species := c.species
            ):
                self._latest_species = species
                # TODO(jhansche): fetching the latest media that matches a
                # feeder from the collection is not straightforward.
                LOGGER.debug(
                    "Setting recent visitor on %s from collection: %s",
                    self.feeder.name,
                    species.name,
                )

        # Notify listeners
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        """Notify listeners of the latest visitor."""
        for listener in self._listeners:
            listener(self)

    async def _on_new_postcard(self, event: Event) -> None:
        """Handle a new-postcard event.

        The backend recognizes the species server-side, so the event carries
        the recognized species and primary media directly.

        Args:
            event: The ``birdbuddy_new_postcard`` event.
        """
        media = event.data.get(ATTR_MEDIA)
        species = event.data.get(ATTR_SPECIES) or []
        if not media and not species:
            LOGGER.debug("Postcard has no media or species; skipping")
            return

        # Rebuild the library models from the slim payload; set both together
        # so the recent-visitor state never lags its picture.
        self._latest_media = Media(media) if media else None
        self._latest_species = Species(species[0]) if species else None

        LOGGER.debug(
            "Setting recent visitor on %s from postcard: %s, %s",
            self.feeder.name,
            self._latest_species.name if self._latest_species else None,
            self._latest_media.content_url if self._latest_media else None,
        )
        self._notify_listeners()
