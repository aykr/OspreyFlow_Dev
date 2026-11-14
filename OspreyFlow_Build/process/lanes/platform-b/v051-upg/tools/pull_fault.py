"""Run 3's rollback fault: a Docker API proxy on a socket of its own that refuses the pull of one image,
as a registry answers an image it does not have, and passes everything else to the real daemon.

    python pull_fault.py <proxy.sock> <regex>    # then DOCKER_HOST=unix://<proxy.sock> for one process

Only the process given `DOCKER_HOST` sees it (the update and the compose calls it makes), so nothing
else on the shared server, osprey-small included, is touched. `<regex>` is matched against the pull's
`fromImage` and `tag` query (`ghcr.io/aykr/ner@sha256:...` arrives as fromImage=ghcr.io/aykr/ner and
tag=sha256:...), the shape `docker compose pull` sends for a digest-pinned image.

Every request is forwarded with `Connection: close`, so each is seen on its own connection; an upgrade
(attach, exec) is passed through untouched. Each refusal is logged to stderr.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from urllib.parse import parse_qs, urlsplit

DAEMON = "/var/run/docker.sock"


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """One direction. Its end is passed on as a half-close, never a close: the Docker command line half-closes
    an exec's hijacked stream when it has no more input, and the daemon's output follows (run 3's first
    attempt lost every exec's output to a close here, so the update's backup failed). Both sockets are closed
    once both directions have ended (`handle`)."""
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
    except (ConnectionError, asyncio.CancelledError, OSError):
        pass


def blocked(target: str, pattern: re.Pattern[str]) -> str | None:
    """The image named by a pull request (`POST /vX/images/create?...`), when the pattern matches it."""
    parts = urlsplit(target)
    if not re.fullmatch(r"(/v[\d.]+)?/images/create", parts.path):
        return None
    query = parse_qs(parts.query)
    image = query.get("fromImage", [""])[0]
    tag = query.get("tag", [""])[0]
    named = f"{image}@{tag}" if tag.startswith("sha256:") else f"{image}:{tag}" if tag else image
    return named if pattern.search(named) else None


async def handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter, pattern: re.Pattern[str]) -> None:
    try:
        head = await client_r.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        client_w.close()
        return
    lines = head.decode("latin-1").split("\r\n")
    method, target, _ = (lines[0].split(" ", 2) + ["", ""])[:3]
    if method == "POST" and (named := blocked(target, pattern)):
        print(f"pull_fault: refused the pull of {named}", file=sys.stderr, flush=True)
        body = b'{"message":"manifest unknown: the rehearsal\'s planted fault"}'
        client_w.write(b"HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nConnection: close\r\n"
                       + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        await client_w.drain()
        client_w.close()
        return
    upgrade = any(l.lower().startswith("connection:") and "upgrade" in l.lower() for l in lines[1:])
    if not upgrade:
        kept = [l for l in lines[1:] if l and not l.lower().startswith("connection:")]
        head = ("\r\n".join([lines[0], *kept, "Connection: close"]) + "\r\n\r\n").encode("latin-1")
    up_r, up_w = await asyncio.open_unix_connection(DAEMON)
    up_w.write(head)
    await up_w.drain()
    try:
        await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))
    finally:
        for writer in (up_w, client_w):
            try:
                writer.close()
            except Exception:
                pass


async def main(sock: str, regex: str) -> None:
    pattern = re.compile(regex)
    if os.path.exists(sock):
        os.unlink(sock)
    server = await asyncio.start_unix_server(lambda r, w: handle(r, w, pattern), path=sock)
    os.chmod(sock, 0o600)
    print(f"pull_fault: listening on {sock}, refusing pulls matching {regex!r}", file=sys.stderr, flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
