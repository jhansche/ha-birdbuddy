"""Tests for the Bird Buddy recent-visitor sensor."""

from unittest.mock import MagicMock, patch

from birdbuddy.feeder import Feeder

from custom_components.birdbuddy.device import BirdBuddyDevice
from custom_components.birdbuddy.sensor import BirdBuddyRecentVisitorEntity
from custom_components.birdbuddy.visitors import RecentVisitors

_ROBIN = {"id": "s1", "name": "American Robin"}
_M1 = {
    "__typename": "MediaImage",
    "contentUrl": "https://example.invalid/c1.jpg",
    "thumbnailUrl": "https://example.invalid/t1.jpg",
    "createdAt": "2026-07-09T12:00:00.000Z",
}
_M2 = {
    "__typename": "MediaImage",
    "contentUrl": "https://example.invalid/c2.jpg",
    "thumbnailUrl": "https://example.invalid/t2.jpg",
    "createdAt": "2026-07-10T12:00:00.000Z",
}


def _postcard_event(species, media):
    """Build a new-postcard event with the given species and media.

    Args:
        species: The recognized-species list for the event payload.
        media: The primary media mapping, or None.

    Returns:
        An event whose ``data`` carries the slim postcard payload.
    """
    event = MagicMock()
    event.data = {
        "postcard_id": "pc1",
        "feeder_id": "feeder1",
        "species": species,
        "media": media,
    }
    return event


def _recent_entity():
    """Build a recent-visitor entity for the test feeder.

    Returns:
        A recent-visitor sensor bound to a mock coordinator.
    """
    device = BirdBuddyDevice(
        {"__typename": "FeederForOwner", "id": "feeder1", "name": "BB"}
    )
    return BirdBuddyRecentVisitorEntity(device, MagicMock())


async def test_recent_visitor_state_tracks_its_picture(hass):
    """Issue #95: state and picture advance together, never lagging.

    A later species-less detection must clear the stale species along with
    the advancing picture, rather than freezing the previous species.
    """
    feeder = Feeder({"id": "feeder1", "name": "Bird Buddy"})
    visitors = RecentVisitors(feeder, MagicMock(), hass)
    entity = _recent_entity()

    with patch.object(entity, "async_write_ha_state"):
        await visitors._on_new_postcard(_postcard_event([_ROBIN], _M1))
        entity._on_recent_visitor(visitors)
        assert entity.native_value == "American Robin"
        assert entity.entity_picture == "https://example.invalid/c1.jpg"

        await visitors._on_new_postcard(_postcard_event([], _M2))
        entity._on_recent_visitor(visitors)
        assert entity.native_value is None
        assert entity.entity_picture == "https://example.invalid/c2.jpg"
