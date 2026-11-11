"""L1.9 part 2's plants (rules 12 and 15), as L1.10b's: each plant is one exact edit to the code
under test at its real call site; the script applies it, runs the named test files, restores every
file byte for byte and writes `red-p<n>-<slug>.txt`, headed by the commit, the plant and the
command. The items' first reds, taken before the code existed, are `red-1-3-render.txt`,
`red-2-admin-refuses.txt`, `red-4a-s3-region-pyarrow.txt` and `red-4b-athena-parse-and-data.txt`.

Rebuilt after the lane review (round 1) with its new plants, at the commit holding the fixes; the
shared files' two diffs (`cloud-platform-L19p2.diff`, `docs-admin-guide-L19p2.diff`, regenerated at
that commit) applied in the worktree, as they are at merge. Run from OspreyFlow_Core with the
closed offline ports pinned (no stack):
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
ATHENA = CORE / "services/ingest/connectors/athena_connector.py"
ATHENA_TESTS = "../OspreyFlow_Build/tests/connectors/test_athena_connector.py"
GUIDE_TOOL = CORE.parent / "OspreyFlow_Build/tools/admin_guide_options.py"
GUIDE_TESTS = "../OspreyFlow_Build/tests/test_admin_guide.py"

#: (slug, what, [(file, old, new)], test files, the tests that must go red, the reason or None)
PLANTS = [
    ("read-undeclared", "a read no longer asks whether its source is declared",
     [(READS, "    refuse_undeclared(settings)\n    if isinstance(settings, SqlConnectionSettings) and isinstance(read, SqlRead):",
       "    if isinstance(settings, SqlConnectionSettings) and isinstance(read, SqlRead):")],
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
    ("unreadable-escapes", "an unreadable declaration escapes as pydantic's error (a 500, no words)",
     [(READS, "    except ValueError as unreadable:  # pydantic's ValidationError is one", "    except KeyError as unreadable:")],
     [DECLARED], ["test_an_unreadable_declaration_refuses_in_words_never_a_500"], None),
    ("api-to-source-host", "an API connection to a declared source's host passes",
     [(READS, "        if made is not None and bare in made.hosts():", "        if False:")],
     [DECLARED], ["test_an_api_connection_to_a_declared_source_s_host_is_refused"], None),
    ("render-unchecked", "the render no longer refuses a wide statement",
     [(TERRAFORM, "    refuse_wide_statements(config, statements)\n", "")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], None),
    ("star-anywhere", "a * is held only to being the whole resource",
     [(TERRAFORM, "    if any(\"?\" in r or r == \"*\" or (\"*\" in r and not any(p.match(r) for p in _NARROW_STAR))", "    if any(\"?\" in r or r == \"*\"")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted1"),
    ("question-mark", "IAM's other wildcard, ?, admitted",
     [(TERRAFORM, "    if any(\"?\" in r or r == \"*\"", "    if any(r == \"*\"")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted2"),
    ("write-on-a-source", "a write is no longer held to the results location",
     [(TERRAFORM, "    if actions & RESULTS_WRITES and not set(resources) <= results:\n        return \"writes outside a declared results_location\"\n", "")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted3"),
    ("any-action", "an action outside the read set admitted",
     [(TERRAFORM, "    if actions - SOURCE_READS - RESULTS_WRITES:\n        return", "    if False:\n        return")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted4"),
    ("undeclared-bucket", "a bucket the declaration does not name admitted",
     [(TERRAFORM, "            if bucket not in declared:\n                return f\"names the bucket {bucket}, which is not declared\"\n", "")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted5"),
    ("outside-folder", "a declared bucket read outside its declared folders",
     [(TERRAFORM, "            if key and not any(key.startswith(f) for f in declared.get(bucket, set())):\n                return", "            if False:\n                return")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted6"),
    ("unconditioned-listing", "a bucket listed with no s3:prefix condition admitted",
     [(TERRAFORM, "            if condition.get(\"variable\") != \"s3:prefix\" or not condition.get(\"values\"):", "            if False:")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted7"),
    ("undeclared-database", "a database the declaration does not name admitted",
     [(TERRAFORM, "            if database.split(\"/\")[0] not in _declared_databases(config):", "            if False:")],
     [RENDER], ["test_a_wide_statement_is_refused_by_the_render"], "planted8"),
    ("location-under-condition", "the bucket's location asked under the listing's s3:prefix condition, as built at 95b4148",
     [(TERRAFORM, "        \"sid\": sid, \"actions\": [\"s3:ListBucket\"], \"resources\": [f\"arn:aws:s3:::{bucket}\"]",
       "        \"sid\": sid, \"actions\": [\"s3:ListBucket\", \"s3:GetBucketLocation\"], \"resources\": [f\"arn:aws:s3:::{bucket}\"]")],
     [RENDER], ["test_a_listing_condition_never_holds_an_action_that_carries_no_prefix"], None),
    ("worker-reaches-connectors", "the worker given connector hosts again, as P7b gave them",
     [(PROFILE, "    connectors: [api]\n", "    connectors: [api, worker]\n")],
     [RENDER], ["test_the_worker_reaches_no_connector_host"], None),
    ("results-bucket-row", "the results location's bucket rendered as the Conduit's egress row",
     [(HARNESS, "for host in _cp(config).connector_sources.hosts()],", f"for host in [*_cp(config).connector_sources.hosts(), {RESULTS_HOST!r}]],"),
      (FIXTURE, "    athena.eu-west-2.amazonaws.com: [\"198.18.3.0/24\"]\n", f"    athena.eu-west-2.amazonaws.com: [\"198.18.3.0/24\"]\n    {RESULTS_HOST}: [\"198.18.0.0/24\"]\n")],
     [RENDER], ["test_no_results_or_table_location_is_an_egress_host"], None),
    ("table-data-unworded", "Athena's refusal of a table location not declared left in Athena's own words",
     [(ATHENA, "            if _DATA_DENIED.match(reason):", "            if False:")],
     [RENDER, ATHENA_TESTS], ["test_a_table_location_not_declared_is_athena_s_refusal_in_typed_words",
                              "test_a_table_whose_data_the_role_may_not_read_is_refused_in_typed_words"], None),
    ("results-blamed-on-tables", "an S3 denial on the results location worded as the tables'",
     [(ATHENA, "_DATA_DENIED = re.compile(r\"^Permission denied on S3 path: \")", "_DATA_DENIED = re.compile(r\"^(Permission denied on S3 path: |Access denied when writing)\")")],
     [ATHENA_TESTS], ["test_a_results_location_refusal_is_never_blamed_on_the_table_locations"], None),
    ("guide-annotated", "the guide's type of a constrained list item printed as pydantic's internals",
     [(GUIDE_TOOL, "    if origin is typing.Annotated:\n        return _type_name(arguments[0])  # its constraints are the schema's, not the reader's\n", "")],
     [GUIDE_TESTS], ["test_a_constrained_list_item_is_named_by_its_type_never_by_pydantic_s_internals"], None),
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
