"""rules-hyg item 3's live plants (rule 15), run on the leased stack's host from `OspreyFlow_Core`:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/rules/hyg/live_plants.py

Each plant changes the product code a live test guards, in the shape the bug would take at its own
call site (the store's SQL; the scheduler's words), runs that test file, and puts the file back from
a copy taken first, checked byte for byte, before the next. Prints each plant's failing cases and
the green run after all are back. Exit 1 if a plant goes green or a file is not put back.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ALERTS = Path("services/api/alerts.py")
SCHEDULER = Path("services/api/scheduler.py")
STORE_TEST = "../OspreyFlow_Build/tests/services/api/test_schedule_notices_needs_you.py"
EXECUTOR_TEST = (
    "../OspreyFlow_Build/tests/services/api/test_schedule_executor.py"
    "::test_a_graph_store_error_never_reaches_the_owners_words"
)
_EXECUTOR = "../OspreyFlow_Build/tests/services/api/test_schedule_executor.py"
PAUSE_TEST = f"{_EXECUTOR}::test_a_failed_exchange_is_told_failed_and_never_pauses_the_schedule"
QUOTA_SLOT_TEST = f"{_EXECUTOR}::test_a_quota_refusal_tells_its_owner_in_the_quota_sentence"
QUOTA_FILE_TEST = f"{_EXECUTOR}::test_a_quota_refused_file_tells_its_owner_the_quota_sentence"
SELECT = "SELECT {_COLUMNS}, count(*) OVER () AS total FROM alerts "
WHERE = (
    '"WHERE owner_id = $1 AND rule_id LIKE $2 AND typology IS NULL "\n'
    "                \"AND status = 'open' AND created_at >= $3 \""
)

PLANTS: list[tuple[str, Path, str, str, str]] = [
    ("the owner filter dropped from the list and the total", ALERTS, WHERE,
     WHERE.replace("owner_id = $1 AND", "$1::text IS NOT NULL AND"), STORE_TEST),
    ("the total counted over every owner", ALERTS, SELECT,
     SELECT.replace("count(*) OVER () AS total", "(SELECT count(*) FROM alerts a2 WHERE "
                    "a2.rule_id LIKE $2 AND a2.typology IS NULL AND a2.status = 'open' "
                    "AND a2.created_at >= $3) AS total"), STORE_TEST),
    ("typology IS NULL dropped", ALERTS, WHERE, WHERE.replace(" AND typology IS NULL", ""),
     STORE_TEST),
    ("status = 'open' dropped", ALERTS, WHERE, WHERE.replace("AND status = 'open' ", ""),
     STORE_TEST),
    ("the window dropped", ALERTS, WHERE,
     WHERE.replace("created_at >= $3", "$3::timestamptz IS NOT NULL"), STORE_TEST),
    ("a dataset reach put back, as reach_clause gives a reader outside any case", ALERTS, WHERE,
     WHERE.replace('created_at >= $3 "', 'created_at >= $3 AND dataset_id IS NULL "'),
     STORE_TEST),
    ("the error's text put back into the words", SCHEDULER,
     "notice_words(self._due(recipe, latest), failure_kind(error))",
     'f"{self._due(recipe, latest)} failed: {error}"', EXECUTOR_TEST),
    ("a failed exchange counted toward the three that pause", SCHEDULER,
     "                about_the_owner=False,  # never one of the three that pause (Amendment 3)\n",
     "", PAUSE_TEST),
    ("the quota refusal at a slot told in another kind", SCHEDULER,
     'notice_words(self._due(recipe, latest), "refused_quota")',
     'notice_words(self._due(recipe, latest), "failed")', QUOTA_SLOT_TEST),
    ("the quota refusal at a watched file told in another kind", SCHEDULER,
     'notice_words(words, "refused_quota")', 'notice_words(words, "failed")', QUOTA_FILE_TEST),
]  # fmt: skip


def pytest(target: str) -> tuple[int, str]:
    done = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", target, "-q",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [x for x in done.stdout.splitlines() if x.startswith("FAILED") or " passed" in x
             or " failed" in x]  # fmt: skip
    return done.returncode, "\n".join(lines)


def main() -> int:
    ok = True
    for label, path, old, new, target in PLANTS:
        text = path.read_text()
        if old == new or text.count(old) != 1:
            print(f"# --- plant ({label}): NOT PLANTED, no single site, or the plant changes nothing")
            ok = False
            continue
        keep = path.with_suffix(".keep")
        shutil.copyfile(path, keep)
        path.write_text(text.replace(old, new))
        code, said = pytest(target)
        shutil.copyfile(keep, path)
        keep.unlink()
        back = path.read_text() == text
        print(f"# --- plant ({label}) in {path}: exit {code}")
        print(f"#     - {old.strip()}")
        print(f"#     + {new.strip() or '(the line removed)'}")
        print(said)
        if code == 0:
            print("    GREEN under a plant: the test cannot see this defect")
            ok = False
        if not back:
            print(f"    {path} NOT put back")
            ok = False
    print("# --- green, every plant put back")
    for target in (STORE_TEST, _EXECUTOR):
        code, said = pytest(target)
        print(said)
        ok = ok and code == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
