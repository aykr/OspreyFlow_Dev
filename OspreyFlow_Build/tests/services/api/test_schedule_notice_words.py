"""ADR-110 Amendment 19, the orchestrator's ruling of 10 November 2026: a scheduled load's notice
says one fixed sentence per kind, naming only the run, never an error's own text (rule 7). Offline:
the words and the kind an error is told as. The executor's own call sites, with an error planted in
the graph adapter's real shape, are proven live in `test_schedule_executor.py`
(`test_a_graph_store_error_never_reaches_the_owners_words`).

What a mistake would do, and the case that catches it (red record:
`process/lanes/rules/hyg/3-schedule-notices-red.txt`):

- an error's text put back into the words, or a kind's sentence made from it:
  `test_each_kind_is_one_fixed_sentence_after_the_runs_name`;
- a timeout, or a run still going, told as a plain failure, or an unknown error told as anything
  but one: `test_an_error_is_told_by_its_kind_alone`.
"""

from __future__ import annotations

from typing import get_args

import pytest
from adapters.graph_arcadedb.client import ArcadeDBError
from services.api.schedule_notices import (
    FALLBACK_WORDS,
    NoticeKind,
    notice_words,
    served_words,
)
from services.api.scheduler import failure_kind
from services.ingest.engine import RowKeyRunInProgress

LEAD = "The scheduled run of Daily export due 2 June 2026 at 06:00"
EXPECTED = {
    "failed": "failed. Its pipeline's Runs, in the Ingest Studio, say why.",
    "timed_out": (
        "timed out before it finished. Its pipeline's Runs, in the Ingest Studio, say how far it got."
    ),
    "refused_reach": "was refused: it no longer reaches its case or its dataset.",
    "refused_rights": "was refused: its owner may no longer run it.",
    "sign_in_unavailable": "could not run: the sign-in service did not answer.",
    "in_progress": "did not run: an earlier run into its case was still going.",
    "refused_quota": (
        "was refused: today's run quota is used. The next may start after midnight, or an "
        "administrator may raise the quota in Admin › Running › Operations."
    ),
    "keyless_refresh": (
        "was refused: its pipeline has no deduplication key, so a refresh would load its rows again."
    ),
}


@pytest.mark.parametrize("kind", get_args(NoticeKind))
def test_each_kind_is_one_fixed_sentence_after_the_runs_name(kind: NoticeKind) -> None:
    assert set(EXPECTED) == set(get_args(NoticeKind)), (
        "a kind with no sentence written here"
    )
    assert notice_words(LEAD, kind) == f"{LEAD} {EXPECTED[kind]}"


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (ArcadeDBError('ArcadeDB error 500: {"detail":"Duplicated key [ROW-7731]"}', status_code=500),
         "failed"),
        (ValueError("column amount is missing"), "failed"),
        (TimeoutError("read timed out from db.internal:5432"), "timed_out"),
        (TimeoutError(), "timed_out"),
        (RowKeyRunInProgress("recipe-1"), "in_progress"),
    ],
)  # fmt: skip
def test_an_error_is_told_by_its_kind_alone(
    error: BaseException, kind: NoticeKind
) -> None:
    assert failure_kind(error) == kind
    words = notice_words(LEAD, failure_kind(error))
    assert str(error) == "" or str(error) not in words
    for leaked in ("ROW-7731", "db.internal", "column amount", "ArcadeDB"):
        assert leaked not in words


def test_only_a_fixed_sentence_is_served_and_anything_else_is_the_fallback() -> None:
    """The merger's review: a notice's stored words are served only when they end in one of the
    fixed sentences; one from before the amendment, with its error's own text, is not."""
    for kind in get_args(NoticeKind):
        assert served_words(notice_words(LEAD, kind)) == notice_words(LEAD, kind)
    for old in (f"{LEAD} failed: ArcadeDB error 500: Duplicated key [ROW-7731]",
                f"{LEAD} was refused: the schedule's owner, approver-1, can no longer sign in",
                "", None):  # fmt: skip
        assert served_words(old) == FALLBACK_WORDS
