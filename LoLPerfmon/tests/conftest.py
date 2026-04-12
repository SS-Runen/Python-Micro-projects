"""Shared fixtures for LoLPerfmon simulation tests."""

import os

import pytest

from LoLPerfmon.validation_checks import ValidationContext


@pytest.fixture
def ctx() -> ValidationContext:
    offline = os.environ.get("LOLPERFMON_OFFLINE", "1").lower() in ("1", "true", "yes")
    return ValidationContext(offline=offline)
