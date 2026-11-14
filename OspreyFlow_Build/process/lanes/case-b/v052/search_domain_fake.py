"""A local stand-in for the namespace's OpenSearch domain, as platform's answers (lane/platform-v052-searchkind,
s3_standin.py `_domain`): a count on the deployment's alias, signed SigV4 for service `es`, is answered; anything
else is refused 403 in the domain's JSON words (an unsigned request, one signed for another service, a count on
another index). Used by test_install_verify.py's probe case and by record_search_probe.py; it checks the shape of
the signature, not its value (the stand-in itself checks that)."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

REFUSED = ("User: anonymous is not authorized to perform: es:ESHttp{method} on resource: "
           "arn:aws:es:eu-west-2:123456789012:domain/ospreyflow-poc-search/")
_SIGNED_FOR_ES = re.compile(r"^AWS4-HMAC-SHA256 Credential=[^/]+/\d{8}/[a-z0-9-]+/es/aws4_request, SignedHeaders=.+, Signature=[0-9a-f]{64}$")


def start(alias: str, *, documents: int = 3, refuse_signed: bool = False) -> HTTPServer:
    class Domain(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            signed = bool(_SIGNED_FOR_ES.match(self.headers.get("Authorization", "")))
            mine = self.path.split("?", 1)[0] == f"/{alias}/_count"
            if signed and mine and not refuse_signed:
                body, status = {"count": documents, "_shards": {"total": 1, "successful": 1}}, 200
            else:
                body, status = {"message": REFUSED.format(method=self.command.title())}, 403
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = _answer

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Domain)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
