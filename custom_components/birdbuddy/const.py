"""Constants for the Bird Buddy integration."""

from datetime import timedelta
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.helpers import config_validation as cv
import logging
import voluptuous as vol

DOMAIN = "birdbuddy"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "Bird Buddy, Inc."

# Default polling interval.
# For best performance, this should be less than the access token expiration
POLLING_INTERVAL = timedelta(minutes=10)

CONF_FEEDER_ID = "feeder_id"
TRIGGER_TYPE_POSTCARD = "new_postcard"
EVENT_NEW_POSTCARD_SIGHTING = f"{DOMAIN}_new_postcard_sighting"

SERVICE_SCHEMA_COLLECT_POSTCARD = vol.Schema(
    {
        vol.Required("postcard"): cv.has_at_least_one_key("id"),
        vol.Required("sighting"): cv.has_at_least_one_key("sightingReport"),
        vol.Optional(CONF_DEVICE_ID): cv.string,  # better?
        vol.Optional("strategy"): cv.string,
        vol.Optional("best_guess_confidence"): vol.Coerce(int),
        # ...?
    }
)
