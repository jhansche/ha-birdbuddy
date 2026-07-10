"""Bird Buddy select entities."""

from __future__ import annotations

from birdbuddy.exceptions import GraphqlError
from birdbuddy.feeder import PowerProfile
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BirdBuddyDataUpdateCoordinator
from .device import BirdBuddyDevice
from .entity import BirdBuddyMixin


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bird Buddy select entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback used to register the new entities.
    """
    coordinator: BirdBuddyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    async_add_entities(BirdBuddyPowerProfileSelector(f, coordinator) for f in feeders)


class BirdBuddyPowerProfileSelector(BirdBuddyMixin, SelectEntity):
    """Select the feeder's power profile."""

    _attr_has_entity_name = True
    _attr_name = "Power Profile"
    _attr_icon = "mdi:power-settings"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "power_profile"
    _attr_options = [
        "frenzy_mode",
        "standard_mode",
        "power_saver_mode",
    ]
    # TODO(jhansche): remove once it is verified working
    _attr_attribution = "(This entity is incubating)"

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the power-profile selector.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-power-profile"

    @property
    def current_option(self) -> str | None:
        """Return the currently selected power profile.

        Returns:
            The active power profile as a lowercase string.
        """
        return self.feeder.power_profile.value.lower()

    @property
    def available(self) -> bool:
        """Return whether the selector is available.

        Returns:
            True when the base entity is available and the feeder is owned by
            this account; only owners may change the power profile.
        """
        return super().available and self.feeder.is_owner

    async def async_select_option(self, option: str) -> None:
        """Set the feeder's power profile.

        Args:
            option: The profile to select, one of ``_attr_options``.

        Raises:
            HomeAssistantError: If the Bird Buddy API rejects the change.
        """
        profile = PowerProfile(option.upper())
        try:
            result = await self.coordinator.client.set_power_profile(
                self.feeder,
                profile,
            )
            if result:
                self.feeder.update(result)
                self.async_write_ha_state()
        except GraphqlError as err:
            msg = f"Cannot set Power Profile for {self.entity_id} to {profile}: {err}"
            raise HomeAssistantError(msg) from err
