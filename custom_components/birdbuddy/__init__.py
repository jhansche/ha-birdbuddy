"""The Bird Buddy integration."""

from __future__ import annotations

from birdbuddy.client import BirdBuddy
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_FEEDER_ID,
    DOMAIN,
    LOGGER,
    SERVICE_COLLECT_POSTCARD,
    SERVICE_SCHEMA_COLLECT_POSTCARD,
)
from .coordinator import BirdBuddyDataUpdateCoordinator
from .hass_util import _find_coordinator_by_feeder

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration from YAML.

    Args:
        hass: The Home Assistant instance.
        config: The parsed Home Assistant configuration.

    Returns:
        True once the services have been registered.
    """
    # This will register the services even if there's no ConfigEntry yet...
    _setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Bird Buddy from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.

    Returns:
        True once the coordinator and platforms are set up.
    """
    hass.data.setdefault(DOMAIN, {})
    client = BirdBuddy(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    client.language_code = hass.config.language
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
    """Unload a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being unloaded.

    Returns:
        True if every platform unloaded successfully.
    """
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Allow a device to be removed from a config entry.

    Args:
        hass: The Home Assistant instance.
        config_entry: The config entry the device belongs to.
        device_entry: The device being removed.

    Returns:
        True to always allow the device to be removed.
    """
    return True


def _setup_services(hass: HomeAssistant) -> None:
    """Register the Bird Buddy service(s).

    Args:
        hass: The Home Assistant instance.
    """

    async def handle_collect_postcard(service: ServiceCall) -> None:
        """Handle a ``birdbuddy.collect_postcard`` service call.

        Args:
            service: The service call carrying the postcard data.

        Raises:
            ValueError: If no coordinator is available for the feeder.
        """
        feeder_id = service.data.get(ATTR_FEEDER_ID)
        coordinator: BirdBuddyDataUpdateCoordinator | None = None
        if feeder_id:
            coordinator = _find_coordinator_by_feeder(hass, feeder_id)

        if coordinator is None:
            # Either the call named no feeder, which the service schema
            # allows, or it named one this account no longer holds: a feeder
            # factory reset and re-paired keeps its owner and takes a new id.
            # Both resolve to the first configured account.
            coordinator = next(iter(hass.data.get(DOMAIN, {}).values()), None)
            if coordinator is None:
                msg = f"Feeder with id '{feeder_id}' not found."
                raise ValueError(msg)
            if feeder_id:
                LOGGER.warning(
                    "Feeder with id '%s' not found: trying %s",
                    feeder_id,
                    list(coordinator.feeders.keys()),
                )

        await coordinator.handle_collect_postcard(service.data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_COLLECT_POSTCARD,
        handle_collect_postcard,
        schema=SERVICE_SCHEMA_COLLECT_POSTCARD,
    )
