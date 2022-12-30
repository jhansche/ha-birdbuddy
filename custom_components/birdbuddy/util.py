"""Bird Buddy utilities"""

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import BirdBuddyDataUpdateCoordinator


def _find_coordinator_by_feeder(
    hass: HomeAssistant,
    feeder_id: str,
) -> BirdBuddyDataUpdateCoordinator:
    """Find the first matching coordinator containing this `feeder_id`."""
    coordinators: list[BirdBuddyDataUpdateCoordinator] = list(
        hass.data[DOMAIN].values()
    )
    return next((c for c in coordinators if feeder_id in c.feeders), None)
