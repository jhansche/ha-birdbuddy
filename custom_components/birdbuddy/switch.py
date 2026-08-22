"""Bird Buddy switches."""

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
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
    """Set up the Bird Buddy switch entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback used to register the new entities.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    feeders = coordinator.feeders.values()
    entities = []
    entities.extend([BirdBuddyAudioSwitch(f, coordinator) for f in feeders])
    entities.extend([BirdBuddyOffGridSwitch(f, coordinator) for f in feeders])
    async_add_entities(entities)


class BirdBuddyOffGridSwitch(BirdBuddyMixin, SwitchEntity):
    """Toggle the feeder's off-grid mode."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Off-Grid"
    _attr_has_entity_name = True
    coordinator: BirdBuddyDataUpdateCoordinator

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the off-grid switch.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-offgrid"

    @property
    def available(self) -> bool:
        """Return whether the switch is available.

        Returns:
            True when the base entity is available and the feeder is owned by
            this account; only owners may toggle off-grid mode.
        """
        return super().available and self.feeder.is_owner

    @property
    def is_on(self) -> bool:
        """Return whether the feeder is in off-grid mode.

        Returns:
            True when the feeder is off-grid.
        """
        return self.feeder.is_off_grid

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable off-grid mode.

        Args:
            **kwargs: Additional Home Assistant turn-on options (unused).
        """
        result = await self.coordinator.client.toggle_off_grid(self.feeder, True)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable off-grid mode.

        Args:
            **kwargs: Additional Home Assistant turn-off options (unused).
        """
        result = await self.coordinator.client.toggle_off_grid(self.feeder, False)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()


class BirdBuddyAudioSwitch(BirdBuddyMixin, SwitchEntity):
    """Toggle whether recorded videos include audio."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Audio"
    _attr_icon = "mdi:microphone"
    _attr_has_entity_name = True
    _attr_translation_key = "audio_enabled"
    coordinator: BirdBuddyDataUpdateCoordinator

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the audio switch.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(feeder, coordinator)
        self._attr_unique_id = f"{self.feeder.id}-audio"

    @property
    def available(self) -> bool:
        """Return whether the switch is available.

        Returns:
            True when the base entity is available and the feeder is owned by
            this account; only owners may toggle audio.
        """
        return super().available and self.feeder.is_owner

    @property
    def is_on(self) -> bool:
        """Return whether audio recording is enabled.

        Returns:
            True when the feeder records audio.
        """
        return self.feeder.is_audio_enabled

    @property
    def icon(self) -> str | None:
        """Return the icon reflecting the current audio state.

        Returns:
            A microphone icon when audio is enabled, otherwise a muted icon.
        """
        return "mdi:microphone" if self.is_on else "mdi:microphone-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable audio recording.

        Args:
            **kwargs: Additional Home Assistant turn-on options (unused).
        """
        result = await self.coordinator.client.toggle_audio_enabled(self.feeder, True)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable audio recording.

        Args:
            **kwargs: Additional Home Assistant turn-off options (unused).
        """
        result = await self.coordinator.client.toggle_audio_enabled(self.feeder, False)
        if result:
            self.feeder.update(result)
            self.coordinator.async_update_listeners()
