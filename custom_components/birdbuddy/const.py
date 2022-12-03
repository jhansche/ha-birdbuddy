"""Constants for the Bird Buddy integration."""

import logging
from datetime import timedelta

DOMAIN = "birdbuddy"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "Bird Buddy, Inc."
POLLING_INTERVAL = timedelta(minutes=15)
