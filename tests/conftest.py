"""Shared fixtures. Async tests run through `asyncio.run(...)` inside sync tests."""

import pytest

from tests.doubles import FakeSessionFactory, make_spec


@pytest.fixture
def raw_spec() -> dict:
    return make_spec()


@pytest.fixture
def session_factory() -> FakeSessionFactory:
    return FakeSessionFactory()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "real_window: run with the real 2.0 s quiet window (gate runner tests)"
    )
