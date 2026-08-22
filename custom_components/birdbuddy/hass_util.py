"""Helpers for resolving Home Assistant devices to Bird Buddy feeders."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import BirdBuddyDataUpdateCoordinator


def _feeder_id_for_device(
    hass: HomeAssistant,
    device_id: str,
) -> str:
    """Return the Bird Buddy feeder id for a device registry id.

    Args:
        hass: The Home Assistant instance.
        device_id: The device registry id to resolve.

    Returns:
        The Bird Buddy feeder id recorded in the device's identifiers.

    Raises:
        ValueError: If no device with the given id exists.
    """
    dev_reg = dr.async_get(hass)
    if not (device_entry := dev_reg.async_get(device_id)):
        msg = f"Device ID {device_id} not found"
        raise ValueError(msg)
    return next(id for (d, id) in device_entry.identifiers if d == DOMAIN)


def _find_coordinator_by_feeder(
    hass: HomeAssistant,
    feeder_id: str | None,
) -> BirdBuddyDataUpdateCoordinator | None:
    """Find the first coordinator that owns a given feeder.

    Args:
        hass: The Home Assistant instance.
        feeder_id: The Bird Buddy feeder id to look for.

    Returns:
        The first coordinator tracking the feeder, or None if none does.
    """
    # Services register in async_setup, so this can run before any config
    # entry has populated hass.data[DOMAIN].
    coordinators: list[BirdBuddyDataUpdateCoordinator] = list(
        hass.data.get(DOMAIN, {}).values()
    )
    return next((c for c in coordinators if feeder_id in c.feeders), None)


def _find_coordinator_by_device(
    hass: HomeAssistant,
    device_id: str,
) -> BirdBuddyDataUpdateCoordinator:
    """Find the coordinator backing a device registry id.

    Args:
        hass: The Home Assistant instance.
        device_id: The device registry id to resolve.

    Returns:
        The coordinator for the device's loaded config entry.

    Raises:
        ValueError: If the device is unknown, its config entry is not
            loaded, or it does not belong to a Bird Buddy config entry.
    """
    dev_reg = dr.async_get(hass)
    if not (device_entry := dev_reg.async_get(device_id)):
        msg = f"Device ID {device_id} not found"
        raise ValueError(msg)

    config_entry_ids = device_entry.config_entries
    # Default to None so a device belonging to some other integration raises
    # the documented ValueError below instead of StopIteration.
    entry = next(
        (
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id in config_entry_ids
        ),
        None,
    )

    if entry is not None and entry.state != ConfigEntryState.LOADED:
        msg = f"Device {device_id} config entry is not loaded"
        raise ValueError(msg)
    if entry is None or entry.entry_id not in hass.data.get(DOMAIN, {}):
        msg = f"Device {device_id} is not from an existing birdbuddy config entry"
        raise ValueError(msg)
    coordinator: BirdBuddyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    return coordinator
