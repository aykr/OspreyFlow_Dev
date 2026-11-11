"""The gateway's measured stand-in (`adapters/model_litellm/stand_in.py`) served over real HTTP, so a
process that is not this one's `httpx` client (Laurium's service, its OpenAI client inside
LangChain) reaches it as it reaches the gateway (`06_DECISIONS.md` ADR-135 Amendment 6).

Nothing of the stand-in's behaviour changes here: each request is handed to the stand-in's own
handler as it arrived (method, path, query, headers, body) and its answer written back, so it grants
and refuses exactly what the in-process stand-in does, which is what was measured against the pinned
LiteLLM image (rule 15's second worked example).

`resolve_litellm_here` points the name `litellm` at this machine for this process alone, as the
deployment's network points it at the gateway's container; Laurium's service accepts no other host.
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


def _handler(gateway: StandInGateway) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else b""
            request = httpx.Request(
                self.command,
                f"http://litellm{self.path}",
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
def serve(gateway: StandInGateway, host: str = "127.0.0.1", port: int = 0) -> Iterator[int]:
    """The stand-in on `host`, on `port` (0: any free one); yields the port."""
    server = ThreadingHTTPServer((host, port), _handler(gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def resolve_litellm_here() -> Iterator[None]:
    """`litellm` resolves to 127.0.0.1 in this process while inside; every other name as before."""
    real = socket.getaddrinfo

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        # anyio (under httpx and the OpenAI client) passes the name as ASCII bytes.
        return real("127.0.0.1" if host in ("litellm", b"litellm") else host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.getaddrinfo = real  # type: ignore[assignment]
