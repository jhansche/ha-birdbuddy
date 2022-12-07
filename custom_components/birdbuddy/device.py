"""Bird Buddy device"""
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, MANUFACTURER
from birdbuddy.feeder import Feeder


class BirdBuddyDevice(Feeder):
    """Represents one Bird Buddy device"""

    def __init__(self, feeder: Feeder) -> None:
        super().__init__(feeder)

    @property
    def device_info(self) -> DeviceInfo:
        """The Home Assistant DeviceInfo"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.id)},
            manufacturer=MANUFACTURER,
            default_model="Bird Buddy",
            default_name="Bird Buddy",
            name=self.name,
            # FIXME: firmware version only for owner account
            sw_version=self.get("firmwareVersion", None),
            suggested_area="Outside",
        )
