"""Test the Bird Buddy collect_postcard service."""

import logging
from unittest.mock import patch

import aiohttp
from birdbuddy.postcards import CollectedPostcard
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from voluptuous.error import MultipleInvalid

from custom_components.birdbuddy.const import DOMAIN, SERVICE_COLLECT_POSTCARD


async def test_collect_postcard_service(hass):
    """The service validates its schema and calls collect_postcard."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"},
    )
    config_entry.add_to_hass(hass)

    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        side_effect=aiohttp.ClientConnectionError("Offline"),
    ):
        assert await async_setup_component(
            hass, DOMAIN, {CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"}
        )

    # postcard_id is required.
    with pytest.raises(MultipleInvalid) as exc_info:
        await hass.services.async_call(
            DOMAIN, SERVICE_COLLECT_POSTCARD, {}, blocking=True
        )
    msgs = [str(e) for e in exc_info.value.errors]
    assert "required key not provided @ data['postcard_id']" in msgs

    # A valid call reaches collect_postcard with the id and the share flag.
    with patch(
        "birdbuddy.client.BirdBuddy.collect_postcard",
        return_value=CollectedPostcard({"id": "feed item id"}),
    ) as collect_postcard:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {"postcard_id": "feed item id", "share": True},
            blocking=True,
        )
    collect_postcard.assert_called_once_with("feed item id", share=True)


async def _setup_entry(hass):
    """Load a config entry so the service has a coordinator to reach.

    Args:
        hass: The Home Assistant instance.
    """
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"},
    )
    config_entry.add_to_hass(hass)
    with patch(
        "birdbuddy.client.BirdBuddy.refresh",
        side_effect=aiohttp.ClientConnectionError("Offline"),
    ):
        assert await async_setup_component(
            hass, DOMAIN, {CONF_EMAIL: "test@email", CONF_PASSWORD: "passw0rd"}
        )


def _feeder_warnings(caplog):
    """Return the warnings the service logged about a named feeder.

    Args:
        caplog: The pytest log capture fixture.

    Returns:
        The matching log records.
    """
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "Feeder with id" in r.getMessage()
    ]


async def test_collect_postcard_without_a_feeder_id_stays_quiet(hass, caplog):
    """Omitting the optional feeder_id reaches the first account silently.

    services.yaml documents feeder_id as optional, so the call that leaves it
    out takes the documented path and belongs in the log at debug level.
    """
    await _setup_entry(hass)

    with (
        caplog.at_level(logging.WARNING),
        patch(
            "birdbuddy.client.BirdBuddy.collect_postcard",
            return_value=CollectedPostcard({"id": "feed item id"}),
        ) as collect_postcard,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {"postcard_id": "feed item id"},
            blocking=True,
        )

    collect_postcard.assert_called_once_with("feed item id", share=False)
    assert _feeder_warnings(caplog) == []


async def test_collect_postcard_warns_for_an_unknown_feeder(hass, caplog):
    """A named feeder no account holds falls back and names the substitute.

    A feeder keeps its owner and takes a new id when it is factory reset and
    re-paired, so an automation holding the old id arrives here.
    """
    await _setup_entry(hass)

    with (
        caplog.at_level(logging.WARNING),
        patch(
            "birdbuddy.client.BirdBuddy.collect_postcard",
            return_value=CollectedPostcard({"id": "feed item id"}),
        ) as collect_postcard,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {"postcard_id": "feed item id", "feeder_id": "retired feeder"},
            blocking=True,
        )

    collect_postcard.assert_called_once_with("feed item id", share=False)
    warnings = _feeder_warnings(caplog)
    assert len(warnings) == 1
    assert "retired feeder" in warnings[0].getMessage()


async def test_collect_postcard_before_any_entry_loads(hass):
    """The service reports a missing feeder when no entry has loaded yet.

    async_setup registers the service whether or not a config entry exists,
    and only async_setup_entry populates hass.data[DOMAIN], so a call can
    arrive while that key is still absent.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    assert DOMAIN not in hass.data

    with pytest.raises(ValueError, match="not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COLLECT_POSTCARD,
            {"postcard_id": "feed item id"},
            blocking=True,
        )
