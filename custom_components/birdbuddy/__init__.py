"""The Bird Buddy integration."""
from __future__ import annotations

from birdbuddy.client import BirdBuddy

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    LOGGER,
    SERVICE_COLLECT_POSTCARD,
    SERVICE_SCHEMA_COLLECT_POSTCARD,
)
from .coordinator import BirdBuddyDataUpdateCoordinator
from .util import _feeder_id_for_device, _find_coordinator_by_feeder

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
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

    if entry.title != client.user.name:
        entry.title = client.user.name
        hass.config_entries.async_update_entry(
            entry,
            title=client.user.name,
            options={},
            unique_id=entry[CONF_EMAIL],
        )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    async_cleanup_devices(hass, entry)

    return True


@callback
def async_cleanup_devices(hass: HomeAssistant, entry: ConfigEntry):
    """Clean up old devices no longer associated with the account."""
    coordinator: BirdBuddyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    if not coordinator:
        LOGGER.warning(
            "Unable to clean up devices for Bird Buddy entry '%s'", entry.title
        )
        return

    reg = dr.async_get(hass)
    entries = dr.async_entries_for_config_entry(reg, entry.entry_id)
    for dev in entries:
        feeder_id = _feeder_id_for_device(hass, dev.id)
        if feeder_id not in coordinator.client.feeders:
            # Note: if there were any device triggers, those automations will
            # become disabled automatically.
            LOGGER.info("Removing orphaned device: %s (%s)", dev.name, dev.id)
            reg.async_remove_device(dev.id)


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
        coordinator: BirdBuddyDataUpdateCoordinator
        coordinator = _find_coordinator_by_feeder(hass, feeder_id)
        if not coordinator:
            # We could not find this specific feeder. This could mean that the Feeder has been
            # factory reset and re-paired, but the Feed belongs to the same user. If we assume
            # that, we can move on to find the next available Coordinator, even if it might not
            # have the same feeder id anymore.
            coordinator = next(iter(hass.data[DOMAIN].values()))
            if coordinator:
                LOGGER.warning(
                    "Feeder with id '%s' not found: trying %s",
                    feeder_id,
                    list(coordinator.feeders.keys()),
                )
            else:
                raise ValueError("Feeder with id '{feeder_id}' not found.")

        await coordinator.handle_collect_postcard(service.data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_COLLECT_POSTCARD,
        handle_collect_postcard,
        schema=SERVICE_SCHEMA_COLLECT_POSTCARD,
    )
