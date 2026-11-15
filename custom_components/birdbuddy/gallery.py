"""Find every Bird Buddy photo and video an account holds.

Two places hold them besides the new postcards:

- The gallery (``me.mediasOwned``): every photo and video the account owns,
  with its species, all the way back. Collected postcards land here, and so
  do visits that were opened in the app before Home Assistant saw them.
- The feed items that carry media: collected postcards, species sightings
  and unlocks, liked media and mystery visitors.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any

from birdbuddy.client import BirdBuddy
from birdbuddy.exceptions import UnexpectedResponseError
from birdbuddy.feed import FeedNode, FeedNodeType
from birdbuddy.media import Media

MYSTERY_VISITOR = "Mystery Visitor"
# The API returns an internal error for pages larger than 100.
PAGE_SIZE = 100

# A photo or video with the species names it shows.
type GalleryItem = tuple[list[str], Media]

OWNED_MEDIA = """
query meMediasOwned($first: Int, $after: String, $orderBy: MediasOwnedOrderByInput) {
  me {
    mediasOwned(first: $first, after: $after, orderBy: $orderBy) {
      edges {
        node {
          id
          isMysteryVisitor
          species {
            id
            name
            __typename
          }
          media {
            id
            createdAt
            thumbnailUrl
            ... on MediaImage {
              contentUrl(size: ORIGINAL)
              __typename
            }
            ... on MediaVideo {
              contentUrl(size: ORIGINAL)
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
      pageInfo {
        hasNextPage
        endCursor
        __typename
      }
      __typename
    }
    __typename
  }
}
""".strip()

# Feed item types whose nodes carry media.
MEDIA_FEED_TYPES = (
    FeedNodeType.CollectedPostcard,
    FeedNodeType.SpeciesSighting,
    FeedNodeType.SpeciesUnlocked,
    FeedNodeType.MediaLiked,
    FeedNodeType.MysteryVisitorNotRecognized,
    FeedNodeType.MysteryVisitorResolved,
)
_MYSTERY_FEED_TYPES = (
    FeedNodeType.MysteryVisitorNotRecognized,
    FeedNodeType.MysteryVisitorResolved,
)


def _names(species: Iterable[Any] | None) -> list[str]:
    """Pick the species names out of a list of species objects.

    Args:
        species: The species objects, or None.

    Returns:
        Their names, skipping any without one.
    """
    return [
        name for s in species or [] if isinstance(s, dict) and (name := s.get("name"))
    ]


def _gallery_item(node: dict[str, Any]) -> GalleryItem | None:
    """Turn one gallery entry into a photo or video with its species.

    Args:
        node: A ``CollectionMedia`` node.

    Returns:
        The species names and the media, or None if it has no usable media.
    """
    media = node.get("media")
    if not isinstance(media, dict) or not media.get("id"):
        return None
    names = _names(node.get("species"))
    if not names and node.get("isMysteryVisitor"):
        names = [MYSTERY_VISITOR]
    return names, Media(media)


async def async_gallery_pages(client: BirdBuddy) -> AsyncIterator[list[GalleryItem]]:
    """Page through the account's gallery, newest first.

    The library has no call for the gallery, so this sends the query through
    its request method, which handles sign-in and token refresh.

    Args:
        client: The signed-in Bird Buddy client.

    Yields:
        Each page's photos and videos.

    Raises:
        UnexpectedResponseError: If a page isn't shaped as expected.
    """
    after: str | None = None
    seen: set[str] = set()
    while True:
        variables: dict[str, Any] = {
            "first": PAGE_SIZE,
            "orderBy": {"createdAt": "DESC"},
        }
        if after is not None:
            # The API errors on an explicit ``after: null``.
            variables["after"] = after
        data = await client._make_request(query=OWNED_MEDIA, variables=variables)
        try:
            connection = data["me"]["mediasOwned"]
            edges = connection["edges"]
        except (KeyError, TypeError) as err:
            raise UnexpectedResponseError(data) from err
        yield [
            item
            for edge in edges
            if isinstance(edge, dict)
            and isinstance(node := edge.get("node"), dict)
            and (item := _gallery_item(node))
        ]
        page_info = connection.get("pageInfo") or {}
        cursor = page_info.get("endCursor")
        if not page_info.get("hasNextPage") or not cursor or cursor in seen:
            return
        seen.add(cursor)
        after = cursor


def feed_item_media(node: FeedNode) -> list[GalleryItem]:
    """Return the photos and videos a feed item carries.

    Args:
        node: A feed node.

    Returns:
        Each media item with its species names; empty for feed items
        without media.
    """
    if node.node_type not in MEDIA_FEED_TYPES:
        return []
    if node.node_type == FeedNodeType.CollectedPostcard:
        names = _names(node.get("species"))
        medias = node.get("medias") or []
    else:
        collection = node.get("collection") or {}
        species = collection.get("species") if isinstance(collection, dict) else None
        names = _names([species])
        medias = [node.get("media")]
    if not names and (
        node.node_type in _MYSTERY_FEED_TYPES or node.get("hasMysteryVisitor")
    ):
        names = [MYSTERY_VISITOR]
    return [(names, Media(m)) for m in medias if isinstance(m, dict) and m.get("id")]


async def async_feed_media(client: BirdBuddy) -> list[GalleryItem]:
    """Collect the media from every media-carrying item in the whole feed.

    Args:
        client: The signed-in Bird Buddy client.

    Returns:
        Each media item with its species names.
    """
    items: list[GalleryItem] = []
    after: str | None = None
    seen: set[str] = set()
    while True:
        feed = await client.feed(first=PAGE_SIZE, after=after)
        for node in feed.nodes:
            items += feed_item_media(node)
        cursor = feed.page_end_cursor
        has_next = (feed.get("pageInfo") or {}).get("hasNextPage")
        if not has_next or not cursor or cursor in seen:
            return items
        seen.add(cursor)
        after = cursor
