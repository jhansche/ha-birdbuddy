"""Constants for the Bird Buddy integration."""

from datetime import timedelta
from homeassistant.helpers import config_validation as cv
import logging
import voluptuous as vol

DOMAIN = "birdbuddy"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "Bird Buddy, Inc."

# Default polling interval.
# For best performance, this should be less than the access token expiration
POLLING_INTERVAL = timedelta(minutes=10)

EVENT_NEW_POSTCARD_SIGHTING = f"{DOMAIN}_new_postcard_sighting"

SERVICE_SCHEMA_COLLECT_POSTCARD = vol.Schema(
    {
        vol.Required("postcard"): cv.has_at_least_one_key("id"),
        vol.Required("sighting"): cv.has_at_least_one_key("sightingReport"),
        vol.Optional("device_id"): cv.string,  # better?
        vol.Optional("strategy"): cv.string,
        # ...?
    }
)
