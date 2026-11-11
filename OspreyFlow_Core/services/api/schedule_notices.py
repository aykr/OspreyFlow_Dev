"""What marks an alert as a scheduled load's notice (ADR-110 Amendment 3 point 1, Amendment 19),
in a module of its own so the alert store and the scheduler both read it without importing each
other.

A notice is any alert whose `rule_id` is `schedule:<recipe id>` and that has no typology: the shape
the scheduler has always written, so a notice written before Amendment 19 is one too."""

from typing import Literal

#: The `rule_id` prefix of a schedule notice.
NOTICE_RULE_PREFIX = "schedule:"

#: ADR-110 Amendment 19: what a notice may say, one fixed sentence per kind, naming only the run
#: (its recipe and when it was due, or the file it was to read). Never an error's own text: that can
#: carry a host, a table or a source row's key (rule 7), and it stays in the ledger and the log.
NoticeKind = Literal[
    "failed", "timed_out", "refused_reach", "refused_rights", "sign_in_unavailable",
    "in_progress", "keyless_refresh", "refused_quota",
]  # fmt: skip

_NOTICE_ENDINGS: dict[str, str] = {
    "failed": "failed. Its pipeline's Runs, in the Ingest Studio, say why.",
    "timed_out": (
        "timed out before it finished. Its pipeline's Runs, in the Ingest Studio, say how far it "
        "got."
    ),
    "refused_reach": "was refused: it no longer reaches its case or its dataset.",
    "refused_rights": "was refused: its owner may no longer run it.",
    "sign_in_unavailable": "could not run: the sign-in service did not answer.",
    "in_progress": "did not run: an earlier run into its case was still going.",
    "keyless_refresh": (
        "was refused: its pipeline has no deduplication key, so a refresh would load its rows "
        "again."
    ),
    "refused_quota": (
        "was refused: today's run quota is used. The next may start after midnight, or an "
        "administrator may raise the quota in Admin › Running › Operations."
    ),
}  # fmt: skip


def notice_words(lead: str, kind: NoticeKind) -> str:
    """A notice's whole words: `lead` names the run (`The scheduled run of <recipe> due <time>`, or
    `The run of <recipe> on the file <name>`), then the kind's fixed sentence."""
    return f"{lead} {_NOTICE_ENDINGS[kind]}"


#: What a notice says when its stored words are not one of the sentences above: one written before
#: Amendment 19, as `"<run> failed: <the error's own text>"`, which can carry a host, a table or a
#: row's key (the merger's review: rule 7). Served in its place, never the stored words.
FALLBACK_WORDS = (
    "A scheduled load of yours did not run as planned. Its pipeline's Runs, in the Ingest Studio, "
    "say why."
)


def served_words(stored: str | None) -> str:
    """A notice's words as *Needs you* serves them: its own when they end in one of the fixed
    sentences, which only `notice_words` writes; else `FALLBACK_WORDS`."""
    if stored and any(stored.endswith(f" {ending}") for ending in _NOTICE_ENDINGS.values()):
        return stored
    return FALLBACK_WORDS
