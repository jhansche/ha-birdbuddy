"""The Bird Buddy integration."""
from __future__ import annotations

from birdbuddy.client import BirdBuddy

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, LOGGER, SERVICE_SCHEMA_COLLECT_POSTCARD
from .coordinator import BirdBuddyDataUpdateCoordinator
from .util import _find_coordinator_by_feeder

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Setup the integration"""
    # This will register the services even if there's no ConfigEntry yet...
    _setup_services(hass)
    return True


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


def _setup_services(hass: HomeAssistant) -> bool:
    """Register the BirdBuddy service(s)"""

    async def handle_collect_postcard(service: ServiceCall) -> None:
        feeder_id = service.data["sighting"]["feeder"]["id"]
        coordinator = _find_coordinator_by_feeder(hass, feeder_id)
        if not coordinator:
            raise ValueError(f"Feeder with id '{feeder_id}' not found.")

        await coordinator.handle_collect_postcard(service.data)

    hass.services.async_register(
        DOMAIN,
        "collect_postcard",
        handle_collect_postcard,
        schema=SERVICE_SCHEMA_COLLECT_POSTCARD,
    )
