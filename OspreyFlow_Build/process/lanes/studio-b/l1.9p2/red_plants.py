"""L1.9 part 2's plants (rules 12 and 15), as L1.10b's: each plant is one exact edit to the code
under test at its real call site; the script applies it, runs the named test files, restores every
file byte for byte and writes `red-p<n>-<slug>.txt`, headed by the commit, the plant and the
command. The items' first reds, taken before the code existed, are `red-1-3-render.txt`,
`red-2-admin-refuses.txt`, `red-4a-s3-region-pyarrow.txt` and `red-4b-athena-parse-and-data.txt`.

Run from OspreyFlow_Core with the closed offline ports pinned (no stack), the shared files' diff
(`cloud-platform-L19p2.diff`) applied:
    .venv/bin/python ../OspreyFlow_Build/process/lanes/studio-b/l1.9p2/red_plants.py
"""

from __future__ import annotations

# ruff: noqa: E501  (each plant is an exact line of the code under test)
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[4] / "OspreyFlow_Core"
READS = CORE / "services/api/connector_reads.py"
HARNESS = CORE / "harness/cloud_platform/__init__.py"
TERRAFORM = CORE / "harness/cloud_platform/terraform.py"
PROFILE = CORE / "harness/cloud_platform/profile.yaml"
FIXTURE = CORE.parent / "OspreyFlow_Build/tests/fixtures/cloud_platform/development-sources.yaml"
RENDER = "../OspreyFlow_Build/tests/harness/test_cloud_sources_render.py"
DECLARED = "../OspreyFlow_Build/tests/services/api/test_cloud_sources_declared.py"
RESULTS_HOST = "synthetic-athena-results.s3.eu-west-2.amazonaws.com"

#: (slug, what, [(file, old, new)], test files, the tests that must go red, the reason or None)
PLANTS = [
    ("read-undeclared", "a read no longer asks whether its source is declared",
     [(READS, "        refuse_undeclared(settings)  # before anything is asked of S3 or Athena\n", "        pass\n")],
     [DECLARED], ["test_a_connection_no_longer_declared_is_refused_at_test_and_at_every_read"], None),
    ("test-undeclared", "Test connection no longer asks whether its source is declared",
     [(READS, "        refuse_undeclared(settings)\n    except ConnectorRefused as refused:\n        return ConnectionTest(ok=False, words=str(refused))\n    found",
       "        pass\n    except ConnectorRefused as refused:\n        return ConnectionTest(ok=False, words=str(refused))\n    found")],
     [DECLARED], ["test_a_connection_no_longer_declared_is_refused_at_test_and_at_every_read"], None),
    ("save-undeclared", "saving a connection no longer asks whether its source is declared",
     [(READS, "    out (`refuse_undeclared`).\"\"\"\n    refuse_undeclared(settings)\n", "    out (`refuse_undeclared`).\"\"\"\n")],
     [DECLARED], ["test_an_undeclared_connection_is_refused_when_it_is_saved",
                  "test_a_connection_wider_than_its_declaration_is_refused"], None),
    ("sibling-folder", "a folder matched without its closing /, so client-ab/ passes as client-a/",
     [(READS, "and settings.prefix.startswith(d.prefix)", "and settings.prefix.startswith(d.prefix.rstrip('/'))")],
     [DECLARED], ["test_a_connection_wider_than_its_declaration_is_refused"], "s3-change4"),
    ("any-database", "one declared database admits the connection's others",
     [(READS, "and set(settings.databases) <= set(d.databases)", "and bool(set(settings.databases) & set(d.databases))")],
     [DECLARED], ["test_a_connection_wider_than_its_declaration_is_refused"], "athena-change7"),
    ("any-catalog", "another catalog admitted, whose Glue entries the role may not read",
     [(READS, "        and settings.catalog == \"AwsDataCatalog\"\n", "")],
     [DECLARED], ["test_a_connection_wider_than_its_declaration_is_refused"], "athena-change8"),
    ("render-unchecked", "the render no longer refuses a wide statement",
     [(TERRAFORM, "    refuse_wide_statements(config, statements)\n", "")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], None),
    ("bucket-wide-star", "a * is held only to being the whole resource, so every bucket passes",
     [(TERRAFORM, "elif any(r == \"*\" or (\"*\" in r and not any(p.match(r) for p in _NARROW_STAR))", "elif any(r == \"*\"")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted1"),
    ("write-on-a-source", "a write is no longer held to the results location",
     [(TERRAFORM, "        elif actions & RESULTS_WRITES and not set(resources) <= results:\n            why = \"writes outside a declared results_location\"\n", "")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted2"),
    ("worker-reaches-connectors", "the worker given connector hosts again, as P7b gave them",
     [(PROFILE, "    connectors: [api]\n", "    connectors: [api, worker]\n")],
     [RENDER], ["test_the_worker_reaches_no_connector_host"], None),
    ("results-bucket-row", "the results location's bucket rendered as the Conduit's egress row",
     [(HARNESS, "for host in _cp(config).connector_sources.hosts()],", f"for host in [*_cp(config).connector_sources.hosts(), {RESULTS_HOST!r}]],"),
      (FIXTURE, "    athena.eu-west-2.amazonaws.com: [\"198.18.3.0/24\"]\n", f"    athena.eu-west-2.amazonaws.com: [\"198.18.3.0/24\"]\n    {RESULTS_HOST}: [\"198.18.0.0/24\"]\n")],
     [RENDER], ["test_no_results_or_table_location_is_an_egress_host"], None),
]


def run(files: list[str]) -> str:
    try:
        done = subprocess.run(
            [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
             "-q", "-rA", *files],
            cwd=CORE, capture_output=True, text=True, timeout=600,
            env={**os.environ, "COLUMNS": "400"},
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        return "FAILED (the run hung past 600 s and was stopped)\n0 passed, hung"
    keep = ("PASSED", "FAILED", "ERROR ")
    lines = [line for line in done.stdout.splitlines() if line.startswith(keep)]
    return "\n".join(lines + [done.stdout.strip().splitlines()[-1]])


def main() -> int:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=CORE, capture_output=True, text=True
    ).stdout.strip()
    only = set(sys.argv[1:])
    plants = [(n, p) for n, p in enumerate(PLANTS, start=1) if not only or p[0] in only]
    originals = {path: path.read_bytes() for _, p in plants for path, _, _ in p[2]}
    missed: list[tuple[str, str]] = []
    for n, (slug, what, edits, files, must_fail, reason) in plants:
        texts = {path: data.decode() for path, data in originals.items()}
        for path, old, new in edits:
            assert texts[path].count(old) == 1, (slug, path.name, old)
            texts[path] = texts[path].replace(old, new)
        try:
            for path, text in texts.items():
                if text != originals[path].decode():
                    path.write_text(text)
            out = run(files)
        finally:
            for path, data in originals.items():
                path.write_bytes(data)
        failed = [line for line in out.splitlines() if line.startswith("FAILED")]
        absent = []
        for test in must_fail:
            mine = [line for line in failed if f"::{test} " in line or f"::{test}[" in line
                    or line.endswith(f"::{test}")]
            if not mine:
                absent.append(test)
            elif reason and not any(reason in line for line in mine):
                absent.append(f"{test}: the reason {reason!r}")
        missed += [(slug, a) for a in absent]
        (HERE / f"red-p{n}-{slug}.txt").write_text(
            f"# head {head}; plant: {what}\n# command: pytest -q -rA {' '.join(files)}\n"
            f"# must fail: {', '.join(must_fail)}"
            f"{'; for the reason ' + repr(reason) if reason else ''}"
            f"; all failed: {'yes' if not absent else absent}\n{out}\n"
        )
    for path, data in originals.items():
        assert path.read_bytes() == data, path
    if not only:
        (HERE / "green.txt").write_text(f"# head {head}; no plant\n{run([RENDER, DECLARED])}\n")
    print("missed:", missed or "none")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
