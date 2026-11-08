"""*Test the connection* (`06_DECISIONS.md` ADR-135 Amendment 2; platform lane, brief P1): ask the
gateway for one tiny completion on an engine's model, and say in words what came back.

**The words are ours, never the provider's.** A provider's refusal can carry part of the key it
refused (OpenAI's "Incorrect API key provided: sk-…abcd", LiteLLM's own "Received API Key = …"), so
nothing from the response body is passed on: the body is read only to tell one refusal from
another, and each outcome has fixed words. That is what keeps a key out of every response, log line,
audit entry and error the check can reach (`tests/adapters/model_litellm/test_connection_check.py`
plants a recognisable key that the stand-in echoes, and looks for it).

The outcomes, as the LiteLLM proxy answers them:

- `ok`: a 2xx;
- `not_routed`: 400 "Invalid model name passed in model=…": the gateway has no entry for the model,
  so the change has not reached it yet (or the engine is not enabled);
- `gateway_token`: 401 naming the proxy's own token: the Conduit and the gateway disagree on the
  gateway's key, a deployment fault, not the provider's;
- `key_refused`: any other 401 or 403, or the 500 a missing key gives ("AuthenticationError"): the
  provider refused the key, or there was none;
- `model_not_offered`: 404: the provider does not offer that model to this key;
- `cooling_down`: 429 naming a cooldown: the gateway holds an engine back for about a minute after a
  failed call, even once a good key is set (measured), so it says "try again in a minute";
- `rate_limited`: any other 429: the provider answered but is limiting this key;
- `unreachable`: a 5xx or a transport failure: the gateway or the provider could not be reached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

Outcome = Literal[
    "ok",
    "not_routed",
    "gateway_token",
    "key_refused",
    "model_not_offered",
    "cooling_down",
    "rate_limited",
    "unreachable",
]

WORDS: dict[Outcome, str] = {
    "ok": "Connected: the engine answered.",
    "not_routed": (
        "The gateway has no route for this model. Save the engine with this model for a job, "
        "and test again."
    ),
    "gateway_token": (
        "The Conduit could not sign in to this deployment's model gateway. This is a deployment "
        "fault, not the provider's: run ospreyflow doctor."
    ),
    "key_refused": (
        "The provider refused the key. Enter the key again, or check it with the provider."
    ),
    "model_not_offered": (
        "The provider accepted the key but does not offer this model to it. Check the model name."
    ),
    "cooling_down": (
        "The gateway is holding this engine back for about a minute after a failed call. This is "
        "not a lasting failure: try again in a minute."
    ),
    "rate_limited": (
        "The provider accepted the key but is limiting it (rate or quota). Try again later."
    ),
    "unreachable": (
        "The provider could not be reached from the gateway, or the gateway is not running."
    ),
}


@dataclass(frozen=True, slots=True)
class ConnectionCheck:
    outcome: Outcome
    #: The HTTP status the gateway answered, or None where it could not be reached.
    status: int | None

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"

    @property
    def words(self) -> str:
        return WORDS[self.outcome]


def classify(status: int, body: str) -> Outcome:
    """Which outcome a gateway answer is. `body` is read only to tell the gateway's own refusals
    apart from the provider's; it is never returned."""
    if 200 <= status < 300:
        return "ok"
    if status == 400 and "Invalid model name" in body:
        return "not_routed"
    if status == 401 and "proxy server token" in body:
        return "gateway_token"
    if status in (401, 403):
        return "key_refused"
    if status == 404:
        return "model_not_offered"
    if status == 429:
        return "cooling_down" if "cooldown_list" in body else "rate_limited"
    if status in (400, 500) and "AuthenticationError" in body:
        # A missing key is a 500 (measured), and some providers answer a bad key with a 400; LiteLLM
        # labels both an authentication error.
        return "key_refused"
    return "unreachable"


async def check_connection(http: httpx.AsyncClient, model: str) -> ConnectionCheck:
    """One completion of at most one token on `model` (the gateway's `model_name`, such as
    `gemini/gemini-2.5-flash`), through the gateway the Conduit already signs in to."""
    try:
        resp = await http.post(
            "/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 1,
            },
            timeout=30.0,
        )
    except httpx.HTTPError:
        return ConnectionCheck("unreachable", None)
    return ConnectionCheck(classify(resp.status_code, resp.text), resp.status_code)
