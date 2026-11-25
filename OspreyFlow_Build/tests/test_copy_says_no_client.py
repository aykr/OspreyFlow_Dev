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

**The pages service's copy** (slice IS5a0; the Glass's own copy is held by the workspace's vitest files, which this slice
may not touch): the templates and modules of `apps/pages/tree-default`, `apps/pages/modules` and `apps/pages/server/views`
are read for the same words by `pages_copy_hits`, templates with their `{# #}` comments blanked and modules with their
comments blanked, so a note to a developer is not copy. `test_pages_copy_names_no_client_or_unsettled_setting` holds the
real tree, and `tests/glass_trees/test_pages_foundation.py` shows each root flagged with a planted line.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from tools.ui_words_check import strip_comments

from tests.test_copy_says_pipeline import CORE, SCANNED, _modules, found

WORDS = re.compile(
    r"\bclient's\b|\bclients'|\bclient parity\b|to be confirmed|\bTBC\b|\bunconfirmed\b"
    r"|\bnot confirmed\b",
    re.IGNORECASE,
)
#: A dependency's own words, replayed as measured: not ours to say.
REPLAYED = {CORE / "packages" / "adapters" / "model_litellm" / "stand_in.py"}
WEIGHTS = CORE / "packages" / "ontology" / "weights"


#: The pages service's copy, relative to the product folder: the Default tree's templates, the client modules, and the
#: server's own views (ADR-152 decision 6).
PAGES_COPY_ROOTS = (
    "apps/pages/tree-default",
    "apps/pages/tree-govuk",
    "apps/pages/modules",
    "apps/pages/server/views",
)


def pages_copy_hits(core: Path = CORE, word: re.Pattern[str] = WORDS) -> list[str]:
    """`path:line: text` for each line of the pages' copy that holds `word`, paths relative to `core`, sorted."""
    hits: list[str] = []
    for root in PAGES_COPY_ROOTS:
        for path in sorted((core / root).rglob("*")):
            if path.suffix not in {".njk", ".ts", ".html"} or not path.is_file() or ".test." in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".ts":
                text = strip_comments(text)
            else:
                text = re.sub(r"\{#.*?#\}", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
            for number, line in enumerate(text.splitlines(), start=1):
                if word.search(line):
                    hits.append(f"{path.relative_to(core).as_posix()}:{number}: {line.strip()}")
    return hits


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


def test_pages_copy_names_no_client_or_unsettled_setting() -> None:
    assert pages_copy_hits() == []


def test_the_pages_walker_finds_each_shape_and_leaves_a_comment_alone(tmp_path: Path) -> None:
    core = tmp_path / "core"
    for root in PAGES_COPY_ROOTS:
        (core / root).mkdir(parents=True)
    (core / "apps/pages/tree-default/a.njk").write_text(
        "{# the client's note to a developer #}\n<p>Its terms are to be confirmed.</p>\n", encoding="utf-8"
    )
    (core / "apps/pages/modules/a.ts").write_text(
        "// the client's comment\nexport const note = `TBC`;\n", encoding="utf-8"
    )
    assert [h.split(": ")[0] for h in pages_copy_hits(core)] == [
        "apps/pages/tree-default/a.njk:2",
        "apps/pages/modules/a.ts:2",
    ]
