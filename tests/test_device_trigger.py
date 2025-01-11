"""The tests for Bird Buddy device triggers."""
import pytest
from pytest_unordered import unordered
from homeassistant.components import automation
from homeassistant.components.device_automation import (
    DeviceAutomationType,
    InvalidDeviceAutomationConfig,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import EventOrigin
from homeassistant.helpers import device_registry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_get_device_automations,
)

from custom_components.birdbuddy import DOMAIN
from custom_components.birdbuddy import device_trigger
from custom_components.birdbuddy.const import EVENT_NEW_POSTCARD_SIGHTING


async def setup_automation(hass, device_id, feeder_id, trigger_type):
    """Set up an automation trigger for testing triggering."""
    return await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": device_id,
                        "feeder_id": feeder_id,
                        "type": trigger_type,
                    },
                    "action": {
                        "service": "test.automation",
                        "data": {"message": "triggered"},
                    },
                },
            ]
        },
    )


async def test_get_triggers(
    hass, device_reg: device_registry.DeviceRegistry, entity_reg
):
    """Test we get the expected triggers from a birdbuddy."""
    config_entry = MockConfigEntry(domain="birdbuddy", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "feeder1")},
    )
    expected_triggers = [
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "new_postcard",
            "device_id": device_entry.id,
            "feeder_id": "feeder1",
            # We didn't add this, but the test produces it
            "metadata": {},
        },
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_entry.id
    )
    assert triggers == unordered(expected_triggers)


async def test_fires_on_postcard_event(
    hass, device_reg: device_registry.DeviceRegistry, calls
):
    """Test new-postcard event firing triggers the device."""
    config_entry = MockConfigEntry(domain="birdbuddy", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "feeder1")},
    )
    assert await setup_automation(hass, device_entry.id, "feeder1", "new_postcard")

    message = {"sighting": {"feeder": {"id": "feeder1"}}, "postcard": {}}
    hass.bus.async_fire(EVENT_NEW_POSTCARD_SIGHTING, message)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["message"] == "triggered"


async def test_does_not_fire_on_postcard_event_for_other_feeder(hass, calls):
    """Test new-postcard event for a different device does not trigger the automation."""
    # Automation is listening for `feeder2`
    assert await setup_automation(hass, "deviceid", "feeder2", "new_postcard")

    # but our event is for `feeder1`
    message = {"sighting": {"feeder": {"id": "feeder1"}}, "postcard": {}}
    hass.bus.async_fire(EVENT_NEW_POSTCARD_SIGHTING, message, origin=EventOrigin.remote)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_config_schema(hass, device_reg):
    """Test we get the expected triggers from a birdbuddy."""
    config_entry = MockConfigEntry(domain="birdbuddy", data={}, state=ConfigEntryState.LOADED)
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "feeder1")},
    )
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = object()
    # Test that invalid config with no device coordinator raises
    config = {
        "platform": "device",
        "domain": "birdbuddy",
        "device_id": device_entry.id,
        "type": "new_postcard",
    }
    await device_trigger.async_validate_trigger_config(hass, config)


async def test_config_schema_no_coordinator(hass, device_reg):
    """Test we get the expected triggers from a birdbuddy."""
    config_entry = MockConfigEntry(domain="birdbuddy", data={}, state=ConfigEntryState.LOADED)
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "feeder1")},
    )
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = None
    # Test that invalid config with no device coordinator raises
    config = {
        "platform": "device",
        "domain": "birdbuddy",
        "feeder_id": "feeder1",
        "device_id": device_entry.id,
        "type": "new_postcard",
    }
    with pytest.raises(InvalidDeviceAutomationConfig):
        await device_trigger.async_validate_trigger_config(hass, config)
