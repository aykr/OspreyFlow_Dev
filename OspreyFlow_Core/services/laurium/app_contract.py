"""What Laurium's service answers (`06_DECISIONS.md` ADR-135 Amendment 6 decision 3): the request it
reads, the answer it gives, and each refusal, by its `refusal` kind. The Conduit's
`adapters/extract_laurium` is its one client and turns each refusal into `ModelPort`'s typed errors.

`POST /v1/extract`, the gateway's token for this call in `Authorization: Bearer …` (the engine's own
key, or the master key for the deployment's own models), which the service uses for this call alone
and never keeps or writes:

- 200 `ExtractAnswer`;
- 401 `no_gateway_token`: no token was given;
- 413 `too_long`: the text is over `MAX_CHARS`, refused rather than read in part (rule 2's spirit);
- 400 `unsupported_schema`: a JSON Schema Laurium is not given (`schema_map`), with our words;
- 502 `gateway`: the gateway refused the call, with its status; for a 429, the gateway's error, so
  the adapter can tell a limit set in *Admin › Models* (`usage.limit_refusal`) from another 429;
- 502 `unparseable`: the model's answer did not parse into the schema after `ATTEMPTS` tries;
- 504 `gateway_unreachable`: the gateway could not be reached, or did not answer in time.

Pydantic only, so the Conduit's tests read it as the image does.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

#: A text longer than this is refused, as the recogniser's sidecar refuses one: the Conduit reads a
#: long document window by window (`services/api/review.py`, ADR-095), each well under it.
MAX_CHARS = 200_000

#: How many times one document is asked before its answer counts as unparseable: the LiteLLM
#: adapter's own number (`adapters/model_litellm/client._MAX_ATTEMPTS`).
ATTEMPTS = 3


class ExtractAsk(BaseModel):
    document_id: str
    #: Checked against `MAX_CHARS` by the route, so the refusal is `too_long`, not a 422.
    text: str
    json_schema: dict[str, Any]
    #: The gateway's `model_name`.
    model: str = Field(min_length=1)
    #: `osprey:<engine>/<job>` (ADR-135 Amendment 3), when the routing named the call.
    tag: str | None = None


class ExtractAnswer(BaseModel):
    document_id: str
    model: str
    data: dict[str, Any]
    #: `laurium:<version>`, the library that read it.
    engine: str
