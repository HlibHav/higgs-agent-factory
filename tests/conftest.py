"""Shared fixtures. Async tests run through `asyncio.run(...)` inside sync tests."""

import ipaddress
import socket
from collections.abc import Iterator
from typing import Any

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


_LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


def _is_loopback_host(host: Any) -> bool:
    """True for no host, a loopback name or a loopback address (127.0.0.0/8, ::1)."""
    if host is None or host == "":
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _blocked(what: str, target: Any) -> OSError:
    return OSError(f"network blocked in offline tests ({what} {target!r}); mark the test live")


@pytest.fixture(autouse=True)
def _offline_network_guard(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Offline tests (AC-54) may reach AF_UNIX and loopback only; `live` tests are exempt."""
    if "live" in request.keywords:
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def allowed(sock: socket.socket, address: Any) -> bool:
        if sock.family == socket.AF_UNIX:
            return True
        return isinstance(address, tuple) and _is_loopback_host(address[0])

    def connect(self: socket.socket, address: Any) -> None:
        if not allowed(self, address):
            raise _blocked("connect", address)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if not allowed(self, address):
            raise _blocked("connect_ex", address)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_loopback_host(host):
            raise _blocked("lookup", host)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield
