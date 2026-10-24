"""Shared fixtures. Async tests run through `asyncio.run(...)` inside sync tests."""

import pytest

from tests.doubles import FakeSessionFactory, make_spec


@pytest.fixture
def raw_spec() -> dict:
    return make_spec()


@pytest.fixture
def session_factory() -> FakeSessionFactory:
    return FakeSessionFactory()
