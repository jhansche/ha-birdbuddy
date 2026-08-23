"""Tests for the Bird Buddy coordinator."""

import json
from unittest.mock import AsyncMock, MagicMock

from birdbuddy.exceptions import GraphqlError
from birdbuddy.feed import FeedNode
from birdbuddy.postcards import CollectedPostcard, PostcardAnalysis
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.birdbuddy.const import DOMAIN, EVENT_NEW_POSTCARD
from custom_components.birdbuddy.coordinator import BirdBuddyDataUpdateCoordinator

_ANALYSIS = PostcardAnalysis(
    {
        "id": "pc1",
        "feeder": {"__typename": "Feeder", "id": "feeder1"},
        "medias": [
            {
                "__typename": "MediaImage",
                "id": "m1",
                "createdAt": "2026-07-09T12:00:00.000Z",
                "thumbnailUrl": "https://example.invalid/t.jpg",
                "contentUrl": "https://example.invalid/c.jpg",
            }
        ],
        "sightingReportPreview": {
            "sightings": [
                {
                    "__typename": "SightingRecognizedBird",
                    "species": {"id": "s1", "name": "American Robin"},
                }
            ]
        },
    }
)


async def test_process_feed_fires_slim_event(hass):
    """_process_feed identifies a postcard and fires a slim event."""
    client = MagicMock()
    client.identify_postcard = AsyncMock(return_value=_ANALYSIS)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = BirdBuddyDataUpdateCoordinator(hass, client, entry)

    events = []
    hass.bus.async_listen(EVENT_NEW_POSTCARD, events.append)

    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc1"})
    await coordinator._process_feed([postcard])
    await hass.async_block_till_done()

    client.identify_postcard.assert_awaited_once_with(postcard)
    assert len(events) == 1
    data = events[0].data
    assert data["postcard_id"] == "pc1"
    assert data["feeder_id"] == "feeder1"
    assert data["species"] == [{"id": "s1", "name": "American Robin"}]
    assert data["media"]["contentUrl"] == "https://example.invalid/c.jpg"
    # Issue #78: the event must stay under HA's recorder size limit.
    assert len(json.dumps(data)) < 32768


async def test_process_feed_skips_without_listeners(hass):
    """With no event listeners, no identify call is made."""
    client = MagicMock()
    client.identify_postcard = AsyncMock(return_value=_ANALYSIS)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = BirdBuddyDataUpdateCoordinator(hass, client, entry)

    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc1"})
    await coordinator._process_feed([postcard])
    await hass.async_block_till_done()

    client.identify_postcard.assert_not_awaited()


async def test_a_rejected_postcard_leaves_the_poll_successful(hass):
    """A server error on one postcard leaves the poll and the rest intact.

    Issue #98 reported INTERNAL_SERVER_ERROR on the old sighting mutation
    taking every entity down with it, since the call sits inside the poll.
    """
    error = GraphqlError(
        {
            "message": "Internal server error.",
            "path": ["inferenceExternalPostcardReanalyze"],
            "extensions": {"code": "INTERNAL_SERVER_ERROR"},
        }
    )
    client = MagicMock()
    client.refresh = AsyncMock()
    client.feeders = {
        "feeder1": {"__typename": "FeederForOwner", "id": "feeder1", "name": "BB"}
    }
    client.refresh_feed = AsyncMock(
        return_value=[
            FeedNode({"__typename": "FeedItemNewPostcard", "id": "bad"}),
            FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc1"}),
        ]
    )
    client.identify_postcard = AsyncMock(side_effect=[error, _ANALYSIS])
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = BirdBuddyDataUpdateCoordinator(hass, client, entry)
    coordinator.first_update = False

    events = []
    hass.bus.async_listen(EVENT_NEW_POSTCARD, events.append)

    assert await coordinator._async_update_data() is client
    await hass.async_block_till_done()

    assert client.identify_postcard.await_count == 2
    assert len(events) == 1
    assert events[0].data["postcard_id"] == "pc1"


async def test_handle_collect_postcard(hass):
    """handle_collect_postcard calls the client with the id and share flag."""
    client = MagicMock()
    client.collect_postcard = AsyncMock(return_value=CollectedPostcard({"id": "pc1"}))
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = BirdBuddyDataUpdateCoordinator(hass, client, entry)

    result = await coordinator.handle_collect_postcard(
        {"postcard_id": "pc1", "share": True}
    )
    assert result is True
    client.collect_postcard.assert_awaited_once_with("pc1", share=True)
