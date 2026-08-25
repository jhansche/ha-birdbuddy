"""Tests for the Bird Buddy recent-visitor image entity."""

from unittest.mock import AsyncMock, MagicMock, patch

from birdbuddy.feeder import Feeder
from birdbuddy.media import Media

from custom_components.birdbuddy.device import BirdBuddyDevice
from custom_components.birdbuddy.image import BirdBuddyRecentVisitorImageEntity
from custom_components.birdbuddy.visitors import RecentVisitors

_MEDIA = {
    "__typename": "MediaImage",
    "id": "m1",
    "createdAt": "2026-07-09T12:00:00.000Z",
    "contentUrl": "https://example.invalid/c.jpg",
    "thumbnailUrl": "https://example.invalid/t.jpg",
}


def _image_entity(hass):
    """Build a recent-visitor image entity for the test feeder.

    Args:
        hass: The Home Assistant instance.

    Returns:
        The image entity bound to a mock coordinator.
    """
    device = BirdBuddyDevice({"__typename": "FeederForOwner", "id": "f1", "name": "BB"})
    return BirdBuddyRecentVisitorImageEntity(hass, device, MagicMock())


def test_image_returns_none(hass):
    """image() defers to URL-based delivery and returns no bytes."""
    assert _image_entity(hass).image() is None


def test_update_url_sets_image_fields(hass):
    """Unexpired media populates the URL, picture, and timestamp."""
    entity = _image_entity(hass)
    entity._update_url(Media(_MEDIA))
    assert entity._attr_image_url == "https://example.invalid/c.jpg"
    assert entity._attr_entity_picture == "https://example.invalid/c.jpg"
    assert entity._attr_image_last_updated is not None


def test_update_url_clears_expired_image(hass):
    """A previously set but now-expired URL is cleared."""
    entity = _image_entity(hass)
    entity._attr_image_url = "https://example.invalid/e.jpg?Expires=1"
    entity._update_url(None)
    assert entity._attr_image_url is None
    assert entity._attr_entity_picture is None


async def test_load_image_forces_jpeg_content_type(hass):
    """A fetched image is retagged as image/jpeg for Home Assistant."""
    entity = _image_entity(hass)
    response = MagicMock()
    response.content = b"bytes"
    with patch.object(entity, "_fetch_url", AsyncMock(return_value=response)):
        image = await entity._async_load_image_from_url("https://x/y.jpg")
    assert image is not None
    assert image.content == b"bytes"
    assert image.content_type == "image/jpeg"


async def test_load_image_returns_none_without_response(hass):
    """An empty fetch yields no image."""
    entity = _image_entity(hass)
    with patch.object(entity, "_fetch_url", AsyncMock(return_value=None)):
        assert await entity._async_load_image_from_url("https://x") is None


async def test_on_recent_visitor_updates_url(hass):
    """The recent-visitor listener refreshes the image URL."""
    entity = _image_entity(hass)
    visitors = RecentVisitors(Feeder({"id": "f1", "name": "BB"}), MagicMock(), hass)
    event = MagicMock()
    event.data = {"species": [{"id": "s1", "name": "Robin"}], "media": _MEDIA}
    await visitors._on_new_postcard(event)

    with patch.object(entity, "async_write_ha_state"):
        entity._on_recent_visitor(visitors)
    assert entity._attr_image_url == "https://example.invalid/c.jpg"
