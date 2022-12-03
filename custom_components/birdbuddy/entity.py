"""Bird Buddy entity helpers"""

from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from .coordinator import BirdBuddyDevice


class BirdBuddyMixin(CoordinatorEntity, RestoreEntity):
    """Helper for all Bird Buddy entities"""

    feeder: BirdBuddyDevice

    def __init__(
        self,
        feeder: BirdBuddyDevice,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self.feeder = feeder
        self._attr_device_info = feeder.device_info

    @property
    def available(self) -> bool:
        return self.feeder is not None
