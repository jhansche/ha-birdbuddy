"""Tests for the Bird Buddy media source."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from birdbuddy.media import Collection, Media
from homeassistant.components.media_player.const import MediaClass
from homeassistant.components.media_source.const import URI_SCHEME
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSourceItem,
)
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.birdbuddy.const import DOMAIN
from custom_components.birdbuddy.media_source import (
    BirdBuddyMediaSource,
    _best_timedelta_title,
    _media_class,
    _mime_type,
    async_get_media_source,
)

_IMG = {
    "__typename": "MediaImage",
    "id": "m1",
    "createdAt": "2026-07-09T12:00:00.000Z",
    "thumbnailUrl": "https://example.invalid/t1.jpg",
    "contentUrl": "https://example.invalid/c.jpg",
}
_VID = {
    "__typename": "MediaVideo",
    "id": "m2",
    "createdAt": "2026-07-09T12:00:00.000Z",
    "thumbnailUrl": "https://example.invalid/t2.jpg",
    "contentUrl": "https://example.invalid/v.mp4",
}
_NO_CONTENT = {
    "__typename": "MediaImage",
    "id": "m3",
    "createdAt": "2026-07-09T12:00:00.000Z",
    "thumbnailUrl": "https://example.invalid/t3.jpg",
}
_COL = {
    "id": "col1",
    "species": {"id": "s1", "name": "American Robin"},
    "visitsAllTime": 5,
    "visitLastTime": "2026-07-09T12:00:00.000Z",
    "coverCollectionMedia": {
        "feederName": "BB",
        "media": {
            "__typename": "MediaImage",
            "id": "cover",
            "createdAt": "2026-07-09T12:00:00.000Z",
            "thumbnailUrl": "https://example.invalid/cover.jpg",
            "contentUrl": "https://example.invalid/coverc.jpg",
        },
    },
}


def _make_source(hass, *, user=None, collections=None, collection_media=None):
    """Build a media source wired to a mock coordinator/client.

    Args:
        hass: The Home Assistant instance.
        user: The value for ``client.user``.
        collections: The ``client.collections`` mapping.
        collection_media: The mapping returned by ``client.collection``.

    Returns:
        A 3-tuple of (media source, client mock, config entry).
    """
    collections = collections or {}
    client = MagicMock()
    client.user = user
    client.collections = collections
    client.refresh_collections = AsyncMock(return_value=collections)
    client.collection = AsyncMock(return_value=collection_media or {})
    coordinator = MagicMock()
    coordinator.client = client
    entry = MockConfigEntry(domain=DOMAIN, title="My BB", entry_id="cfg")
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    return BirdBuddyMediaSource(hass), client, entry


def _item(hass: HomeAssistant, identifier: str) -> MediaSourceItem:
    """Build a media source item for an identifier.

    Args:
        hass: The Home Assistant instance.
        identifier: The media identifier to browse or resolve.

    Returns:
        A media source item targeting the identifier.
    """
    return MediaSourceItem(hass, DOMAIN, identifier, None)


def _child_content_ids(result: BrowseMediaSource) -> list[str]:
    """Return the ``media_content_id`` of each child node.

    Args:
        result: A browse result whose children to read.

    Returns:
        The child media content ids, in order.
    """
    assert result.children is not None
    return [child.media_content_id for child in result.children]


async def test_async_get_media_source(hass):
    """The setup helper returns the Bird Buddy media source."""
    source = await async_get_media_source(hass)
    assert isinstance(source, BirdBuddyMediaSource)


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("a#b#c", ("a", "b", "c")),
        ("a", ("a", None, None)),
        ("a#b#c#d", ("a", "b", "c#d")),
    ],
)
async def test_parse_identifier_pads_missing_parts(hass, identifier, expected):
    """Identifiers split into (config, collection, media), padded None."""
    source, _, _ = _make_source(hass)
    assert source._parse_identifier(identifier) == expected


@pytest.mark.parametrize(
    ("typename", "media_class", "mime"),
    [
        ("MediaImage", MediaClass.IMAGE, "image/jpeg"),
        ("MediaVideo", MediaClass.VIDEO, "video/mp4"),
    ],
)
def test_media_class_and_mime(typename, media_class, mime):
    """Images and videos map to their media class and MIME type."""
    media = Media({"__typename": typename})
    assert _media_class(media) is media_class
    assert _mime_type(media) == mime


def test_timedelta_recent_is_relative():
    """A sub-day delta renders as an 'x ago' relative string."""
    now = dt_util.utcnow()
    other = now - timedelta(minutes=5)
    assert _best_timedelta_title(other, now).endswith(" ago")


def test_timedelta_within_week_uses_weekday():
    """A 1-7 day delta renders as a weekday and time."""
    now = dt_util.utcnow()
    other = now - timedelta(days=3)
    assert "," in _best_timedelta_title(other, now)


def test_timedelta_future_and_old():
    """Future and over-a-year timestamps still render to a string."""
    now = dt_util.utcnow()
    future = now + timedelta(days=1)
    old = now - timedelta(days=800)
    assert _best_timedelta_title(future, now)
    assert _best_timedelta_title(old, now)


async def test_browse_root_lists_accounts(hass):
    """The root browse lists one node per configured account."""
    source, _, _ = _make_source(
        hass, user=SimpleNamespace(avatar_url="https://example.invalid/a.jpg")
    )
    result = await source.async_browse_media(_item(hass, ""))
    assert result.title == "Bird Buddy Media"
    assert _child_content_ids(result) == [f"{URI_SCHEME}{DOMAIN}/cfg"]


async def test_browse_account_lists_collections(hass):
    """Browsing an account node lists its collections."""
    source, _, _ = _make_source(
        hass,
        user=SimpleNamespace(avatar_url=None),
        collections={"col1": Collection(_COL)},
    )
    result = await source.async_browse_media(_item(hass, "cfg"))
    assert _child_content_ids(result) == [f"{URI_SCHEME}{DOMAIN}/cfg#col1"]
    assert result.children is not None
    assert result.children[0].title == "American Robin"


async def test_browse_collection_lists_media(hass):
    """Browsing a collection lists its media as playable children."""
    source, _, _ = _make_source(
        hass,
        collections={"col1": Collection(_COL)},
        collection_media={"m1": Media(_IMG), "m2": Media(_VID)},
    )
    result = await source.async_browse_media(_item(hass, "cfg#col1"))
    assert _child_content_ids(result) == [
        f"{URI_SCHEME}{DOMAIN}/cfg#col1#m1",
        f"{URI_SCHEME}{DOMAIN}/cfg#col1#m2",
    ]
    assert result.children is not None
    video_child = result.children[1]
    assert video_child.can_play is True
    assert video_child.media_content_type == "video/mp4"


async def test_browse_unknown_config_raises(hass):
    """An identifier for an unknown config entry raises MediaSourceError."""
    source, _, _ = _make_source(hass)
    with pytest.raises(MediaSourceError):
        await source.async_browse_media(_item(hass, "nope#col1"))


async def test_get_config_or_raise_missing(hass):
    """Resolving an unknown config id raises MediaSourceError."""
    source, _, _ = _make_source(hass)
    with pytest.raises(MediaSourceError):
        source._get_config_or_raise("missing")


async def test_resolve_media_returns_play_media(hass):
    """A complete identifier resolves to a playable content URL."""
    source, _, _ = _make_source(hass, collection_media={"m1": Media(_IMG)})
    result = await source.async_resolve_media(_item(hass, "cfg#col1#m1"))
    assert result.url == "https://example.invalid/c.jpg"
    assert result.mime_type == "image/jpeg"


async def test_resolve_media_incomplete_identifier(hass):
    """An identifier missing the collection/media parts is unresolvable."""
    source, _, _ = _make_source(hass)
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(_item(hass, "cfg"))


async def test_resolve_media_without_content_url(hass):
    """Media that carries no content URL is unresolvable."""
    source, _, _ = _make_source(hass, collection_media={"m3": Media(_NO_CONTENT)})
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(_item(hass, "cfg#col1#m3"))
