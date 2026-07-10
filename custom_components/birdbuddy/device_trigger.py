"""Provides device triggers for Bird Buddy."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_EVENT_DATA,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from . import DOMAIN
from .const import CONF_FEEDER_ID, EVENT_NEW_POSTCARD_SIGHTING, TRIGGER_TYPE_POSTCARD
from .hass_util import _feeder_id_for_device, _find_coordinator_by_device

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
    """Validate a device trigger config.

    Args:
        hass: The Home Assistant instance.
        config: The trigger configuration to validate.

    Returns:
        The validated, schema-normalized configuration.

    Raises:
        InvalidDeviceAutomationConfig: If no coordinator backs the device.
    """
    # voluptuous' Schema.__call__ is untyped, so the validated result is seen
    # as ``object``; it is a ConfigType dict at runtime.
    config = TRIGGER_SCHEMA(config)  # type: ignore[reportAssignmentType]
    coordinator = _find_coordinator_by_device(hass, config[CONF_DEVICE_ID])
    if not coordinator:
        raise InvalidDeviceAutomationConfig
    return config


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List the device triggers for a Bird Buddy device.

    Args:
        hass: The Home Assistant instance.
        device_id: The device registry id to list triggers for.

    Returns:
        The available device trigger configurations.
    """
    triggers = []

    # TODO(jhansche): attach node-state triggers from entities such as
    # BirdBuddyStateEntity.
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
    """Attach a device trigger.

    Args:
        hass: The Home Assistant instance.
        config: The validated trigger configuration.
        action: The action to run when the trigger fires.
        trigger_info: Metadata about the trigger being attached.

    Returns:
        A callable that detaches the trigger when called.
    """
    event_data: dict[str, Any] = {}
    if CONF_FEEDER_ID not in config:
        config[CONF_FEEDER_ID] = _feeder_id_for_device(hass, config[CONF_DEVICE_ID])
    if CONF_FEEDER_ID in config:
        # Add the feeder id to the trigger event data. The event includes
        # .sighting.feeder.id, which is what we trigger on.
        event_data["sighting"] = {"feeder": {"id": config[CONF_FEEDER_ID]}}
    # voluptuous' Schema.__call__ is untyped; the validated event config is a
    # ConfigType dict at runtime.
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_NEW_POSTCARD_SIGHTING,
            CONF_EVENT_DATA: event_data,
        }
    )
    return await event_trigger.async_attach_trigger(
        hass,
        event_config,  # type: ignore[reportArgumentType]
        action,
        trigger_info,
        platform_type="device",
    )
