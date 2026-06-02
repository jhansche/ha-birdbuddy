"""Test the Bird Buddy config flow."""
from unittest.mock import ANY, patch

from birdbuddy.sightings import SightingFinishStrategy
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)
from voluptuous.error import MultipleInvalid

from custom_components.birdbuddy.const import (
    DOMAIN,
    SERVICE_COLLECT_POSTCARD,
)


async def test_services(hass):  # , config_entry):
    """Test services."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"},
    )
    config_entry.add_to_hass(hass)

    # config_entry.add_to_hass(hass)
    assert await async_setup_component(
        hass, DOMAIN, {CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"}
    )

    # Schema is checked in layers: empty object raises missing top-level keys
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

    # Next layer of schema
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
                "postcard": {"id": "feed item id"},
            },
            blocking=True,
        )
        assert len(exc_info.value.errors) == 2
        msgs = [str(e) for e in exc_info.value.errors]
        assert "required key not provided @ data['sighting']['feeder']['id']" in msgs
        assert "required key not provided @ data['sighting']['feeder']['name']" in msgs

    with patch(
        "birdbuddy.client.BirdBuddy.finish_postcard",
        return_value=True,
    ) as finish_postcard_method:
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

        finish_postcard_method.assert_called_once_with(
            "feed item id",
            ANY,
            SightingFinishStrategy.RECOGNIZED,
            confidence_threshold=None,
            share_media=False,
        )

    with patch(
        "birdbuddy.client.BirdBuddy.finish_postcard",
        return_value=True,
    ) as finish_postcard_method:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {
                "sighting": {
                    "sightingReport": {},
                    "feeder": {"id": "feeder id", "name": "Feeder"},
                },
                "postcard": {"id": "feed item id"},
                "strategy": "mystery",
                "best_guess_confidence": 7,
                "share_media": True,
            },
            blocking=True,
        )

        finish_postcard_method.assert_called_once_with(
            "feed item id",
            ANY,
            SightingFinishStrategy.MYSTERY,
            confidence_threshold=7,
            share_media=True,
        )
