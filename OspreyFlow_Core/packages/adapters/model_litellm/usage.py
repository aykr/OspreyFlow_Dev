"""Each model call's engine and job, the engine's own gateway key, a limit's refusal in words, and
the gateway's usage records read as counts (`06_DECISIONS.md` ADR-135 Amendment 3).

**Measured first** (8 November 2026, two platform leases on stack a, the pinned LiteLLM 1.101.0):
the gateway records each call under each of its tags per day (`LiteLLM_DailyTagSpend`, read with
`GET /tag/daily/activity`), with calls, successes, failures and tokens and no prompt or answer
text; it enforces limits only on a virtual key, never on a model entry; and a limit's refusal
names the key's hash or its last four characters. So:

- **every call carries one tag**, `osprey:<engine>/<job>`, set by the routing for the call it
  decided (`calling`), and nothing else about it: never a person, a case, a dataset or a source
  identifier;
- **each hosted engine's calls go with its own gateway key**, `engine_key`, an HMAC of the engine's
  name under the gateway master key the Conduit already holds: never stored, never written, the
  same in every Conduit replica, and gone with the master key. The engine's limits are that key's;
- **a limit's refusal is `ModelLimitReached`**, built from the refusal's type, kind and reset time
  alone, never its words;
- **usage is read as counts** (`read_usage`): only tags of the `osprey:` shape, only their figures.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

import httpx

from .errors import ModelLimitReached, UsageUnavailableError

TAG_PREFIX = "osprey:"
#: The deployment's own engine (`services.api.model_routing.LOCAL`); its calls use the master key.
LOCAL = "local"
#: An engine's name as `ModelProviderConfig` takes it (any length), or `local`.
_NAME = re.compile(r"[a-z][a-z0-9_]*")
_JOB = re.compile(r"[a-z]{1,24}")


@dataclass(frozen=True)
class Call:
    """The routing's decision for one call: which engine, for which job."""

    engine: str
    job: str


_current: contextvars.ContextVar[Call | None] = contextvars.ContextVar(
    "osprey_model_call", default=None
)


@contextmanager
def calling(engine: str, job: str) -> Iterator[None]:
    """Every gateway call made inside is tagged with `engine` and `job`, and goes with the engine's
    key (a hosted one) or the master key (`local`)."""
    token = _current.set(Call(engine, job))
    try:
        yield
    finally:
        _current.reset(token)


def current_call() -> Call | None:
    return _current.get()


def usage_tag(engine: str, job: str) -> str:
    return f"{TAG_PREFIX}{engine}/{job}"


def parse_tag(tag: str) -> Call | None:
    """`osprey:<engine>/<job>` back to its parts; anything else (the gateway's own `User-Agent: …`
    tags, a tag of another shape) is None, and is never read."""
    if not tag.startswith(TAG_PREFIX):
        return None
    engine, sep, job = tag.removeprefix(TAG_PREFIX).partition("/")
    if not sep or not _NAME.fullmatch(engine) or not _JOB.fullmatch(job):
        return None
    return Call(engine, job)


def engine_key(master: str, engine: str) -> str:
    """An engine's gateway key: an HMAC of its name under the master key. Never stored anywhere;
    each Conduit derives the same one."""
    digest = hmac.new(master.encode(), f"osprey-engine:{engine}".encode(), hashlib.sha256)
    return "sk-osprey-" + digest.hexdigest()[:48]


# --- a limit's refusal --------------------------------------------------------------------------

#: The gateway's own words for a key's limit (measured); a 429 without them is not one.
_RATE_WORDS = re.compile(r"^Rate limit exceeded for (api_key|model_per_key): ")
_BUDGET_WORDS = "Budget has been exceeded!"
_RESETS = re.compile(r"Limit resets at: (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) UTC")
_KIND = re.compile(r"Limit type: (requests|tokens)\b")


def limit_refusal(response: httpx.Response) -> ModelLimitReached | None:
    """A 429 the gateway gave for a key's limit, as `ModelLimitReached`; None for any other answer
    (a cooldown's 429, a provider's own 429 passed through). It must carry both the measured type
    and the gateway's own words for a key's limit. Only the type, the kind and the reset time are
    read from it: nothing else of its words, which name the key's hash or part of
    the key, ever leaves this function."""
    if response.status_code != 429:
        return None
    try:
        error = dict(response.json().get("error") or {})
    except ValueError:
        return None
    kind_of = str(error.get("type", ""))
    message = str(error.get("message", ""))
    if kind_of == "budget_exceeded" and message.startswith(_BUDGET_WORDS):
        return ModelLimitReached("budget")
    if kind_of == "throttling_error" and _RATE_WORDS.match(message):
        kind = _KIND.search(message)
        resets = _RESETS.search(message)
        at = (
            datetime.strptime(resets.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            if resets
            else None
        )
        return ModelLimitReached(
            "tokens" if kind and kind.group(1) == "tokens" else "requests", resets_at=at
        )
    return None


# --- usage --------------------------------------------------------------------------------------

Figure = Literal["calls", "succeeded", "failed", "prompt_tokens", "completion_tokens", "tokens"]
_FROM_GATEWAY: Mapping[Figure, str] = {
    "calls": "api_requests",
    "succeeded": "successful_requests",
    "failed": "failed_requests",
    "prompt_tokens": "prompt_tokens",
    "completion_tokens": "completion_tokens",
    "tokens": "total_tokens",
}
#: Rows a page asks for (measured: the gateway's default is 10 rows of day and tag, and it takes
#: 1000), and pages read before refusing: a period's answer longer than this is said, never cut
#: short (rule 2).
PAGE_SIZE = 1000
_MAX_PAGES = 100


@dataclass(frozen=True)
class UsageRecord:
    engine: str
    job: str
    figures: Mapping[Figure, int]


async def read_usage(http: httpx.AsyncClient, start: date, end: date) -> list[UsageRecord]:
    """The gateway's own records from `start` to `end` (UTC days, both included), summed per
    engine and job. `http` carries the master key: only it may read them (measured). A failure is
    `UsageUnavailableError` in fixed words; the gateway's are never passed on."""
    totals: dict[tuple[str, str], dict[Figure, int]] = {}
    page = 1
    while True:
        try:
            resp = await http.get(
                "/tag/daily/activity",
                params={
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "page": page,
                    "page_size": PAGE_SIZE,
                },
                timeout=30.0,
            )
        except httpx.HTTPError:
            raise UsageUnavailableError(
                "The model gateway could not be reached, so its usage cannot be read now."
            ) from None
        if resp.status_code != 200:
            raise UsageUnavailableError(
                f"The model gateway refused to give its usage (HTTP {resp.status_code}). Run "
                "ospreyflow doctor."
            )
        body: dict[str, Any] = resp.json()
        for day in body.get("results") or []:
            entities = dict(dict(day.get("breakdown") or {}).get("entities") or {})
            for tag, held in entities.items():
                call = parse_tag(str(tag))
                if call is None:
                    continue
                metrics = dict(dict(held or {}).get("metrics") or {})
                row = totals.setdefault((call.engine, call.job), dict.fromkeys(_FROM_GATEWAY, 0))
                for ours, theirs in _FROM_GATEWAY.items():
                    row[ours] += int(metrics.get(theirs) or 0)
        meta = dict(body.get("metadata") or {})
        if not meta.get("has_more"):
            break
        page += 1
        if page > _MAX_PAGES:
            raise UsageUnavailableError(
                "The model gateway's usage for this period is longer than can be read at once; "
                "choose a shorter period."
            )
    return [UsageRecord(engine, job, figures) for (engine, job), figures in sorted(totals.items())]
