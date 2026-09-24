"""The interpreter is the project venv, not system Python — a rehearsal-derived check.

One of the four failures the 23 September 2026 demo rehearsal actually hit. It is worth a check of
its own because of how it fails: a system Python resolves every import that happens to be installed
globally and fails on the ones that are not, so the operator sees a `ModuleNotFoundError` for one
package rather than "you are running the wrong interpreter". The first is a package problem, the
second is the real problem, and only the second has a one-line remedy.
"""

from __future__ import annotations

from pathlib import Path

from harness.preflight.context import REPO_ROOT, PreflightContext
from harness.preflight.result import CheckResult, failed, passed

NAME = "interpreter"

PROJECT_VENV = REPO_ROOT / ".venv"


def check(context: PreflightContext) -> CheckResult:
    interpreter = Path(context.interpreter)
    detail = (f"interpreter: {interpreter}", f"project venv: {PROJECT_VENV}")

    # Resolve the *directory*, never the interpreter file itself. `.venv/bin/python` is a symlink
    # to whatever base interpreter created the venv — on this machine, miniconda — so resolving the
    # file walks straight out of the venv and the check reports a correct setup as broken. Found by
    # running this check against its own repository before it had a test: it failed on the very
    # interpreter it is meant to accept.
    try:
        inside_project_venv = interpreter.parent.resolve().is_relative_to(PROJECT_VENV.resolve())
    except OSError:
        inside_project_venv = False

    if inside_project_venv:
        return passed(NAME, detail=detail)

    return failed(
        NAME,
        what_is_wrong=(
            f"this is running under {interpreter}, which is not the project virtual environment "
            f"at {PROJECT_VENV}. Imports will resolve against whatever happens to be installed "
            "system-wide, so the first failure you see will name a missing package rather than "
            "the wrong interpreter."
        ),
        what_to_do=(
            "Run through the project venv — `.venv/bin/python -m harness.preflight`, or activate "
            "it first with `source .venv/bin/activate`. If the venv does not exist yet, `uv sync` "
            "creates it."
        ),
        detail=detail,
    )
