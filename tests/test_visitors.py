"""Tests for the recent-visitor postcard listener.

The event filter registered in RecentVisitors._start is worth exercising
through the real event bus: Home Assistant catches anything a filter raises
and skips the listener (see homeassistant/core.py, _async_dispatch), so a
filter that mishandles its argument drops postcards silently instead of
surfacing an error.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.birdbuddy.const import EVENT_NEW_POSTCARD_SIGHTING
from custom_components.birdbuddy.visitors import RecentVisitors

FEEDER_ID = "feeder-under-test"


@pytest.fixture(name="visitors")
def visitors_fixture(hass):
    """Return a RecentVisitors bound to FEEDER_ID with a stubbed client."""
    feeder = MagicMock()
    feeder.id = FEEDER_ID
    feeder.name = "Test Feeder"
    return RecentVisitors(feeder, MagicMock(), hass)


@pytest.mark.parametrize(
    ("fired_feeder_id", "expected_calls"),
    [(FEEDER_ID, 1), ("a-different-feeder", 0)],
    ids=["this feeder", "another feeder"],
)
async def test_event_filter_admits_only_this_feeder(
    hass,
    visitors,
    fired_feeder_id,
    expected_calls,
):
    """Postcards reach the handler only when the feeder id matches."""
    with (
        # Both stubs isolate the filter: the seeding job would call the API,
        # and the handler would parse a full PostcardSighting payload.
        patch.object(RecentVisitors, "_update_latest_visitor", AsyncMock()),
        patch.object(RecentVisitors, "_on_new_postcard", AsyncMock()) as handler,
    ):
        visitors.register_callback(lambda _visitors: None)
        await hass.async_block_till_done()

        hass.bus.async_fire(
            EVENT_NEW_POSTCARD_SIGHTING,
            {"sighting": {"feeder": {"id": fired_feeder_id}}},
        )
        await hass.async_block_till_done()

    assert handler.call_count == expected_calls
