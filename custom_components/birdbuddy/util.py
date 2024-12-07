"""Bird Buddy utilities"""

from birdbuddy.feed import FeedNode

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
)

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


def _feeder_id_for_device(
    hass: HomeAssistant,
    device_id: str,
) -> str:
    """Return the Bird Buddy Feeder ID for this `device_id`."""
    dev_reg = dr.async_get(hass)
    if not (device_entry := dev_reg.async_get(device_id)):
        raise ValueError(f"Device ID {device_id} not found")
    return next((id for (d, id) in device_entry.identifiers if d == DOMAIN))


def _find_coordinator_by_device(
    hass: HomeAssistant,
    device_id: str,
) -> BirdBuddyDataUpdateCoordinator:
    """Find the first coordinator for this `device_id`."""
    dev_reg = dr.async_get(hass)
    if not (device_entry := dev_reg.async_get(device_id)):
        raise ValueError(f"Device ID {device_id} not found")

    config_entry_ids = device_entry.config_entries
    entry = next(
        (
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id in config_entry_ids
        )
    )

    if entry and entry.state != ConfigEntryState.LOADED:
        raise ValueError(f"Device {device_id} config entry is not loaded")
    if entry is None or entry.entry_id not in hass.data[DOMAIN]:
        raise ValueError(
            f"Device {device_id} is not from an existing birdbuddy config entry"
        )
    coordinator: BirdBuddyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    return coordinator


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
