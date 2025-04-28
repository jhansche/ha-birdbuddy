"""Helpers for managing recent visitors."""

from typing import TypeVar
from collections.abc import Callable

from birdbuddy.birds import Species
from birdbuddy.client import BirdBuddy
from birdbuddy.feed import FeedNodeType
from birdbuddy.feeder import Feeder
from birdbuddy.media import Media, is_media_expired
from birdbuddy.sightings import PostcardSighting

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CALLBACK_TYPE

from .const import EVENT_NEW_POSTCARD_SIGHTING, LOGGER
from .util import _find_media_with_species

_RecentVisitors = TypeVar("_RecentVisitors", bound="RecentVisitors")
type VisitorCallback = Callable[[_RecentVisitors], None]


class RecentVisitors:
    """Class to manage recent visitors to this Feeder."""

    def __init__(
        self,
        feeder: Feeder,
        client: BirdBuddy,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the recent visitors manager."""
        self.hass = hass
        self.client = client
        self.feeder = feeder
        self._listeners: set[VisitorCallback] = set()
        self._disposable: Callable[[], None] | None = None
        self._latest_media: Media | None = None
        self._latest_species: Species | None = None

    @property
    def latest_media(self) -> Media | None:
        """Return the latest media."""
        return self._latest_media

    @property
    def latest_species(self) -> Species | None:
        """Return the latest species."""
        return self._latest_species

    def register_callback(self, listener: VisitorCallback) -> CALLBACK_TYPE:
        """Register a callback to be called when a new visitor is detected."""
        if not self._listeners:
            self._disposable = self._start()
        if self._latest_media and not is_media_expired(
            self._latest_media.content_url or self._latest_media.thumbnail_url
        ):
            listener(self)
        self._listeners.add(listener)
        return lambda: self.unregister_callback(listener)

    def unregister_callback(self, listener: VisitorCallback) -> None:
        """Unregister a callback."""
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
        """Start listening for new postcards."""

        @callback
        def filter_my_postcards(event: Event) -> bool:
            data = event if callable(getattr(event, "get", None)) else event.data
            return self.feeder.id == (
                data.get("sighting", {}).get("feeder", {}).get("id")
            )

        LOGGER.info("Listening for new visitors to feeder %s", self.feeder.name)
        self.hass.add_job(self._update_latest_visitor)
        return self.hass.bus.async_listen(
            EVENT_NEW_POSTCARD_SIGHTING,
            self._on_new_postcard,
            event_filter=filter_my_postcards,
        )

    async def _update_latest_visitor(self) -> None:
        feed = await self.client.feed()

        items = feed.filter(
            of_type=[
                FeedNodeType.SpeciesSighting,
                FeedNodeType.SpeciesUnlocked,
                FeedNodeType.CollectedPostcard,
            ],
        )

        my_items = _find_media_with_species(self.feeder.id, items)

        if latest := max(my_items, default=None, key=lambda x: x.created_at):
            self._latest_media = Media(latest["media"])
            species = [Species(s) for s in latest.get("species", [])]
            self._latest_species = next(iter(species), None)
            LOGGER.debug(
                "Setting recent visitor on %s from feed: %s, %s: %s",
                self.feeder.name,
                self._latest_species.name,
                self._latest_media.created_at,
                self._latest_media.content_url,
            )

        if not self._latest_species:
            # Did not find media in the feed.
            c = await self.client.refresh_collections()
            c = [c for c in c.values() if c.feeder_name == self.feeder.name]
            if c := max(c, default=None, key=(lambda x: x.last_visit)):
                self._latest_species = c.species
                # TODO: not easy to fetch latest media that matches a feeder
                # c = await self.client.latest_collection_media(c.collection_id)
                # m = max(c.values(), default=None, key=(lambda x: x.created_at))
                # self._latest_media = m

                LOGGER.debug(
                    "Setting recent visitor on %s from collection: %s",
                    self.feeder.name,
                    self._latest_species.name,
                )

        # Notify listeners
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        """Notify listeners of the latest visitor."""
        for listener in self._listeners:
            listener(self)

    async def _on_new_postcard(self, event: Event | None = None) -> None:
        """Handle a new postcard sighting."""
        postcard = PostcardSighting(event.data["sighting"])

        assert postcard.report.sightings
        assert postcard.medias

        # media has created_at
        # but sightings[] does not.
        media = next(iter(postcard.medias), None)

        if media:
            self._latest_media = media

        if unlocked := [
            s for s in postcard.report.sightings if s.sighting_type.is_unlocked
        ]:
            # NOTE: this might not be correct - if one sighting has multiple recognized
            # species, and one unlocked species, it's highly probably that the one unlocked
            # species is a mis-identification!
            # It's a little unusual for a single sighting to contain multiple bird species.
            self._latest_species = unlocked[0].species
            LOGGER.debug(
                "Reporting recent visitor from unlocked: %s", self._latest_species.name
            )
        elif recognized := [
            s for s in postcard.report.sightings if s.sighting_type.is_recognized
        ]:
            # Next best, select a recognized species
            self._latest_species = recognized[0].species
            LOGGER.debug(
                "Reporting recent visitor from recognized: %s",
                self._latest_species.name,
            )
        elif guessable := [s for s in postcard.report.sightings if s.suggestions]:
            # Else, select one that has a list of suggestions
            suggested = guessable[0].suggestions[0]
            self._latest_species = suggested.species
            LOGGER.info(
                "Reporting recent visitor from unrecognized suggestion: %s",
                suggested.species.name,
            )
        else:
            # We don't know what it was. Instead of reporting a bogus "cannot decide"
            # type, just clear the value.
            self._latest_species = None
            LOGGER.info("Cannot decide species: %s", postcard.report.sightings[0])

        LOGGER.debug(
            "Setting recent visitor on %s from postcard: %s, %s: %s",
            self.feeder.name,
            self._latest_species.name,
            self._latest_media.created_at,
            self._latest_media.content_url,
        )

        self._notify_listeners()
