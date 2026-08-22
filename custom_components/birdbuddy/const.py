"""Constants for the Bird Buddy integration."""

from datetime import timedelta
import logging

from homeassistant.helpers import config_validation as cv
import voluptuous as vol

DOMAIN = "birdbuddy"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "Bird Buddy, Inc."

# Default polling interval.
# For best performance, this should be less than the access token expiration
POLLING_INTERVAL = timedelta(minutes=10)

# Home Assistant keeps CONF_ and ATTR_ constants for the same string and
# picks by role, as core does with CONF_DEVICE_ID and ATTR_DEVICE_ID. This
# one names the device-trigger config key.
CONF_FEEDER_ID = "feeder_id"

# Service-call fields and event-payload keys.
ATTR_FEEDER_ID = "feeder_id"
ATTR_POSTCARD_ID = "postcard_id"
ATTR_SHARE = "share"
ATTR_SPECIES = "species"
ATTR_MEDIA = "media"

TRIGGER_TYPE_POSTCARD = "new_postcard"
EVENT_NEW_POSTCARD = f"{DOMAIN}_new_postcard"

SERVICE_COLLECT_POSTCARD = "collect_postcard"
SERVICE_SCHEMA_COLLECT_POSTCARD = vol.Schema(
    {
        vol.Required(ATTR_POSTCARD_ID): cv.string,
        vol.Optional(ATTR_FEEDER_ID): cv.string,
        vol.Optional(ATTR_SHARE): cv.boolean,
    }
)
