"""Bird Buddy device."""

from birdbuddy.feeder import Feeder
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER


class BirdBuddyDevice(Feeder):
    """Represents one Bird Buddy device."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return the Home Assistant device registry info.

        Returns:
            The DeviceInfo describing this feeder in the device registry.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self.id)},
            manufacturer=MANUFACTURER,
            model="Bird Buddy",  # TODO(jhansche): use feeder.tier for model
            name=self.name,
            sw_version=self.get("firmwareVersion", None),
            suggested_area="Outside",
        )
