"""The DuckDB lock holder is not running when seeding is requested — a rehearsal-derived check.

**`DEMO_GUIDE.md`'s own words for the fault:** "seeding needs the Conduit stopped (DuckDB takes an
exclusive lock the Conduit's own `AnalyticsPort` also holds a handle to) — so the Conduit starts
twice, not once, with seeding in between."

**The check opens the file for real rather than hunting for a process.** A `pgrep` for `uvicorn`
would miss a lock held by anything else — a stray `python -m scripts.seed_fixture_corp`, an editor's
DuckDB extension, a second harness — and would report a process that happens to be running but has
already closed its handle. The question is "can this be locked right now", so the check tries, and
closes again immediately if it succeeds.
"""

from __future__ import annotations

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped

NAME = "duckdb-lock"


def check(context: PreflightContext) -> CheckResult:
    if not context.seeding:
        return skipped(
            NAME,
            reason=(
                "seeding was not requested, and the exclusive DuckDB lock only blocks a seed. "
                "Not checked — pass --seeding to check it."
            ),
        )

    path = context.analytics_db_path
    detail = (f"analytics store: {path}",)

    if not path.exists():
        return passed(
            NAME,
            detail=(*detail, "the store does not exist yet, so nothing can be holding it"),
        )

    try:
        import duckdb
    except ImportError:  # pragma: no cover - duckdb is a hard dependency of this project
        return skipped(NAME, reason="duckdb is not importable here, so the lock was not checked.")

    try:
        connection = duckdb.connect(str(path))
    except Exception as error:  # duckdb raises IOException; catching broadly keeps this honest
        return failed(
            NAME,
            what_is_wrong=(
                f"another process is holding an exclusive lock on {path}, so a seed would fail "
                f"partway through: {error}"
            ),
            what_to_do=(
                "Stop the Conduit before seeding and start it again afterwards — it holds a "
                "handle through its own AnalyticsPort. The demo sequence starts it twice for "
                "exactly this reason. If the Conduit is already stopped, something else has the "
                "file: `lsof " + str(path) + "` names it."
            ),
            detail=detail,
        )
    connection.close()
    return passed(NAME, detail=(*detail, "no other process holds the lock"))
