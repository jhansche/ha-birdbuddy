"""Constants for the Bird Buddy integration."""

from datetime import timedelta
import logging

from homeassistant.helpers import config_validation as cv
import voluptuous as vol

DOMAIN = "birdbuddy"
CONF_AUTH_METHOD = "auth_method"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_USER_ID = "user_id"
# Options: the folder that keeps every visit's photos, videos and species.
# Blank turns the archive off.
CONF_ARCHIVE_FOLDER = "archive_folder"
DEFAULT_ARCHIVE_FOLDER = "/media/birdbuddy"
AUTH_EMAIL = "email"
AUTH_GOOGLE = "google"
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

# Recent-visitor sensor attribute: when the visitor's photo was taken.
ATTR_LAST_VISIT = "last_visit"

TRIGGER_TYPE_POSTCARD = "new_postcard"
EVENT_NEW_POSTCARD = f"{DOMAIN}_new_postcard"

# The event name this integration fired before adopting pybirdbuddy v0.1.0.
# A listener still registered on it means an automation kept the old trigger,
# which repairs reports.
EVENT_NEW_POSTCARD_SIGHTING_LEGACY = f"{DOMAIN}_new_postcard_sighting"
ISSUE_LEGACY_POSTCARD_EVENT = "legacy_postcard_event"

SERVICE_COLLECT_POSTCARD = "collect_postcard"
SERVICE_SCHEMA_COLLECT_POSTCARD = vol.Schema(
    {
        vol.Required(ATTR_POSTCARD_ID): cv.string,
        vol.Optional(ATTR_FEEDER_ID): cv.string,
        vol.Optional(ATTR_SHARE): cv.boolean,
    }
)

SERVICE_ARCHIVE_HISTORY = "archive_history"
SERVICE_SCHEMA_ARCHIVE_HISTORY = vol.Schema({})
