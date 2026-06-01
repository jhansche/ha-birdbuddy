"""Test the Bird Buddy config flow."""
from unittest.mock import MagicMock

from birdbuddy.sightings import SightingFinishStrategy
from homeassistant.setup import async_setup_component
import pytest
from voluptuous.error import MultipleInvalid

from custom_components.birdbuddy.const import DOMAIN, SERVICE_COLLECT_POSTCARD


async def test_services(hass):
    """Test service schema and dispatch."""
    mock_coordinator = MagicMock()
    mock_coordinator.feeders = {"feeder id": {"id": "feeder id", "name": "Feeder"}}
    mock_coordinator.handle_collect_postcard.return_value = True

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["test_entry"] = mock_coordinator

    assert await async_setup_component(hass, DOMAIN, {})

    with pytest.raises(MultipleInvalid) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {},
            blocking=True,
        )
    assert len(exc_info.value.errors) == 2
    msgs = [str(e) for e in exc_info.value.errors]
    assert "required key not provided @ data['postcard']" in msgs
    assert "required key not provided @ data['sighting']" in msgs

    with pytest.raises(MultipleInvalid) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {
                "sighting": {},
                "postcard": {},
            },
            blocking=True,
        )
    assert len(exc_info.value.errors) == 3
    msgs = [str(e) for e in exc_info.value.errors]
    assert "required key not provided @ data['sighting']['sightingReport']" in msgs
    assert "required key not provided @ data['sighting']['feeder']" in msgs
    assert (
        "must contain at least one of id. for dictionary value @ data['postcard']"
        in msgs
    )

    with pytest.raises(MultipleInvalid) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {
                "sighting": {"sightingReport": {}, "feeder": {}},
                "postcard": {},
            },
            blocking=True,
        )
    assert len(exc_info.value.errors) == 1
    msgs = [str(e) for e in exc_info.value.errors]
    assert (
        "must contain at least one of id. for dictionary value @ data['postcard']"
        in msgs
    )

    with pytest.raises(MultipleInvalid) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {
                "sighting": {"sightingReport": {}, "feeder": {}},
                "postcard": {"id": "feed item id"},
            },
            blocking=True,
        )
    assert len(exc_info.value.errors) == 2
    msgs = [str(e) for e in exc_info.value.errors]
    assert "required key not provided @ data['sighting']['feeder']['id']" in msgs
    assert "required key not provided @ data['sighting']['feeder']['name']" in msgs

    await hass.services.async_call(
        DOMAIN,
        SERVICE_COLLECT_POSTCARD,
        {
            "sighting": {
                "sightingReport": {},
                "feeder": {"id": "feeder id", "name": "Feeder"},
            },
            "postcard": {"id": "feed item id"},
        },
        blocking=True,
    )

    mock_coordinator.handle_collect_postcard.assert_called_once_with(
        {
            "sighting": {
                "sightingReport": {},
                "feeder": {"id": "feeder id", "name": "Feeder"},
            },
            "postcard": {"id": "feed item id"},
        }
    )

    mock_coordinator.handle_collect_postcard.reset_mock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_COLLECT_POSTCARD,
        {
            "sighting": {
                "sightingReport": {},
                "feeder": {"id": "feeder id", "name": "Feeder"},
            },
            "postcard": {"id": "feed item id"},
            "strategy": SightingFinishStrategy.MYSTERY.value,
            "best_guess_confidence": 7,
            "share_media": True,
        },
        blocking=True,
    )

    mock_coordinator.handle_collect_postcard.assert_called_once_with(
        {
            "sighting": {
                "sightingReport": {},
                "feeder": {"id": "feeder id", "name": "Feeder"},
            },
            "postcard": {"id": "feed item id"},
            "strategy": SightingFinishStrategy.MYSTERY.value,
            "best_guess_confidence": 7,
            "share_media": True,
        }
    )
