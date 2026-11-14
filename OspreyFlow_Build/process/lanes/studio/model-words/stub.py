"""Answers Gemini's generateContent as Gemini does when refusing, so the pinned LiteLLM's own
gemini provider wraps it. Bodies from Google's documented error format (ai.google.dev, errors)."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

BODIES = {
    "429": (
        429,
        {
            "error": {
                "code": 429,
                "message": "You exceeded your current quota, please check your plan and billing "
                "details.",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    ),
    "403": (
        403,
        {
            "error": {
                "code": 403,
                "message": "Method doesn't allow unregistered callers (callers without established "
                "identity). Please use API Key or other form of API consumer identity to call "
                "this API.",
                "status": "PERMISSION_DENIED",
            }
        },
    ),
    "503": (
        503,
        {
            "error": {
                "code": 503,
                "message": "The model is overloaded. Please try again later.",
                "status": "UNAVAILABLE",
            }
        },
    ),
}


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        self.rfile.read(n)
        kind = self.server.kind
        code, body = BODIES[kind]
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print("stub", kind, self.path.split("?")[0], file=sys.stderr, flush=True)

    def log_message(self, *a):
        pass


for kind, port in (("429", 59881), ("403", 59882), ("503", 59883)):
    import threading

    s = HTTPServer(("127.0.0.1", port), H)
    s.kind = kind
    threading.Thread(target=s.serve_forever, daemon=True).start()
threading.Event().wait()
