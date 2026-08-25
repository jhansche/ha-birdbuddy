"""Tests for the device/feeder resolution helpers."""

from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.birdbuddy.const import DOMAIN
from custom_components.birdbuddy.hass_util import (
    _feeder_id_for_device,
    _find_coordinator_by_device,
    _find_coordinator_by_feeder,
)


def _entry(hass, state=ConfigEntryState.LOADED):
    """Add a Bird Buddy config entry to hass.

    Args:
        hass: The Home Assistant instance.
        state: The config-entry state to report.

    Returns:
        The added config entry.
    """
    entry = MockConfigEntry(domain=DOMAIN, state=state)
    entry.add_to_hass(hass)
    return entry


def _device(device_reg, entry, feeder_id="feeder1"):
    """Register a Bird Buddy device for a config entry.

    Args:
        device_reg: The device registry.
        entry: The owning config entry.
        feeder_id: The feeder id stored in the device identifiers.

    Returns:
        The created device entry.
    """
    return device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, feeder_id)},
    )


async def test_feeder_id_for_device(hass, device_reg):
    """The feeder id is read from the device's Bird Buddy identifier."""
    device = _device(device_reg, _entry(hass))
    assert _feeder_id_for_device(hass, device.id) == "feeder1"


async def test_feeder_id_for_missing_device_raises(hass, device_reg):
    """An unknown device id raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        _feeder_id_for_device(hass, "nope")


async def test_find_coordinator_by_feeder(hass):
    """The first coordinator tracking the feeder is returned, else None."""
    coordinator = MagicMock()
    coordinator.feeders = {"feeder1": object()}
    hass.data[DOMAIN] = {"cfg": coordinator}
    assert _find_coordinator_by_feeder(hass, "feeder1") is coordinator
    assert _find_coordinator_by_feeder(hass, "other") is None


async def test_find_coordinator_by_device(hass, device_reg):
    """A device resolves to its loaded config entry's coordinator."""
    entry = _entry(hass)
    coordinator = MagicMock()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    device = _device(device_reg, entry)
    assert _find_coordinator_by_device(hass, device.id) is coordinator


async def test_find_coordinator_by_device_not_loaded(hass, device_reg):
    """A device whose config entry is not loaded raises ValueError."""
    entry = _entry(hass, state=ConfigEntryState.NOT_LOADED)
    hass.data[DOMAIN] = {}
    device = _device(device_reg, entry)
    with pytest.raises(ValueError, match="not loaded"):
        _find_coordinator_by_device(hass, device.id)


async def test_find_coordinator_by_device_not_registered(hass, device_reg):
    """A loaded entry absent from hass.data raises ValueError."""
    entry = _entry(hass)
    hass.data[DOMAIN] = {}
    device = _device(device_reg, entry)
    with pytest.raises(ValueError, match="not from an existing"):
        _find_coordinator_by_device(hass, device.id)


async def test_find_coordinator_by_device_missing(hass):
    """An unknown device id raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        _find_coordinator_by_device(hass, "nope")
