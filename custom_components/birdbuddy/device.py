"""Bird Buddy device"""
from homeassistant.helpers.entity import DeviceInfo
from birdbuddy.feeder import Feeder
from .const import DOMAIN, MANUFACTURER


class BirdBuddyDevice(Feeder):
    """Represents one Bird Buddy device"""

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
