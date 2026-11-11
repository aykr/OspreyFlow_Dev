"""L1.9 part 1, round 1 (the orchestrator's review of b29dba44): every refusal shown red, planted at
its real call site (`process/CLAUDE.md` rule 15), one plant at a time, the file put back after each
and checked by its hash. Committed with the round, in place of the first round's `/tmp` script.

Run from `OspreyFlow_Core`, with the offline ports (the port guard's own):

    env ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 \
      .venv/bin/python ../OspreyFlow_Build/process/lanes/studio-b/l1.9r1/plant.py [plant …]

With no names, every plant whose tests are offline; `OSPREY_S3_STANDIN` set runs the live ones too.
Each plant's line goes to stdout and to `plants.txt` beside this file: RED (the named tests failed,
with the failing ids) or NOT RED. A plant is a list of swaps in one file, each `old` occurring
exactly once, or that whole file as it was at a commit (`git:<commit>`).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CORE = Path.cwd()
TOP = CORE.parent
OUT = Path(__file__).with_name("plants.txt")
ATHENA = "services/ingest/connectors/athena_connector.py"
S3 = "services/ingest/connectors/s3_connector.py"
READS = "services/api/connector_reads.py"
APP = "services/api/app.py"
SOURCES = "services/api/sources.py"
FIXTURE = "../OspreyFlow_Build/tests/connectors/athena_fixture.py"
T_ATHENA = "../OspreyFlow_Build/tests/connectors/test_athena_connector.py"
T_CLIENTS = "../OspreyFlow_Build/tests/connectors/test_cloud_clients.py"
T_ACCESS = "../OspreyFlow_Build/tests/services/api/test_cloud_connector_access.py"
T_LIVE = "../OspreyFlow_Build/tests/connectors/test_s3_connector_live.py"
OUTSIDE = f"{T_ATHENA}::test_a_named_query_naming_a_table_outside_the_connection_is_never_sent"
UNSURE = f"{T_ATHENA}::test_a_named_query_the_checker_cannot_follow_is_refused"
NOT_ONE = f"{T_ATHENA}::test_a_named_query_that_is_not_one_select_is_never_sent"
S3_HOST = f"{T_CLIENTS}::test_the_s3_store_reaches_the_bucket_s_own_host_virtual_hosted_with_no_key"
ATHENA_HOST = f"{T_CLIENTS}::test_the_athena_client_reaches_athena_s_own_host_with_no_key"
STOPS = f"{T_CLIENTS}::test_a_listing_stops_at_the_object_cap_and_one"
ACCESS = [
    f"{T_ACCESS}::test_another_dataset_s_author_cannot_read_through_it",
    f"{T_ACCESS}::test_another_dataset_s_source_is_refused",
    f"{T_ACCESS}::test_refresh_now_through_a_rebound_connection_reads_nothing",
]
#: The rest of the statement passed over, unchecked: b29dba44's fail-open shape.
SKIP = "while self._peek()[0] != 'end': self.i += 1"
GATE = ('    if list(principal.datasets or []) != [dataset_id]:\n        raise HTTPException('
        'status_code=status.HTTP_404_NOT_FOUND, detail="not_found")')  # fmt: skip
LIST_PAGE = "MaxKeys=min(1_000, limit + 1 - len(found))"
LIST_STOP = 'if len(found) > limit or not page.get("IsTruncated"):'


@dataclass
class Plant:
    file: str
    swaps: list[tuple[str, str]]
    tests: list[str]
    what: str
    live: bool = False


PLANTS: dict[str, Plant] = {
    # --- item 1: the named query's checker, as it was, then each of its branches --------------
    "checker-at-b29dba44": Plant(
        ATHENA, [("", "git:b29dba44")], [OUTSIDE, UNSURE, NOT_ONE],
        "the checker as the review found it, against this round's cases"),
    "comma-unchecked": Plant(
        ATHENA, [('            if not self._punct(","):\n                return\n'
                  '            self.i += 1\n',
                  '            if not self._punct(","):\n                return\n'
                  f"            {SKIP}\n")],
        [OUTSIDE], "a FROM list's comma not followed by a checked relation (the review's shape)"),
    "subquery-relation-returns": Plant(
        ATHENA, [('            if self._word("select", "with", "values", ahead=ahead - 1):\n'
                  '                self.query()\n',
                  '            if self._word("select", "with", "values", ahead=ahead - 1):\n'
                  '                self.query()\n                self._expect_punct(")")\n'
                  f"                {SKIP}\n                return\n")],
        [OUTSIDE], "after a subquery in FROM, the rest passed over (the review's case 1)"),
    "cross-join-swallows": Plant(
        ATHENA, [('                self._expect_word("join")\n                self._relation()\n',
                  '                self._expect_word("join")\n                self._relation()\n'
                  f"                {SKIP}\n")],
        [OUTSIDE], "after a CROSS JOIN, the rest passed over (case 2)"),
    "on-swallows-commas": Plant(
        ATHENA, [("self._expression(commas=False, stops=_RELATION_END)\n            elif",
                  "self._expression(commas=True, stops=_RELATION_END)\n            elif")],
        [OUTSIDE], "a join's ON condition taking the comma after it as its own (case 3)"),
    "unnest-swallows": Plant(
        ATHENA, [('            if self._word("with") and self._word("ordinality", ahead=1):',
                  f'            {SKIP}\n'
                  '            if self._word("with") and self._word("ordinality", ahead=1):')],
        [OUTSIDE], "after UNNEST(…), the rest passed over (case 4)"),
    "sample-swallows": Plant(
        ATHENA, [("                raise _Unsure\n            self._group()\n\n    def _table",
                  "                raise _Unsure\n"
                  "            self._expression(commas=True, stops=frozenset())\n\n    def _table")],
        [OUTSIDE], "TABLESAMPLE's argument scanned together with what follows it (case 5)"),
    "select-end-open": Plant(
        ATHENA, [("            raise _Unsure  # a comma, a word or a relation",
                  "            pass  # a comma, a word or a relation")],
        [UNSURE], "what follows a SELECT's clauses, unaccounted for, passed (failing open); NOT RED "
                  "alone, by design: the statement's own end check refuses the same shapes (the "
                  "next plant removes both)"),
    "fail-closed-off": Plant(
        ATHENA, [("            raise _Unsure  # a comma, a word or a relation",
                  "            pass  # a comma, a word or a relation"),
                 ('        if self._peek()[0] != "end":\n            raise _Unsure\n',
                  '        if self._peek()[0] != "end":\n            pass\n')],
        [UNSURE], "both end checks off: a shape the checker does not follow passed over"),
    "quoted-is-keyword": Plant(
        ATHENA, [('found.append(("quoted", text[1:-1]', 'found.append(("word", text[1:-1]')],
        [OUTSIDE], 'a quoted name read as a keyword (`"where"` as WHERE)'),
    "comments-first": Plant(
        ATHENA, [("    for match in _TOKEN.finditer(statement):",
                  "    for match in _TOKEN.finditer(re.sub(r'--[^\\n]*(\\n|$)|/\\*.*?\\*/', ' ', "
                  "statement, flags=re.DOTALL)):")],
        [OUTSIDE, NOT_ONE], "comments stripped before strings are read (b29dba44's order)"),
    # --- item 3: Athena's result columns --------------------------------------------------------
    "duplicate-columns": Plant(
        ATHENA, [("            _refuse_a_column_named_twice(columns, where)\n", "")],
        [f"{T_ATHENA}::test_a_result_naming_a_column_twice_is_refused_never_one_value_written_in_both"],
        "a result naming a column twice kept, the second value in both cells"),
    "surplus-values": Plant(
        ATHENA, [("            if len(values) != len(columns):", "            if False:"),
                 ("zip(columns, values, strict=True)", "zip(columns, values, strict=False)")],
        [f"{T_ATHENA}::test_a_row_with_more_values_than_columns_is_refused_never_cut"],
        "a row's surplus values dropped silently (b29dba44's zip)"),
    # --- item 7: the fixture, as it was ---------------------------------------------------------
    "fixture-at-b29dba44": Plant(
        FIXTURE, [("", "git:b29dba44")],
        [f"{T_ATHENA}::test_a_catalog_athena_does_not_hold_is_refused_in_words",
         f"{T_ATHENA}::test_a_join_to_a_table_athena_does_not_hold_is_refused_in_words",
         f"{T_ATHENA}::test_an_unqualified_table_is_read_from_the_query_s_own_database"],
        "the fixture as the review found it: catalog ignored, first FROM only, unqualified asserted"),
    # --- items 6 and 8: the clients a deployment builds, and the bounded listing ---------------
    "list-whole": Plant(
        READS, [(LIST_PAGE, "MaxKeys=1_000"), (LIST_STOP, 'if not page.get("IsTruncated"):')],
        [STOPS], "the folder listed whole, then counted (pyarrow's listing, as at b29dba44)"),
    "list-whole-live": Plant(
        READS, [(LIST_PAGE, "MaxKeys=1_000"), (LIST_STOP, 'if not page.get("IsTruncated"):')],
        [f"{T_LIVE}::test_a_real_listing_stops_at_the_object_cap_and_one"],
        "the folder listed whole, against SeaweedFS", live=True),
    "only-to-off": Plant(
        READS, [('    client.meta.events.register_first(f"before-send.{service}", '
                 "_refuse_elsewhere)", "    del _refuse_elsewhere")],
        [f"{T_CLIENTS}::test_a_request_bound_for_another_host_is_never_sent"],
        "a request bound for another host sent"),
    "path-style": Plant(
        READS, [('config=_cloud_config(s3={"addressing_style": "virtual"})',
                 'config=_cloud_config(s3={"addressing_style": "path"})')],
        [S3_HOST], "the listing client addressing the bucket by path, at s3.<region>"),
    "s3-endpoint-from-env": Plant(
        READS, [('"s3", region_name=settings.region, endpoint_url=f"https://{endpoint}",',
                 '"s3", region_name=settings.region,')],
        [S3_HOST], "the listing client's endpoint left to the environment (AWS_ENDPOINT_URL)"),
    "s3-fs-key": Plant(
        READS, [('region=settings.region, scheme="https", access_key=None, secret_key=None,',
                 'region=settings.region, scheme="https", access_key="AKIDPLANTEDKEY", '
                 'secret_key="planted",')],
        [S3_HOST], "pyarrow's filesystem given a key"),
    "s3-fs-path-style": Plant(
        READS, [("        endpoint_override=endpoint, force_virtual_addressing=True,",
                 "        endpoint_override=endpoint, force_virtual_addressing=False,")],
        [S3_HOST], "pyarrow's filesystem addressing the bucket by path"),
    "athena-endpoint-from-env": Plant(
        READS, [('"athena", region_name=settings.region, endpoint_url=f"https://{settings.host()}",',
                 '"athena", region_name=settings.region,')],
        [ATHENA_HOST], "the Athena client's endpoint left to the environment"),
    "athena-key": Plant(
        READS, [('        config=_cloud_config(),\n    )  # fmt: skip\n    return only_to(client, '
                 '"athena"',
                 '        config=_cloud_config(), aws_access_key_id="AKIDPLANTEDKEY", '
                 'aws_secret_access_key="planted",\n    )  # fmt: skip\n    return only_to('
                 'client, "athena"')],
        [ATHENA_HOST], "the Athena client given a key"),
    "region-words": Plant(
        S3, [('    if code in {"PermanentRedirect", "AuthorizationHeaderMalformed", "301"}:',
              "    if False:")],
        [f"{T_CLIENTS}::test_s3_s_refusals_are_refused_in_words_and_never_followed"],
        "a bucket in another region not told so"),
    # --- item 4: the two main access cases, under every guard they pass ------------------------
    "unbound-cloud": Plant(
        READS, [('    if connection.kind != "files" and dataset_id not in connection.datasets:',
                 '    if connection.kind not in {"files", "s3", "athena"} and dataset_id not in '
                 "connection.datasets:")],
        ACCESS, "refuse_unbound skipping s3 and athena (round 1's plant, now on every case)"),
    "route-unbound-removed": Plant(
        APP, [("            refuse_unbound(connection, dataset_id)\n        except ConnectorRefused "
               "as refused:\n            # Answered as an unknown connection is",
               "            pass\n        except ConnectorRefused as refused:\n            # "
               "Answered as an unknown connection is")],
        ACCESS, "the register route's own refuse_unbound (app.py:11526) removed"),
    "store-ignores-dataset": Plant(
        SOURCES, [("        if found is None or found.dataset_id != dataset_id:\n            raise "
                   "SourceNotFoundError(source_id)\n        return found",
                   "        if found is None:\n            raise SourceNotFoundError(source_id)\n"
                   "        return found")],
        ACCESS, "a source found by id alone, not within the route's dataset (the store's WHERE; "
                "the in-memory store stands in for the Postgres one)"),
    "dataset-gate-open": Plant(
        APP, [(GATE, GATE.replace("if list(principal.datasets or []) != [dataset_id]:", "if False:"))],
        ACCESS, "the dataset's own gate (require_studio_dataset) admitting anyone"),
    "dataset-gate-403": Plant(
        APP, [(GATE, GATE.replace("HTTP_404_NOT_FOUND", "HTTP_403_FORBIDDEN"))],
        ACCESS, "the dataset's gate answering 403, telling a dataset that exists apart from one "
                "that does not (item 5)"),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _run(tests: list[str]) -> tuple[list[str], str]:
    found = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p", "no:randomly",
         "-p", "no:cacheprovider", "--tb=no", "-rfE", *tests],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    failed = sorted({line.split(" ", 1)[1].split(" - ", 1)[0].rsplit("::", 1)[-1]
                     for line in found.stdout.splitlines()
                     if line.startswith(("FAILED ", "ERROR "))})  # fmt: skip
    summary = next((line for line in reversed(found.stdout.splitlines()) if " in " in line), "?")
    return failed, summary.strip("= ")


def _planted(p: Plant, path: Path, held: str) -> str | None:
    if p.swaps[0][1].startswith("git:"):
        repo_path = os.path.relpath(path.resolve(), TOP)
        return subprocess.run(["git", "show", f"{p.swaps[0][1][4:]}:{repo_path}"],
                              capture_output=True, text=True, check=True).stdout  # fmt: skip
    planted = held
    for old, new in p.swaps:
        if planted.count(old) != 1:
            return None
        planted = planted.replace(old, new)
    return planted


def plant(name: str) -> tuple[bool, str]:
    p = PLANTS[name]
    path = CORE / p.file
    held = path.read_text()
    planted = _planted(p, path, held)
    if planted is None:
        return False, f"{name}: NOT PLANTED (a swap's text is not in {p.file} exactly once)"
    try:
        path.write_text(planted)
        failed, summary = _run(p.tests)
    finally:
        path.write_text(held)
    assert _sha(path.read_text()) == _sha(held), f"{p.file} was not put back"
    verdict = "RED" if failed else "NOT RED"
    line = f"{name}: {verdict} — {p.what} ({p.file}) — {summary}"
    return bool(failed), line + "".join(f"\n    failed: {f}" for f in failed)


def main(names: list[str]) -> int:
    live = bool(os.environ.get("OSPREY_S3_STANDIN"))
    chosen = names or [n for n, p in PLANTS.items() if live or not p.live]
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()  # fmt: skip
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()  # fmt: skip
    lines = [f"# plants at {head}{' + uncommitted changes' if dirty else ''}"]
    print(lines[0], flush=True)
    every_red = True
    for name in chosen:
        red, line = plant(name)
        every_red &= red
        print(line, flush=True)
        lines.append(line)
    with OUT.open("a") as out:
        out.write("\n".join(lines) + "\n\n")
    return 0 if every_red else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
