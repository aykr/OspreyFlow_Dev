"""No words the Conduit gives a person, and no data the Glass shows, name the client or a setting still
to be confirmed (the owner, 14 November 2026: the Connection strength legend said "(the client's)" and
"to be confirmed with the client"). The Glass's own copy is held by
`apps/workspace/src/copyNoClient.test.ts`.

**What is read.** The same strings as `test_copy_says_pipeline.py` (the Conduit, the ingest engine,
the adapters, the shared models; a refusal, an f-string, a string joined from parts), and every string
in the strength weights files, whose influencers' notes the legend shows beside them.

**What is looked for.** The client as a customer ("the client's", "client parity") and a setting not
yet settled ("to be confirmed", "TBC", "unconfirmed", "not confirmed"). An identity provider's
*client* (a client-credentials grant, `manage-clients`, an orchestrator's sign-in client) is another
word, said to an operator or an orchestrator, and is not looked for. Nor is the stand-in gateway's
replay of LiteLLM's own measured words (`stand_in.py`).

Shown red by `test_the_check_finds_each_shape_the_words_took`, planted in today's shapes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from tests.test_copy_says_pipeline import CORE, SCANNED, _modules, found

WORDS = re.compile(
    r"\bclient's\b|\bclients'|\bclient parity\b|to be confirmed|\bTBC\b|\bunconfirmed\b"
    r"|\bnot confirmed\b",
    re.IGNORECASE,
)
#: A dependency's own words, replayed as measured: not ours to say.
REPLAYED = {CORE / "packages" / "adapters" / "model_litellm" / "stand_in.py"}
WEIGHTS = CORE / "packages" / "ontology" / "weights"


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _data_hits(text: str) -> list[str]:
    return [s for s in _strings(yaml.safe_load(text)) if WORDS.search(s)]


def test_no_message_to_a_person_names_the_client_or_an_unsettled_setting() -> None:
    hits = [
        f"{p.relative_to(CORE)}:{line}: {words}"
        for p in _modules(SCANNED)
        if p not in REPLAYED
        for line, words in found(p, word=WORDS)
    ]
    assert hits == []


def test_no_strength_weights_file_holds_such_a_note() -> None:
    hits = [
        f"{p.relative_to(CORE)}: {s}"
        for p in sorted(WEIGHTS.glob("*.yaml"))
        for s in _data_hits(p.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_the_check_finds_each_shape_the_words_took() -> None:
    """Rule 15, at the shapes these words took before this change."""
    planted = '''
from fastapi import HTTPException

BLANK_LICENCE = "the client's own list: its terms are the client's"

def scale_words(strength) -> str:
    return f"connection strength {strength.raw_sum:.2f} on the client's scale with them"

def refuse(role: str) -> None:
    raise HTTPException(status_code=409, detail=f"The {role} model is the client's own provider, "
                        "and it may not be sent to it")

REASON = (
    "no open licence was found for the list; "
    "its terms are to be confirmed with the UN"
)

def unsettled(why: str) -> None:
    raise ValueError(f"this list's licence is not confirmed: {why}")
'''
    lines = sorted(line for line, _ in found(Path("planted.py"), planted, word=WORDS))
    assert lines == [4, 7, 10, 14, 19]
    weights = "influencers:\n  - id: a\n    label: A\n    note: to be confirmed with the client\n"
    assert _data_hits(weights) == ["to be confirmed with the client"]


def test_the_check_leaves_an_identity_provider_s_client_alone() -> None:
    clean = '''
"""The client's docstring, which no person is shown."""
import logging

log = logging.getLogger(__name__)

def refuse() -> None:
    "the client's string standing as a comment"
    log.info("the client's call %s", 1)
    raise ValueError("sign in with the client-credentials grant of the client it is owned by")
    raise ValueError("its account needs manage-users, manage-clients and view-events")
    scale = "client"
'''
    assert found(Path("clean.py"), clean, word=WORDS) == []
