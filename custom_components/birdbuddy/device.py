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
            model="Bird Buddy",  # TODO: use feeder.tier to determine model
            name=self.name,
            sw_version=self.get("firmwareVersion", None),
            suggested_area="Outside",
        )
