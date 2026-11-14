"""The Bird Buddy integration."""

from __future__ import annotations

from birdbuddy.auth import AuthTokens
from birdbuddy.client import BirdBuddy
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.json import JsonValueType

from .archive import normalize_folder
from .const import (
    ATTR_FEEDER_ID,
    AUTH_EMAIL,
    AUTH_GOOGLE,
    CONF_ARCHIVE_FOLDER,
    CONF_AUTH_METHOD,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    LOGGER,
    SERVICE_ARCHIVE_HISTORY,
    SERVICE_COLLECT_POSTCARD,
    SERVICE_SCHEMA_ARCHIVE_HISTORY,
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

    async def save_tokens(tokens: AuthTokens) -> None:
        """Keep the rotated Bird Buddy refresh token with the config entry."""
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_REFRESH_TOKEN: tokens.refresh_token}
        )

    if entry.data.get(CONF_AUTH_METHOD) == AUTH_GOOGLE:
        client = BirdBuddy(
            refresh_token=entry.data[CONF_REFRESH_TOKEN], tokens_updated=save_tokens
        )
    else:
        client = BirdBuddy(
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
            refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
            tokens_updated=save_tokens,
        )
    client.language_code = hass.config.language
    coordinator = BirdBuddyDataUpdateCoordinator(hass, client, entry)

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the archive folder changes.

    Every entry update calls this, including the token rotation that
    ``save_tokens`` writes, so only a changed folder reloads.
    """
    coordinator: BirdBuddyDataUpdateCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    running = (
        str(coordinator.archive.folder) if coordinator and coordinator.archive else ""
    )
    if normalize_folder(entry.options.get(CONF_ARCHIVE_FOLDER)) != running:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Retain password entries and their entity identities when upgrading."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry, version=2, data={**entry.data, CONF_AUTH_METHOD: AUTH_EMAIL}
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

    async def handle_archive_history(service: ServiceCall) -> ServiceResponse:
        """Handle a ``birdbuddy.archive_history`` service call.

        Saves every collection and the postcards still in the feed, for each
        account that has an archive folder.

        Args:
            service: The service call.

        Returns:
            How many files were saved, per account.

        Raises:
            HomeAssistantError: If no account has an archive folder.
        """
        coordinators = [
            c
            for c in hass.data.get(DOMAIN, {}).values()
            if isinstance(c, BirdBuddyDataUpdateCoordinator) and c.archive
        ]
        if not coordinators:
            msg = "Set an archive folder in the Bird Buddy options first"
            raise HomeAssistantError(msg)
        response: dict[str, JsonValueType] = {}
        for c in coordinators:
            counts = await c.async_archive_history()
            response[c.config_entry.title or c.config_entry.entry_id] = dict(counts)
        return response

    hass.services.async_register(
        DOMAIN,
        SERVICE_ARCHIVE_HISTORY,
        handle_archive_history,
        schema=SERVICE_SCHEMA_ARCHIVE_HISTORY,
        supports_response=SupportsResponse.OPTIONAL,
    )
