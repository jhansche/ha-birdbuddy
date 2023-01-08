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

    @property
    def available(self) -> bool:
        return self.feeder is not None
