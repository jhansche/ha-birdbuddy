"""Bird Buddy utilities."""

from birdbuddy.feed import FeedNode


def _find_media_with_species(feeder_id: str, items: list[FeedNode]) -> list[FeedNode]:
    """Filter feed items to this feeder's image sightings with a species.

    Args:
        feeder_id: The feeder id to match against media thumbnail URLs.
        items: The feed nodes to filter.

    Returns:
        The matching feed nodes, each augmented with a ``media`` key holding
        the first matching image (or None).
    """
    return [
        item | {"media": next(iter(medias), None)}
        for item in items
        if item
        and (
            medias := [
                m
                for m in item.get("medias", [])
                if m.get("__typename") == "MediaImage"
                and feeder_id in m.get("thumbnailUrl", "")
            ]
        )
        and item.get("species", None)
    ]
