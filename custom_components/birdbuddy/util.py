"""Bird Buddy utilities"""

from birdbuddy.feed import FeedNode


def _find_media_with_species(feeder_id: str, items: list[FeedNode]) -> list[FeedNode]:
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
