"""Pytest shared fixtures for AMISim tests."""

from __future__ import annotations

from typing import Any, Generator

import pytest

from amisim import AmisimApp


@pytest.fixture(autouse=True)
def reset_amisim_app_singleton() -> Generator[Any, None, None]:
    """Reset the AmisimApp singleton before and after each test."""
    current = AmisimApp.singleton_instance
    if current is not None:
        current.close()
    AmisimApp.singleton_instance = None
    yield
    current = AmisimApp.singleton_instance
    if current is not None:
        current.close()
    AmisimApp.singleton_instance = None
