"""Global fixtures for the Bird Buddy integration tests."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import (
    async_mock_service,
    mock_device_registry,
    mock_registry,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip persistent notification calls during tests."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield


@pytest.fixture
def device_reg(hass):
    """Return an empty, loaded, device registry."""
    return mock_device_registry(hass)


@pytest.fixture
def entity_reg(hass):
    """Return an empty, loaded, entity registry."""
    return mock_registry(hass)


@pytest.fixture
def calls(hass):
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")
