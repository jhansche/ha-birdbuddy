"""Report automations still triggering on the pre-v0.1.0 postcard event.

Adopting pybirdbuddy v0.1.0 renamed the postcard event, and Home Assistant
offers no way to rewrite a user's automation. An automation left on the old
name keeps loading and waits for an event that never arrives, so the failure
is silent.

EventBus.async_listeners() reports the registrations held per event type,
leaving out the match-all listeners that the recorder and logbook install.
This integration listens only to the new name, so a count against the old
one comes from user configuration.

The coordinator calls this on every poll, first one included. That reads the
count with Home Assistant running and every automation holding its triggers,
and repeats often enough to clear the issue once the last automation moves
across.
"""

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    EVENT_NEW_POSTCARD,
    EVENT_NEW_POSTCARD_SIGHTING_LEGACY,
    ISSUE_LEGACY_POSTCARD_EVENT,
    LOGGER,
)

DOCS_URL = "https://github.com/jhansche/ha-birdbuddy#breaking-changes"


@callback
def async_check_legacy_event_listeners(hass: HomeAssistant) -> None:
    """Raise or clear the repairs issue for the renamed postcard event.

    The issue is is_fixable=False, so Home Assistant shows the description
    and a link and leaves the edit to the user: repairing it means changing
    an automation this integration has no standing to rewrite. Moving the
    last automation to the new event clears the issue on the next poll.

    Args:
        hass: The Home Assistant instance.
    """
    listeners = hass.bus.async_listeners().get(EVENT_NEW_POSTCARD_SIGHTING_LEGACY, 0)
    if not listeners:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_LEGACY_POSTCARD_EVENT)
        return

    registry = ir.async_get(hass)
    if registry.async_get_issue(DOMAIN, ISSUE_LEGACY_POSTCARD_EVENT) is None:
        LOGGER.warning(
            "%d listener(s) remain on %s; switch those automations to %s",
            listeners,
            EVENT_NEW_POSTCARD_SIGHTING_LEGACY,
            EVENT_NEW_POSTCARD,
        )
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_LEGACY_POSTCARD_EVENT,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LEGACY_POSTCARD_EVENT,
        translation_placeholders={
            "legacy_event": EVENT_NEW_POSTCARD_SIGHTING_LEGACY,
            "event": EVENT_NEW_POSTCARD,
        },
        learn_more_url=DOCS_URL,
    )
