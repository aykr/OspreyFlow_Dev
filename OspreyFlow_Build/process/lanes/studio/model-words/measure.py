"""Each refusal as our client meets it: the real LiteLLMClient, through the pinned LiteLLM 1.101.0,
recording the gateway's raw answer and what the client raised."""

import asyncio
import json
import sys
import time

import httpx

from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


async def one(model: str) -> dict:
    seen = []
    real = httpx.AsyncHTTPTransport()

    class Rec(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            r = await real.handle_async_request(request)
            await r.aread()
            seen.append({"status": r.status_code, "body": r.content.decode()})
            return r

    c = LiteLLMClient(
        LiteLLMConfig(
            host="127.0.0.1",
            port=59870,
            api_key="sk-measurement-only",
            timeout_seconds=float(__import__("os").environ.get("T", "120")),
        ),
        transport=Rec(),
    )
    t = time.monotonic()
    try:
        await c.extract_json(model=model, text="t", response_schema=SCHEMA)
        raised = None
    except Exception as e:
        raised = f"{type(e).__module__}.{type(e).__name__}: {e}"[:600]
    finally:
        await c.aclose()
    return {
        "model": model,
        "seconds": round(time.monotonic() - t, 1),
        "answers": seen,
        "raised": raised,
    }


async def main():
    out = [await one(m) for m in sys.argv[1:]]
    print(json.dumps(out, indent=1))


asyncio.run(main())
