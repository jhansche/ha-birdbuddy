"""Constants for the Bird Buddy integration."""

import logging
from datetime import timedelta

DOMAIN = "birdbuddy"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "Bird Buddy, Inc."

# Default polling interval.
# For best performance, this should be less than the access token expiration
POLLING_INTERVAL = timedelta(minutes=10)

EVENT_NEW_POSTCARD_SIGHTING = f"{DOMAIN}_new_postcard_sighting"
