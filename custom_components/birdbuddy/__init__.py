"""The Bird Buddy integration."""
from __future__ import annotations

from birdbuddy.birds import PostcardSighting
from birdbuddy.client import BirdBuddy

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, LOGGER, SERVICE_SCHEMA_COLLECT_POSTCARD
from .coordinator import BirdBuddyDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Setup the integration"""
    # This will register the services even if there's no ConfigEntry yet...
    setup_services(hass)
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


def setup_services(hass: HomeAssistant) -> bool:
    """Register the BirdBuddy service(s)"""

    async def handle_collect_postcard(service: ServiceCall) -> None:
        sighting = PostcardSighting(service.data["sighting"])
        postcard_id = service.data["postcard"]["id"]
        LOGGER.warning("JHH: service called: %s", service.data)
        LOGGER.warning("JHH: service: id=%s, sighting=%s", postcard_id, sighting)
        # Now we can finish the postcard

    LOGGER.info("JHH: registering services")
    hass.services.async_register(
        DOMAIN,
        "collect_postcard",
        handle_collect_postcard,
        schema=SERVICE_SCHEMA_COLLECT_POSTCARD,
    )
