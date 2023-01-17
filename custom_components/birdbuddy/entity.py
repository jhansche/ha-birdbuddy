"""Bird Buddy entity helpers"""

from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import BirdBuddyDataUpdateCoordinator, BirdBuddyDevice


class BirdBuddyMixin(CoordinatorEntity, RestoreEntity):
    """Helper for all Bird Buddy entities"""

    feeder: BirdBuddyDevice
    coordinator: BirdBuddyDataUpdateCoordinator

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: BirdBuddyDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self.feeder = feeder
        self._attr_device_info = feeder.device_info

    def _handle_coordinator_update(self) -> None:
        self.device_info.update(self.feeder.device_info)
        return super()._handle_coordinator_update()

    @property
    def entity_registry_enabled_default(self) -> bool:
        if self.feeder.is_pending:
            # While pending, we only have access to the name and id.
            return False
        return super().entity_registry_enabled_default

    @property
    def available(self) -> bool:
        return self.feeder is not None
