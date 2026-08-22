"""Bird Buddy entity helpers."""

from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BirdBuddyDataUpdateCoordinator, BirdBuddyDevice


class BirdBuddyMixin(CoordinatorEntity[BirdBuddyDataUpdateCoordinator], RestoreEntity):
    """Helper for all Bird Buddy entities."""

    feeder: BirdBuddyDevice
    coordinator: BirdBuddyDataUpdateCoordinator

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        """Initialize the entity.

        Args:
            feeder: The Bird Buddy device this entity represents.
            coordinator: The coordinator providing feeder updates.
        """
        super().__init__(coordinator)
        self.feeder = feeder
        self._attr_device_info = feeder.device_info

    def _handle_coordinator_update(self) -> None:
        """Refresh the cached device info when the coordinator updates."""
        if self.device_info is not None:
            self.device_info.update(self.feeder.device_info)
        super()._handle_coordinator_update()

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return whether the entity is enabled in the registry by default.

        Returns:
            False while the feeder is only pending (only its name and id are
            known); otherwise the base-class default.
        """
        if self.feeder.is_pending:
            # While pending, we only have access to the name and id.
            return False
        return super().entity_registry_enabled_default

    @property
    def available(self) -> bool:
        """Return whether the entity is available.

        Returns:
            True while the feeder is present.
        """
        return self.feeder is not None
