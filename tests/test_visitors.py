"""Tests for driving the recent visitor from a postcard's own media.

The point of these is that none of them touch `sightingCreateFromPostcard`.
"""

from unittest.mock import MagicMock

from birdbuddy.feed import FeedNode

from custom_components.birdbuddy.visitors import RecentVisitors

FEEDER_ID = "feeder-1"
OTHER_FEEDER_ID = "feeder-2"

# Signed media URLs carry an Expires param. 4102444800 is 2100-01-01.
LIVE = "https://media.example.test/media/feeder/{f}/media/{m}/CONTENT.jpg?Expires=4102444800"
EXPIRED = "https://media.example.test/media/feeder/{f}/media/{m}/CONTENT.jpg?Expires=1000000000"


def _image(media_id: str, created_at: str, feeder_id: str = FEEDER_ID, url: str = LIVE):
    formatted = url.format(f=feeder_id, m=media_id)
    return {
        "id": media_id,
        "createdAt": created_at,
        "thumbnailUrl": formatted,
        "contentUrl": formatted,
        "__typename": "MediaImage",
    }


def _postcard(medias: list, feeder_id: str | None = FEEDER_ID) -> FeedNode:
    node = {
        "id": "postcard-1",
        "__typename": "FeedItemNewPostcard",
        "createdAt": "2026-08-11T13:19:52.956Z",
        "medias": medias,
    }
    if feeder_id is not None:
        node["feeder"] = {
            "id": feeder_id,
            "name": "Feeder",
            "__typename": "FeederForOwner",
        }
    return FeedNode(node)


def _visitors() -> RecentVisitors:
    feeder = MagicMock()
    feeder.id = FEEDER_ID
    feeder.name = "Feeder"
    return RecentVisitors(feeder, MagicMock(), MagicMock())


def test_media_taken_from_postcard_without_any_mutation():
    """The newest image on the postcard becomes the latest media."""
    visitors = _visitors()
    assert visitors.update_from_postcard(
        _postcard(
            [
                _image("older", "2026-08-11T12:24:19.693Z"),
                _image("newer", "2026-08-11T13:19:49.779Z"),
            ]
        )
    )
    assert visitors.latest_media is not None
    assert visitors.latest_media.id == "newer"


def test_older_postcard_does_not_replace_newer_media():
    """A postcard older than what we hold is ignored."""
    visitors = _visitors()
    visitors.update_from_postcard(_postcard([_image("newer", "2026-08-11T13:19:49.779Z")]))
    assert not visitors.update_from_postcard(
        _postcard([_image("older", "2026-08-11T12:24:19.693Z")])
    )
    assert visitors.latest_media.id == "newer"


def test_postcard_for_another_feeder_is_ignored():
    """Media belonging to a different feeder is never adopted."""
    visitors = _visitors()
    assert not visitors.update_from_postcard(
        _postcard(
            [_image("other", "2026-08-11T13:19:49.779Z", feeder_id=OTHER_FEEDER_ID)],
            feeder_id=OTHER_FEEDER_ID,
        )
    )
    assert visitors.latest_media is None


def test_feeder_matched_by_media_url_when_item_has_no_feeder():
    """With no feeder on the item, the signed media URL decides ownership."""
    visitors = _visitors()
    assert visitors.update_from_postcard(
        _postcard([_image("mine", "2026-08-11T13:19:49.779Z")], feeder_id=None)
    )
    assert visitors.latest_media.id == "mine"

    other = _visitors()
    assert not other.update_from_postcard(
        _postcard(
            [_image("theirs", "2026-08-11T13:19:49.779Z", feeder_id=OTHER_FEEDER_ID)],
            feeder_id=None,
        )
    )


def test_expired_media_is_not_adopted():
    """An already-expired signed URL is no use to the image entity."""
    visitors = _visitors()
    assert not visitors.update_from_postcard(
        _postcard([_image("stale", "2026-08-11T13:19:49.779Z", url=EXPIRED)])
    )
    assert visitors.latest_media is None


def test_postcard_without_images_is_ignored():
    """No media, or video only, means nothing to show."""
    visitors = _visitors()
    assert not visitors.update_from_postcard(_postcard([]))
    video = {
        "id": "vid",
        "createdAt": "2026-08-11T13:19:49.779Z",
        "thumbnailUrl": LIVE.format(f=FEEDER_ID, m="vid"),
        "__typename": "MediaVideo",
    }
    assert not visitors.update_from_postcard(_postcard([video]))
    assert visitors.latest_media is None


def test_listeners_notified_only_when_asked():
    """notify=False lets a bulk feed scan defer to a single notification."""
    visitors = _visitors()
    seen = []
    visitors.register_callback(seen.append)
    seen.clear()

    visitors.update_from_postcard(
        _postcard([_image("quiet", "2026-08-11T12:24:19.693Z")]), notify=False
    )
    assert seen == []

    visitors.update_from_postcard(_postcard([_image("loud", "2026-08-11T13:19:49.779Z")]))
    assert seen == [visitors]
