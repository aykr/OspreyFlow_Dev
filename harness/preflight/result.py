"""The shape every Preflight check returns, and the probes they read the world through.

`05_DEPLOYMENT.md` §2.1: "A failure explains what is wrong and what to do about it, with a
**Re-check** button rather than a loop of edit-and-rerun." Those two sentences are why
`what_is_wrong` and `what_to_do` are separate required fields rather than one message string — a
check that only says what is wrong sends the operator back to this document to work out the rest,
which is the loop the Re-check button exists to replace.

**`skip` is a third status, not a lenient `pass`.** A GPU driver version that cannot be read on this
platform, or cluster connectivity at `local-lite`, is not a check that passed: it is a check that
did not run, and saying so is the difference between "your GPU driver is fine" and "nobody looked".
Every `skip` carries its own reason in `what_is_wrong`, in those terms.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    #: Something is genuinely wrong and Launch may still proceed. Distinct from `skip`, which means
    #: nobody looked, and from `fail`, which blocks. A `warn` is a finding with a remedy the
    #: operator can apply *after* install — and it must have one, or it is a `fail` in disguise.
    #:
    #: **Awaiting owner confirmation.** Introducing a fourth status softens `05_DEPLOYMENT.md`
    #: §2.1's "Preflight must pass before Launch is enabled", which is a real change to what that
    #: gate promises, so it is marked rather than assumed.
    WARN = "warn"


@dataclass(frozen=True)
class CheckResult:
    """One check's own answer.

    `rechecked_at` is set on every run, including the first, because the Re-check button's whole
    purpose is telling a stale result from a fresh one — a field only populated on re-runs would
    leave the first result indistinguishable from one nobody has re-run.
    """

    check: str
    status: Status
    what_is_wrong: str = ""
    what_to_do: str = ""
    rechecked_at: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    #: Free-form, printed under the result. `05_DEPLOYMENT.md`'s own bind-address finding needs the
    #: check to *print* what it saw, not merely judge it.
    detail: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Does this result allow Launch? A `skip` does not block — a check that could not run is
        not evidence of a fault. Nor does a `warn`: it is a real finding whose remedy is available
        after install, which is precisely what distinguishes it from a `fail`."""
        return self.status not in (Status.FAIL,)


def passed(check: str, *, detail: tuple[str, ...] = ()) -> CheckResult:
    return CheckResult(check=check, status=Status.PASS, detail=detail)


def failed(
    check: str, *, what_is_wrong: str, what_to_do: str, detail: tuple[str, ...] = ()
) -> CheckResult:
    if not what_is_wrong or not what_to_do:
        raise ValueError(
            f"{check}: a failing check must say both what is wrong and what to do about it "
            "(05_DEPLOYMENT.md §2.1) — one without the other is the edit-and-rerun loop the "
            "Re-check button exists to replace"
        )
    return CheckResult(
        check=check,
        status=Status.FAIL,
        what_is_wrong=what_is_wrong,
        what_to_do=what_to_do,
        detail=detail,
    )


def warned(
    check: str, *, what_is_wrong: str, what_to_do: str, detail: tuple[str, ...] = ()
) -> CheckResult:
    """A finding that does not block Launch.

    Requires a remedy for the same reason `failed()` does, and for a sharper one: a warning with no
    remedy is noise an operator learns to scroll past, and the next real one scrolls past with it.
    """
    if not what_is_wrong or not what_to_do:
        raise ValueError(
            f"{check}: a warning must say both what is wrong and what to do about it — a warning "
            "with no remedy is noise, and noise is how a real finding gets missed"
        )
    return CheckResult(
        check=check,
        status=Status.WARN,
        what_is_wrong=what_is_wrong,
        what_to_do=what_to_do,
        detail=detail,
    )


def skipped(check: str, *, reason: str, detail: tuple[str, ...] = ()) -> CheckResult:
    if not reason:
        raise ValueError(f"{check}: a skipped check must say why it did not run, not merely skip")
    return CheckResult(
        check=check,
        status=Status.SKIP,
        what_is_wrong=reason,
        what_to_do="Nothing here — this check did not run. It is not evidence that the thing it "
        "would have checked is correct.",
        detail=detail,
    )


#: A check reads the world through its context and returns one result. Deliberately not a class
#: hierarchy: a check is a function of the environment, and the only thing every check shares is
#: this signature.
Check = Callable[["object"], CheckResult]
