"""Laurium's service (`06_DECISIONS.md` ADR-135 Amendment 6): Laurium 0.6.0 on Python 3.13 behind
one call, `POST /v1/extract` (`app_contract.py` has the request, the answer and each refusal).

**Laurium's own pieces, every call through the gateway.** For each document the service maps the
request's JSON Schema to Laurium's (`schema_map`), builds Laurium's model, prompt and output parser
(`make_dynamic_example_model`, `prompts.create_prompt`, LangChain's `PydanticOutputParser`, as
Laurium's documentation does), its chat model with Laurium's `create_llm` on the `openai` platform
with the gateway as `openai_api_base` and the call's own gateway token, and Laurium's
`BatchExtractor`.

**It awaits the extractor's chain for the one document, not `process_chunk`** (decision 5):
Laurium's `BatchExtractor` catches each row's failure and returns it with every field `None`,
which here would be an empty finding standing for a refused key or an unknown model. So each
failure is answered as itself: the gateway's refusal with its status, an unparseable answer after
`ATTEMPTS` tries.

**Settings are checked whole at import**, so the process never serves with any of them wrong
(`settings.py`): the words are written to standard error and the process exits.

The gateway token arrives with each call and is used for that call alone: never kept, logged or
answered back. Nothing of a document or an answer is logged.
"""

from __future__ import annotations

import os
import sys
from importlib.metadata import version
from typing import Any

import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser

from laurium.decoder_models import BatchExtractor, create_llm, prompts
from laurium.decoder_models.pydantic_models import make_dynamic_example_model

from .app_contract import ATTEMPTS, MAX_CHARS, ExtractAnswer, ExtractAsk
from .schema_map import UnsupportedSchema, descriptions_for, laurium_schema, output_for
from .settings import RefusedSetting, Settings

try:
    SETTINGS = Settings.from_env(os.environ)
except RefusedSetting as refused:
    print(str(refused), file=sys.stderr, flush=True)
    raise SystemExit(78) from None  # EX_CONFIG

ENGINE = f"laurium:{version('laurium')}"

#: Laurium's system message for every document: ours, with no braces (the prompt is a template).
SYSTEM = (
    "You read one document and report the findings it states, for an analyst to review. Report "
    "only what the document itself says; never guess, and leave a list empty when the document "
    "names nothing of that kind. Answer with one JSON object and nothing else."
)

app = FastAPI(title="OspreyFlow Laurium")


def _refused(status: int, kind: str, **more: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"refusal": kind, **more})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "engine": ENGINE}


@app.post("/v1/extract", response_model=None)
async def extract(ask: ExtractAsk, request: Request) -> ExtractAnswer | JSONResponse:
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        return _refused(401, "no_gateway_token")
    if len(ask.text) > MAX_CHARS:
        return _refused(413, "too_long")
    try:
        fields = laurium_schema(ask.json_schema)
    except UnsupportedSchema as exc:
        return _refused(400, "unsupported_schema", words=str(exc))

    descriptions = descriptions_for(ask.json_schema)
    findings = make_dynamic_example_model(fields, descriptions, "Findings")
    parser = PydanticOutputParser(pydantic_object=findings)
    prompt = prompts.create_prompt(
        system_message=SYSTEM,
        examples=[],
        example_human_template="",
        example_assistant_template="",
        final_query="{text}",
        schema=fields,
        descriptions=descriptions,
    )
    llm = create_llm(
        llm_platform="openai",
        model_name=ask.model,
        api_key=token,
        openai_api_base=SETTINGS.gateway_url,
        temperature=0.0,
    )
    call: dict[str, Any] = {"timeout": SETTINGS.timeout_seconds}
    if ask.tag:
        # ADR-135 Amendment 3: the gateway records the call's usage under its tag.
        call["extra_body"] = {"metadata": {"tags": [ask.tag]}}
    extractor = BatchExtractor(
        llm=llm.bind(**call),
        prompt=prompt,
        parser=parser,
        max_retries=ATTEMPTS,
    )

    for _ in range(ATTEMPTS):
        try:
            parsed = await extractor.chain.ainvoke(ask.text)
        except OutputParserException:
            continue
        except openai.APIStatusError as exc:
            refusal: dict[str, Any] = {"gateway_status": exc.status_code}
            if exc.status_code == 429:
                try:
                    refusal["gateway_error"] = exc.response.json().get("error")
                except ValueError:
                    pass
            return _refused(502, "gateway", **refusal)
        except (openai.APIConnectionError, openai.APITimeoutError):
            return _refused(504, "gateway_unreachable")
        return ExtractAnswer(
            document_id=ask.document_id,
            model=ask.model,
            data=output_for(parsed, ask.json_schema),
            engine=ENGINE,
        )
    return _refused(502, "unparseable")
