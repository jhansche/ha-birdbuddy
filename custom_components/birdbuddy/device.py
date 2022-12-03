"""Bird Buddy device"""
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, MANUFACTURER


class BirdBuddyDevice(dict[str, any]):
    """Represents one Bird Buddy device"""

    def __init__(self, feeder: dict[str, any]) -> None:
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

    @property
    def id(self):
        """Bird Buddy UUID"""
        return self["id"]

    @property
    def name(self):
        """Bird Buddy name"""
        return self.get("name", "Bird Buddy")

    @property
    def battery_percentage(self) -> int:
        """Percentage of battery remaining"""
        return self["battery"].get("percentage", 0)

    @property
    def is_charging(self) -> bool:
        """Whether the Bird Buddy battery is charging"""
        return self["battery"].get("charging", False)
