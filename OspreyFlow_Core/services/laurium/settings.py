"""Laurium's service settings, checked whole at start (`06_DECISIONS.md` ADR-135 Amendment 6
decision 4): every model call goes to the deployment's gateway and nowhere else.

The service builds its chat model with Laurium's own `create_llm` on the `openai` platform, its
`openai_api_base` the gateway. Laurium's other platforms (`ollama`, `bedrock`, `anthropic`) each
reach their own host, so none is offered: there is no platform setting at all. What remains that
could send a call elsewhere is the environment the libraries under Laurium read for themselves
(the OpenAI, Anthropic, Ollama and AWS clients' base URLs, LangSmith's endpoint and tracing, an
HTTP proxy), and the gateway URL itself. Each is refused here, in words, before the app serves
anything; the words name the setting, never its value, which can carry a credential.

Standard library only, so the Conduit's own test run reads this module as the image does
(`tests/services/laurium/test_settings.py`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

#: The deployment's gateway, by the service name every profile renders it under. Not a setting:
#: a host that could be set could be set to anything.
GATEWAY_HOST = "litellm"

#: The settings this service reads. Any other `OSPREY_LAURIUM_*` is refused, not ignored.
GATEWAY_URL = "OSPREY_LAURIUM_GATEWAY_URL"
TIMEOUT_SECONDS = "OSPREY_LAURIUM_TIMEOUT_SECONDS"
_KNOWN = frozenset({GATEWAY_URL, TIMEOUT_SECONDS})
_OURS = "OSPREY_LAURIUM_"

#: Settings the libraries under Laurium read for themselves, each naming a host: refused whenever
#: set to anything. Compared without case (`https_proxy` is read as `HTTPS_PROXY` is).
_HOST_SETTINGS = (
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "OPENAI_PROXY",
    "OLLAMA_HOST",
    "OLLAMA_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_URL",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_ENDPOINT",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    # The resolver's own: each can make the single-label name `litellm` resolve elsewhere.
    "LOCALDOMAIN",
    "RES_OPTIONS",
    "HOSTALIASES",
)
#: Debug logs that write each request, a document's text with it: refused whenever set.
_LOGGING_SETTINGS = ("OPENAI_LOG", "LANGCHAIN_VERBOSE", "LANGCHAIN_DEBUG")
#: AWS's per-service endpoints (`AWS_ENDPOINT_URL_BEDROCK_RUNTIME`, …), Bedrock's among them.
_AWS_ENDPOINT = re.compile(r"^AWS_ENDPOINT_URL(_[A-Z0-9_]+)?$")
#: LangSmith's tracing, which sends every prompt and answer to LangSmith's own host.
_TRACING = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)
_OFF = frozenset({"", "0", "false", "no", "off"})

DEFAULT_TIMEOUT_SECONDS = 900.0


class RefusedSetting(Exception):
    """The service will not start: each reason, in words."""


@dataclass(frozen=True, slots=True)
class Settings:
    gateway_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        reasons: list[str] = []
        # Every spelling is read, never only the last: the libraries read either case of a name
        # (urllib prefers the lower), so one spelling set is enough to refuse.
        for name, value in sorted(env.items()):
            key = name.upper()
            if key in _HOST_SETTINGS or _AWS_ENDPOINT.match(key):
                if value.strip():
                    reasons.append(
                        f"{name} is set: it names a host, and Laurium's calls go to the "
                        "deployment's gateway alone"
                    )
            elif key in _LOGGING_SETTINGS:
                if value.strip():
                    reasons.append(
                        f"{name} is set: it logs each request, and nothing of a document is logged"
                    )
            elif key in _TRACING and value.strip().lower() not in _OFF:
                reasons.append(
                    f"{name} turns LangSmith tracing on, which sends every prompt to LangSmith's "
                    "host"
                )
        for name in sorted(env):
            if name.startswith(_OURS) and name not in _KNOWN:
                reasons.append(f"{name} is not a setting of this service")

        gateway = env.get(GATEWAY_URL, "").strip()
        if not gateway:
            reasons.append(f"{GATEWAY_URL} is not set: the deployment's gateway must be named")
        elif not _is_gateway(gateway):
            reasons.append(
                f"{GATEWAY_URL} does not name the deployment's gateway "
                f"(http://{GATEWAY_HOST}:<port>, optionally /v1), and Laurium's calls go to the "
                "gateway alone"
            )

        timeout = DEFAULT_TIMEOUT_SECONDS
        raw = env.get(TIMEOUT_SECONDS)
        if raw is not None:
            try:
                timeout = float(raw)
            except ValueError:
                timeout = -1.0
            if not timeout > 0:
                reasons.append(f"{TIMEOUT_SECONDS} is not a positive number of seconds")

        if reasons:
            raise RefusedSetting(
                "Laurium's service will not start: " + "; ".join(reasons) + "."
            )
        return cls(gateway_url=gateway.rstrip("/"), timeout_seconds=timeout)


def _is_gateway(url: str) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme in ("http", "https")
        and parts.hostname == GATEWAY_HOST
        and parts.username is None
        and parts.password is None
        and "@" not in parts.netloc
        and port is not None
        and parts.path.rstrip("/") in ("", "/v1")
        and not parts.query
        and not parts.fragment
    )
