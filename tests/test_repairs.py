"""Tests for the renamed-postcard-event repairs issue."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.automation.const import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.const import SERVICE_TURN_OFF
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.birdbuddy.const import (
    DOMAIN,
    EVENT_NEW_POSTCARD,
    EVENT_NEW_POSTCARD_SIGHTING_LEGACY,
    ISSUE_LEGACY_POSTCARD_EVENT,
)
from custom_components.birdbuddy.coordinator import BirdBuddyDataUpdateCoordinator
from custom_components.birdbuddy.repairs import async_check_legacy_event_listeners


async def setup_event_automation(hass, event_type):
    """Set up an automation triggering on an event type.

    Args:
        hass: The Home Assistant instance.
        event_type: The event type the automation triggers on.

    Returns:
        True once the automation integration is set up.
    """
    return await async_setup_component(
        hass,
        AUTOMATION_DOMAIN,
        {
            AUTOMATION_DOMAIN: [
                {
                    "alias": "collect postcards",
                    "trigger": {"platform": "event", "event_type": event_type},
                    "action": {
                        "service": "test.automation",
                        "data": {"message": "triggered"},
                    },
                }
            ]
        },
    )


def _issue(hass):
    """Return the repairs issue, if it is currently raised.

    Args:
        hass: The Home Assistant instance.

    Returns:
        The issue entry, or None while no issue is raised.
    """
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_LEGACY_POSTCARD_EVENT)


async def test_automation_on_the_old_event_raises_the_issue(hass):
    """An automation triggering on the old event name raises the issue."""
    assert await setup_event_automation(hass, EVENT_NEW_POSTCARD_SIGHTING_LEGACY)
    await hass.async_block_till_done()

    async_check_legacy_event_listeners(hass)

    issue = _issue(hass)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.translation_placeholders == {
        "legacy_event": EVENT_NEW_POSTCARD_SIGHTING_LEGACY,
        "event": EVENT_NEW_POSTCARD,
    }


async def test_automation_on_the_new_event_raises_nothing(hass):
    """An automation already moved to the new event name stays quiet."""
    assert await setup_event_automation(hass, EVENT_NEW_POSTCARD)
    await hass.async_block_till_done()

    async_check_legacy_event_listeners(hass)

    assert _issue(hass) is None


async def test_disabling_the_automation_clears_the_issue(hass):
    """Turning the automation off detaches its trigger and clears the issue."""
    assert await setup_event_automation(hass, EVENT_NEW_POSTCARD_SIGHTING_LEGACY)
    await hass.async_block_till_done()
    async_check_legacy_event_listeners(hass)
    assert _issue(hass) is not None

    await hass.services.async_call(
        AUTOMATION_DOMAIN,
        SERVICE_TURN_OFF,
        {"entity_id": "automation.collect_postcards"},
        blocking=True,
    )
    async_check_legacy_event_listeners(hass)

    assert _issue(hass) is None


async def test_the_first_poll_runs_the_check(hass):
    """The coordinator raises the issue on its very first poll.

    The first poll skips feed processing, so the check sits outside that
    branch to report a stale trigger without waiting an extra interval.
    """
    assert await setup_event_automation(hass, EVENT_NEW_POSTCARD_SIGHTING_LEGACY)
    await hass.async_block_till_done()
    client = MagicMock()
    client.refresh = AsyncMock()
    client.feeders = {
        "feeder1": {"__typename": "FeederForOwner", "id": "feeder1", "name": "BB"}
    }
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = BirdBuddyDataUpdateCoordinator(hass, client, entry)
    assert coordinator.first_update is True

    await coordinator._async_update_data()

    assert _issue(hass) is not None
