"""Provides device triggers for Bird Buddy."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from . import DOMAIN
from .const import (
    CONF_FEEDER_ID,
    EVENT_NEW_POSTCARD_SIGHTING,
    TRIGGER_TYPE_POSTCARD,
)
from .util import (
    _find_coordinator_by_device,
    _feeder_id_for_device,
)

TRIGGER_TYPES = {TRIGGER_TYPE_POSTCARD}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Optional(CONF_FEEDER_ID): cv.string,
    }
)


async def async_validate_trigger_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate config."""
    config = TRIGGER_SCHEMA(config)
    try:
        coordinator = _find_coordinator_by_device(hass, config[CONF_DEVICE_ID])
        assert coordinator
    except Exception as exc:
        raise InvalidDeviceAutomationConfig() from exc
    return config


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for Bird Buddy devices."""
    triggers = []

    # TODO: get entities, like BirdBuddyStateEntity to attach node state triggers
    feeder_id = _feeder_id_for_device(hass, device_id)

    base_trigger = {
        CONF_PLATFORM: "device",
        CONF_DEVICE_ID: device_id,
        CONF_DOMAIN: DOMAIN,
    }

    # new postcard trigger
    triggers.append(
        {
            **base_trigger,
            CONF_TYPE: TRIGGER_TYPE_POSTCARD,
            CONF_FEEDER_ID: feeder_id,
        }
    )
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    event_data = {}
    if CONF_FEEDER_ID in config:
        # Add feeder id to trigger event data
        # The event will include .sighting.feeder.id, so that's what we will trigger on
        event_data["sighting"] = {"feeder": {"id": config[CONF_FEEDER_ID]}}
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_NEW_POSTCARD_SIGHTING,
            event_trigger.CONF_EVENT_DATA: event_data,
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
