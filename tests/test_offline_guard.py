"""The offline suite cannot reach the network (AC-54); `live` tests are exempt."""

import os
import socket
import tempfile

import pytest


def test_non_loopback_connect_refused() -> None:
    with pytest.raises(OSError, match="network blocked"):
        socket.create_connection(("192.0.2.1", 80), timeout=1)


def test_non_loopback_raw_connect_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(OSError, match="network blocked"):
            s.connect(("192.0.2.1", 80))
        with pytest.raises(OSError, match="network blocked"):
            s.connect_ex(("192.0.2.1", 80))


def test_name_lookup_off_loopback_refused() -> None:
    with pytest.raises(OSError, match="network blocked"):
        socket.getaddrinfo("example.com", 443)


def test_loopback_allowed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            conn, _ = server.accept()
            conn.close()
    assert socket.getaddrinfo("localhost", port)


def test_unix_socket_allowed() -> None:
    # AF_UNIX paths are short on macOS: bind in a short temp dir.
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        path = os.path.join(d, "s")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            server.listen(1)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(path)
