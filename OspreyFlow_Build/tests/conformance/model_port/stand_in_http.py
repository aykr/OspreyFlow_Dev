"""The gateway's measured stand-in (`adapters/model_litellm/stand_in.py`) served over real HTTP, so a
process that is not this one's `httpx` client (Laurium's service, its OpenAI client inside
LangChain) reaches it as it reaches the gateway (`06_DECISIONS.md` ADR-135 Amendment 6).

Each request is handed to the stand-in's own handler as it arrived (method, path, query, headers,
body) and its answer written back, so it grants and refuses what the in-process stand-in does, which
is what was measured against the pinned LiteLLM image (rule 15's second worked example). **One
addition, LiteLLM's own:** the proxy serves the OpenAI routes under `/v1` as well as bare
(`/v1/chat/completions` and `/chat/completions` are one route in LiteLLM's `proxy_server.py`), and an
OpenAI client given the base `http://litellm:4000/v1` (which Laurium's settings accept) asks the
first. The in-process stand-in routes only the bare path, so here `/v1/chat/completions` is handed to
it as `/chat/completions`; every other path goes as it came, and is refused as before.

`resolve_litellm_here` points the name `litellm` at this machine for this process alone, as the
deployment's network points it at the gateway's container, and **refuses every other name** (and
keeps it), so a call that would leave for any other host fails at the lookup, never reaching it, and
the test can say which name was asked.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

from adapters.model_litellm.stand_in import StandInGateway

_LOCK = threading.Lock()


#: LiteLLM serves these under `/v1` too; the stand-in routes them bare.
_V1_ALIASES = ("/v1/chat/completions",)


def _handler(gateway: StandInGateway, paths: list[str] | None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else b""
            if paths is not None:
                paths.append(f"{self.command} {self.path}")
            path = self.path
            if path.split("?")[0] in _V1_ALIASES:
                path = path.removeprefix("/v1")
            request = httpx.Request(
                self.command,
                f"http://litellm{path}",
                headers=[(k, v) for k, v in self.headers.items()],
                content=body,
            )
            with _LOCK:  # the stand-in keeps state; one request at a time
                response = gateway.transport().handle_request(request)
                content = response.read()
            self.send_response(response.status_code)
            self.send_header("content-type", response.headers.get("content-type", "application/json"))
            self.send_header("content-length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_POST = do_PATCH = do_DELETE = _serve  # noqa: N815

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return  # nothing of a request is logged

    return Handler


@contextmanager
def serve(
    gateway: StandInGateway,
    host: str = "127.0.0.1",
    port: int = 0,
    *,
    paths: list[str] | None = None,
) -> Iterator[int]:
    """The stand-in on `host`, on `port` (0: any free one); yields the port. Each request's method
    and path, as it arrived, is appended to `paths` when one is given."""
    server = ThreadingHTTPServer((host, port), _handler(gateway, paths))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def resolve_litellm_here(address: str = "127.0.0.1") -> Iterator[list[str]]:
    """While inside, `litellm` resolves to `address` in this process and **every other name is
    refused** as an unknown name; yields the list of each refused name, as it was asked."""
    real = socket.getaddrinfo
    refused: list[str] = []

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        # anyio (under httpx and the OpenAI client) passes the name as ASCII bytes.
        if host in ("litellm", b"litellm"):
            return real(address, *args, **kwargs)
        refused.append(host.decode() if isinstance(host, bytes) else str(host))
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    try:
        yield refused
    finally:
        socket.getaddrinfo = real  # type: ignore[assignment]
