"""The AnkiConnect probe and the direct-fallback switch."""

from __future__ import annotations

import asyncio
import socket

import pytest

from mcp_ankiconnect.backend_mode import ankiconnect_listening, direct_backend_enabled


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_nothing_listening_means_closed():
    assert await ankiconnect_listening(f"http://127.0.0.1:{_free_port()}") is False


async def _serve(reply: bytes):
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        await reader.read(65536)
        writer.write(reply)
        await writer.drain()
        writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


@pytest.mark.parametrize(
    "reply",
    [
        b'HTTP/1.1 200 OK\r\nContent-Length: 29\r\n\r\n{"result": 6, "error": null}\n',
        # An erroring server is still a running Anki: never take its file.
        b"HTTP/1.1 500 Oops\r\nContent-Length: 0\r\n\r\n",
    ],
)
async def test_any_reply_means_open(reply: bytes):
    server = await _serve(reply)
    port = server.sockets[0].getsockname()[1]
    async with server:
        assert await ankiconnect_listening(f"http://127.0.0.1:{port}") is True


def test_fallback_switch():
    pytest.importorskip("anki")
    assert direct_backend_enabled({}) is True
    assert direct_backend_enabled({"ANKI_DIRECT_FALLBACK": "0"}) is False
    assert direct_backend_enabled({"ANKI_DIRECT_FALLBACK": "false"}) is False
