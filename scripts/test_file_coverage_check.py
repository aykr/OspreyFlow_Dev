"""A drift gate for CI test-file coverage — the same shape as `scripts/domain_model_coverage_
check.py`/`scripts/route_coverage_check.py`: a real check against a real source (`.github/
workflows/ci.yml`'s own job commands, not a hand-maintained list), paired with an explicit
allowlist of currently-undocumented exceptions, each with a stated reason.

**The bug this exists to catch, precisely — found four times before this gate existed
(`test_pattern_store.py`, `test_alerts.py`, `test_change_stream.py`, `test_assessment_routes.py`,
per each file's own landing history in `.github/workflows/ci.yml`'s comments), each time by
accident.** A test file needing a real service (Postgres, ArcadeDB, Valkey) was *not* invisible to
CI — the fast `test` job's own default collection (`pyproject.toml`'s `testpaths = ["tests"]`,
minus that job's own `--ignore` list) picked it up regardless, since nothing excluded it. It ran
there, with no live service guaranteed up, and either failed in a way nobody connected to "this
file is mis-wired" rather than "this test is broken," or passed by luck depending on the runner's
own incidental state. The fix each time was adding the file to *both* the fast job's own
`--ignore` list *and* a live-service job's own explicit file list, together — before the fix, it
was in *neither*. A gate checking only "is this file referenced by some job" would not have caught
any of the four: each file *was* referenced, by the fast job's own broad, unignored collection,
which is exactly the wrong kind of reference.

**Two checks, not one, for exactly that reason.**

1. **The orphan check** (`find_orphaned`). Every real test file (one containing at least one
   `test_*` function — `conftest.py`, fixture-only modules like `tests/services/api/working_set/
   fakes.py`, and files with no such function are excluded) must be reachable by at least one CI
   job's own collection — an explicit file/directory listed in a job's run command, or the `test`
   job's default-minus-ignore collection — or appear in the allowlist with a stated reason.

2. **The live-service classification check** (`find_misclassified`) — the one that actually
   catches the historical bug. A file is classified as needing a live service if its own source
   imports or calls any of `LIVE_SERVICE_MARKERS` below (derived directly from this repo's own
   live-service test files — `test_assessments.py`, `test_export.py`, `test_pattern_store.py`,
   `test_alerts.py`, `test_change_stream.py`, `test_assessment_routes.py` — not guessed). Every
   such file must be **both** in the `test` job's own `--ignore` list **and** in a live-service
   job's own explicit file list (`conformance`, `conformance-model`, `conformance-model-vision`,
   or `conformance-guard`'s own directory argument) — a file failing either half is named
   specifically, not merely counted.

**Parsing `ci.yml` as text, deliberately, the same pragmatic choice `route_coverage_check.py`'s own
`_DOC_ROUTE_LINE` regex already makes** — a full YAML+shell parse of a folded (`>-`) multi-line
`run:` block buys nothing a plain-text token scan does not, for a file whose only structure this
gate cares about is "which `tests/...` tokens appear, ignored or not, in which job's block."

**First real run found the Makefile itself 22 files out of sync with `ci.yml`** — `make test`'s own
`--ignore` list and `make test-all`'s own explicit list had silently drifted to a strict subset of
`ci.yml`'s equivalents, meaning a developer running either target locally would hit the identical
failure mode this gate exists to catch, just outside CI. Fixed in the same change that added this
gate (`Makefile`'s own `test`/`test-all` targets, now kept in sync by eye until this gate's own
scope is widened to check the Makefile too — a disclosed gap, not solved here, since parsing
`Makefile`'s own line-continuation shape is a second, different
text format from `ci.yml`'s YAML).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
CI_YML_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "test_file_coverage_allowlist.txt"

#: Derived directly from this repo's own real live-service test files — not guessed. A file that
#: actually *imports* any of these names needs a real ArcadeDB, Valkey or Postgres to pass, not a
#: fake. Checked against real `import`/`from ... import` statements (`_imported_names` below), not
#: raw substring search over the whole file — a docstring *naming* one of these to explain that the
#: file does *not* use it (`tests/services/api/working_set/test_service.py`'s own module docstring:
#: "not `ValkeyWorkingSetStore` or a real adapter") would otherwise false-positive. Each of these
#: is unambiguous by its own presence — an adapter/client/store class, or the `asyncpg` driver
#: itself, that is only ever imported to open a real connection.
LIVE_SERVICE_MARKERS: frozenset[str] = frozenset(
    {
        "arcadedb_adapter",
        "ArcadeDBClient",
        "ArcadeDBConfig",
        "ValkeyWorkingSetStore",
        "Valkey",
        "asyncpg",
    }
)

#: `PostgresConfig` is not import-sufficient like the markers above — found live, not assumed:
#: `test_auth.py`/`test_websocket_auth.py` both import it only to build an inert `ApiConfig` with
#: dummy placeholder credentials (`PostgresConfig(host="localhost", ..., user="x", password="x",
#: database="x")`) never connected to, since the routes those tests exercise never touch Postgres.
#: `.from_env()` — reading whatever this environment actually has configured, the same call
#: `JudgementStore.connect`/`ExportLedgerStore.connect`/every other real store in this repo makes —
#: is the real signal; checked as an `ast.Call` whose own `.func` is an `Attribute` named
#: `from_env` on a `Name` in this set, not a substring, for the same docstring-false-positive
#: reason the import-based markers above are AST-checked rather than grepped.
CALL_REQUIRED_MARKERS: frozenset[str] = frozenset({"PostgresConfig"})

#: Job header lines this gate reads — `.github/workflows/ci.yml`'s own top-level job names, in the
#: order they appear. `test` is the fast, ignore-based job; the rest are live-service jobs whose
#: own explicit file/dir lists this gate treats as "covered, and correctly wired if also ignored
#: by `test`."
_JOB_HEADER = re.compile(r"^  ([a-z][a-z0-9_-]*):\s*$", re.MULTILINE)
_PYTEST_TOKEN = re.compile(r"(--ignore=)?(tests/[\w./-]*)")


def list_test_files() -> list[Path]:
    """Every file under `tests/` containing at least one `test_*` function — `conftest.py` and
    fixture-only modules (no such function) are excluded, the same "a file is a test file iff
    pytest would actually collect something from it" bar this gate's own two checks both need."""
    files = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if path.name in {"conftest.py", "__init__.py"}:
            continue
        source = path.read_text(encoding="utf-8")
        if _has_test_function(source):
            files.append(path)
    return files


def _has_test_function(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test_"
        ):
            return True
    return False


def _job_blocks(ci_text: str) -> dict[str, str]:
    """Splits `ci.yml`'s text into `{job_name: job_body_text}` by the top-level job headers —
    good enough for this gate's own purpose (finding `tests/...` tokens inside each job's `run:`
    lines), not a general YAML job parser."""
    matches = list(_JOB_HEADER.finditer(ci_text))
    blocks: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(ci_text)
        blocks[m.group(1)] = ci_text[start:end]
    return blocks


def _pytest_run_lines(job_body: str) -> str:
    """The job body text from its first `pytest`/`uv run pytest` invocation onward — every
    `tests/...` token anywhere after that point in the job is treated as belonging to that
    invocation, which is correct for every job this gate reads today (one `run: pytest ...` step
    per job, `>-`-folded across several physical lines) and stated as this gate's own known
    boundary otherwise."""
    idx = job_body.find("pytest")
    return job_body[idx:] if idx != -1 else ""


def job_tokens(job_body: str) -> tuple[set[str], set[str]]:
    """`(ignored, positional)` — every `tests/...` token in the job's own pytest invocation,
    split by whether it followed `--ignore=`. A bare directory token (no trailing `.py`) is kept
    as-is; callers treat it as covering every test file under it."""
    run_text = _pytest_run_lines(job_body)
    ignored: set[str] = set()
    positional: set[str] = set()
    for is_ignore, token in _PYTEST_TOKEN.findall(run_text):
        token = token.rstrip("/")
        if not token or token == "tests":
            continue
        (ignored if is_ignore else positional).add(token)
    return ignored, positional


def _covers(token: str, rel_path: str) -> bool:
    """Whether a job token (a file or a bare directory, both relative to the repo root, `tests/...`
    form) covers `rel_path` (also `tests/...` form)."""
    return rel_path == token or rel_path.startswith(token + "/")


def load_allowlist(path: Path = ALLOWLIST_PATH) -> set[str]:
    if not path.exists():
        return set()
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped.split()[0])
    return entries


def find_orphaned(
    test_files: list[str], test_job_ignored: set[str], live_job_tokens: dict[str, set[str]]
) -> list[str]:
    """Every test file reachable by no job at all: not covered by any live-service job's own
    explicit tokens, and either ignored by `test` (so not covered by its default collection
    either) or simply absent from every live-service job while also not benefiting from `test`'s
    own broad collection because it *is* ignored there with nowhere else to run."""
    orphaned = []
    for rel_path in test_files:
        covered_by_live_job = any(
            any(_covers(tok, rel_path) for tok in tokens) for tokens in live_job_tokens.values()
        )
        covered_by_test_default = rel_path not in test_job_ignored and not any(
            _covers(tok, rel_path) for tok in test_job_ignored
        )
        if not covered_by_live_job and not covered_by_test_default:
            orphaned.append(rel_path)
    return sorted(orphaned)


def _imported_names(source: str) -> set[str]:
    """Every name a module actually imports (`import X`, `from Y import X`, `from Y import X as
    Z` — `Z`, the local binding, plus `X`, since either could match a marker) — never a docstring
    or comment mention, which `ast.parse` structurally cannot confuse with a real import."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).rsplit(".", 1)[-1])
                names.add(alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
                names.add(alias.name)
    return names


def _has_from_env_call(source: str, names: frozenset[str]) -> bool:
    """True if the source calls `<name>.from_env(...)` for any `name` in `names`, via a real
    `ast.Call` node, not a substring match."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "from_env"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in names
        ):
            return True
    return False


def is_live_service_file(source: str) -> bool:
    if _imported_names(source) & LIVE_SERVICE_MARKERS:
        return True
    return _has_from_env_call(source, CALL_REQUIRED_MARKERS)


def find_misclassified(
    test_files_abs: list[Path],
    test_job_ignored: set[str],
    live_job_tokens: dict[str, set[str]],
) -> list[str]:
    """Every live-service-marked file missing from either half of the required pairing: the
    `test` job's own `--ignore` list, and at least one live-service job's own explicit coverage.
    Returns one message per offending file, naming which half it failed."""
    problems = []
    for path in test_files_abs:
        rel_path = str(path.relative_to(REPO_ROOT))
        if not is_live_service_file(path.read_text(encoding="utf-8")):
            continue
        ignored = rel_path in test_job_ignored or any(
            _covers(tok, rel_path) for tok in test_job_ignored
        )
        covered = any(
            any(_covers(tok, rel_path) for tok in tokens) for tokens in live_job_tokens.values()
        )
        if not ignored and not covered:
            problems.append(
                f"{rel_path}: in neither the `test` job's ignore list nor any live-service job"
            )
        elif not ignored:
            problems.append(
                f"{rel_path}: needs a live service but is not ignored by the `test` job"
            )
        elif not covered:
            problems.append(f"{rel_path}: ignored by `test` but not run by any live-service job")
    return sorted(problems)


def find_stale_entries(
    test_files: list[str],
    test_job_ignored: set[str],
    live_job_tokens: dict[str, set[str]],
    allowlist: set[str],
) -> list[str]:
    live_set = set(test_files)
    orphaned = set(find_orphaned(test_files, test_job_ignored, live_job_tokens))
    return sorted(entry for entry in allowlist if entry not in live_set or entry not in orphaned)


def _load(ci_yml_path: Path = CI_YML_PATH) -> tuple[set[str], dict[str, set[str]]]:
    ci_text = ci_yml_path.read_text(encoding="utf-8")
    blocks = _job_blocks(ci_text)
    test_ignored, _ = job_tokens(blocks.get("test", ""))
    live_job_tokens: dict[str, set[str]] = {}
    for name in (
        "conformance",
        "conformance-model",
        "conformance-model-vision",
        "conformance-guard",
    ):
        _, positional = job_tokens(blocks.get(name, ""))
        live_job_tokens[name] = positional
    return test_ignored, live_job_tokens


def main() -> int:
    test_job_ignored, live_job_tokens = _load()
    test_files_abs = list_test_files()
    test_files = [str(p.relative_to(REPO_ROOT)) for p in test_files_abs]
    allowlist = load_allowlist()

    orphaned = find_orphaned(test_files, test_job_ignored, live_job_tokens)
    new_orphans = sorted(set(orphaned) - allowlist)
    misclassified = find_misclassified(test_files_abs, test_job_ignored, live_job_tokens)
    stale = find_stale_entries(test_files, test_job_ignored, live_job_tokens, allowlist)

    ok = True
    if new_orphans:
        ok = False
        print(
            "test-file-coverage-check: test file(s) reachable by no CI job and not in the "
            f"allowlist: {', '.join(new_orphans)}",
            file=sys.stderr,
        )
    if misclassified:
        ok = False
        print(
            "test-file-coverage-check: live-service test file(s) not correctly wired "
            f"(need both a `test`-job ignore and a live-service-job listing): "
            f"{'; '.join(misclassified)}",
            file=sys.stderr,
        )
    if stale:
        ok = False
        print(
            f"test-file-coverage-check: stale allowlist entr(ies) in "
            f"{ALLOWLIST_PATH.relative_to(REPO_ROOT)} — remove: {', '.join(stale)}",
            file=sys.stderr,
        )
    if ok:
        print(
            f"test-file-coverage-check: {len(test_files)} test file(s), "
            f"{len(allowlist)} allowlisted, no new drift."
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
