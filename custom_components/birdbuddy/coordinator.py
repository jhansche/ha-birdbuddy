"""Data Update coordinator for ZAMG weather data."""
from __future__ import annotations

from birdbuddy.client import BirdBuddy

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from .const import DOMAIN, LOGGER, POLLING_INTERVAL

from .device import BirdBuddyDevice


class BirdBuddyDataUpdateCoordinator(DataUpdateCoordinator[BirdBuddy]):
    """Class to coordinate fetching BirdBuddy data."""

    config_entry: ConfigEntry
    client: BirdBuddy
    feeders: dict[str, BirdBuddyDevice]

    def __init__(
        self,
        hass: HomeAssistant,
        client: BirdBuddy,
        entry: ConfigEntry,
    ) -> None:
        self.client = client
        self.feeders = {}
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=POLLING_INTERVAL,
        )

    async def _async_update_data(self) -> BirdBuddy:
        try:
            if await self.client.refresh():
                for d in map(BirdBuddyDevice, self.client.feeders):
                    self.feeders.setdefault(d.id, d).update(d)
        except Exception as exc:
            raise UpdateFailed from exc
        return self.client
