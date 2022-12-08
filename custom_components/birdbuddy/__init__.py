"""The Bird Buddy integration."""
from __future__ import annotations

from birdbuddy.client import BirdBuddy

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import BirdBuddyDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Bird Buddy from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    client = BirdBuddy(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    coordinator = BirdBuddyDataUpdateCoordinator(hass, client, entry)

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
