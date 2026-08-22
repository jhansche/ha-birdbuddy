"""Tests for the Bird Buddy recent-visitors tracker.

The event filter registered in RecentVisitors._start is worth exercising
through the real event bus: Home Assistant catches anything a filter raises
and skips the listener (see homeassistant/core.py, _async_dispatch), so a
filter that mishandles its argument drops postcards silently instead of
surfacing an error.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from birdbuddy.feeder import Feeder
import pytest

from custom_components.birdbuddy.const import EVENT_NEW_POSTCARD
from custom_components.birdbuddy.visitors import RecentVisitors

FEEDER_ID = "feeder1"


def _visitors(hass):
    feeder = Feeder({"id": FEEDER_ID, "name": "Bird Buddy"})
    return RecentVisitors(feeder, MagicMock(), hass)


@pytest.mark.parametrize(
    ("fired_feeder_id", "expected_calls"),
    [(FEEDER_ID, 1), ("a-different-feeder", 0)],
    ids=["this feeder", "another feeder"],
)
async def test_event_filter_admits_only_this_feeder(
    hass,
    fired_feeder_id,
    expected_calls,
):
    """Postcards reach the handler only when the feeder id matches."""
    visitors = _visitors(hass)
    with (
        # Both stubs isolate the filter: the seeding job would call the API,
        # and the handler would rebuild the library models.
        patch.object(RecentVisitors, "_update_latest_visitor", AsyncMock()),
        patch.object(RecentVisitors, "_on_new_postcard", AsyncMock()) as handler,
    ):
        visitors.register_callback(lambda _visitors: None)
        await hass.async_block_till_done()

        hass.bus.async_fire(
            EVENT_NEW_POSTCARD,
            {"postcard_id": "pc1", "feeder_id": fired_feeder_id},
        )
        await hass.async_block_till_done()

    assert handler.call_count == expected_calls


async def test_on_new_postcard_sets_latest(hass):
    """_on_new_postcard rebuilds media and species from the slim payload."""
    visitors = _visitors(hass)
    event = MagicMock()
    event.data = {
        "postcard_id": "pc1",
        "feeder_id": FEEDER_ID,
        "species": [{"id": "s1", "name": "American Robin"}],
        "media": {
            "__typename": "MediaImage",
            "contentUrl": "https://example.invalid/c.jpg",
            "thumbnailUrl": "https://example.invalid/t.jpg",
            "createdAt": "2026-07-09T12:00:00.000+0000",
        },
    }
    await visitors._on_new_postcard(event)

    assert visitors.latest_species is not None
    assert visitors.latest_species.name == "American Robin"
    assert visitors.latest_media is not None
    assert visitors.latest_media.content_url == "https://example.invalid/c.jpg"


async def test_on_new_postcard_without_data_is_ignored(hass):
    """A postcard with neither media nor species leaves the state unset."""
    visitors = _visitors(hass)
    event = MagicMock()
    event.data = {
        "postcard_id": "pc1",
        "feeder_id": FEEDER_ID,
        "species": [],
        "media": None,
    }
    await visitors._on_new_postcard(event)

    assert visitors.latest_media is None
    assert visitors.latest_species is None
