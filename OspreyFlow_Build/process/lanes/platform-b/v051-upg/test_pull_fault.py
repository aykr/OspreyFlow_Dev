"""pull_fault.py against a daemon of its own (run 3's first attempt, 14 November 2026: the update's backup
failed under the proxy before anything was changed, so no pull was refused and no rollback ran).

The Docker command line half-closes an exec's hijacked stream when it has no more input to send, and the
daemon answers the exec's output after that. A proxy that closes the daemon's connection on the client's
half-close loses the output: this daemon writes only after the client's EOF, as an exec does.

    .venv/bin/python -m pytest -p no:cacheprovider ../OspreyFlow_Build/process/lanes/platform-b/v051-upg/test_pull_fault.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import tempfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("pull_fault", Path(__file__).resolve().parent / "tools" / "pull_fault.py")
assert SPEC and SPEC.loader
pf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pf)


async def _daemon(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    head = (await reader.readuntil(b"\r\n\r\n")).decode()
    if "upgrade" in head.lower():
        writer.write(b"HTTP/1.1 101 UPGRADED\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n")
        await writer.drain()
        await reader.read()  # the client's half-close: an exec's stdin ended
        writer.write(b"the exec's output, after the client's half-close")
    else:
        body = b'{"ok": true}'
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
    await writer.drain()
    writer.close()


async def _through_the_proxy(request: bytes, half_close: bool) -> bytes:
    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        daemon_sock, proxy_sock = f"{tmp}/d.sock", f"{tmp}/p.sock"
        daemon = await asyncio.start_unix_server(_daemon, path=daemon_sock)
        pf.DAEMON = daemon_sock
        pattern = re.compile("^nothing-matches$")
        proxy = await asyncio.start_unix_server(lambda r, w: pf.handle(r, w, pattern), path=proxy_sock)
        try:
            r, w = await asyncio.open_unix_connection(proxy_sock)
            w.write(request)
            await w.drain()
            if half_close:
                await r.readuntil(b"\r\n\r\n")
                w.write_eof()
            got = await asyncio.wait_for(r.read(), timeout=5)
            w.close()
            return got
        finally:
            proxy.close(), daemon.close()


def test_an_exec_s_output_after_the_client_s_half_close_comes_through() -> None:
    request = (b"POST /v1.47/exec/abc/start HTTP/1.1\r\nHost: api\r\nContent-Type: application/json\r\n"
               b"Connection: Upgrade\r\nUpgrade: tcp\r\nContent-Length: 2\r\n\r\n{}")
    assert asyncio.run(_through_the_proxy(request, half_close=True)) == b"the exec's output, after the client's half-close"


def test_a_plain_request_is_answered_as_the_daemon_answers_it() -> None:
    got = asyncio.run(_through_the_proxy(b"GET /v1.47/version HTTP/1.1\r\nHost: api\r\nConnection: keep-alive\r\n\r\n", half_close=False))
    assert got.startswith(b"HTTP/1.1 200 OK") and got.endswith(b'{"ok": true}')


def test_the_planted_pull_is_still_refused() -> None:
    async def refused() -> bytes:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            proxy = await asyncio.start_unix_server(
                lambda r, w: pf.handle(r, w, re.compile(r"^ghcr\.io/aykr/ner@sha256:(?!old)")), path=f"{tmp}/p.sock")
            try:
                r, w = await asyncio.open_unix_connection(f"{tmp}/p.sock")
                w.write(b"POST /v1.47/images/create?fromImage=ghcr.io%2Faykr%2Fner&tag=sha256%3Anew HTTP/1.1\r\nHost: api\r\n\r\n")
                await w.drain()
                return await r.read()
            finally:
                proxy.close()
    assert asyncio.run(refused()).startswith(b"HTTP/1.1 404 Not Found")
