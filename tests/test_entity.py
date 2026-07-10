"""Tests for the Bird Buddy entity mixin."""

from unittest.mock import MagicMock

import pytest

from custom_components.birdbuddy.device import BirdBuddyDevice
from custom_components.birdbuddy.entity import BirdBuddyMixin


def _mixin(coordinator):
    """Build a bare mixin entity for the test feeder.

    Args:
        coordinator: The coordinator mock backing the entity.

    Returns:
        A BirdBuddyMixin bound to feeder ``f1``.
    """
    feeder = BirdBuddyDevice({"__typename": "FeederForOwner", "id": "f1", "name": "BB"})
    return BirdBuddyMixin(feeder, coordinator)


@pytest.mark.parametrize(
    ("last_update_success", "expected"),
    [(True, True), (False, False)],
)
def test_available_follows_coordinator(last_update_success, expected):
    """The entity is available only while the last coordinator poll won."""
    coordinator = MagicMock()
    coordinator.last_update_success = last_update_success
    assert _mixin(coordinator).available is expected
