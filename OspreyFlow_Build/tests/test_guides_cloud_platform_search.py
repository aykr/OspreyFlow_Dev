"""The administration guide's §6a on search and the shared volume, held to the `cloud-platform` render
(ADR-148 Amendment 13 decisions 1 to 3; ADR-150). Amendment 13 removed the poc shape's refusal of
OpenSearch, gave the pods that read the stores the domain's address, and left the search index out of the
backup set, rebuilt from the graph at the end of a restore. The guide had said the opposite of each.
Each case reads the render, so the guide's words turn red when the render changes, either way (rule 12):

- which shapes make the OpenSearch domain (`terraform/opensearch.tf`), and that the poc shape refuses
  nothing; and that `postgres-fulltext` makes none;
- which pods are given the domain's address (`OPENSEARCH_URL`): the workloads and the index's Jobs;
- the restore's last steps: the backups' CronJobs resumed (never the index's), then the index rebuilt and
  the drift check, by the CronJobs' own names, the index not being in a set, each CronJob running a module
  the tree holds (rules' v0.5.2 index step brings them);
- the shared volume's folders in the standard shape (no staging folder on it), anywhere in §6a.
"""

from __future__ import annotations

import json
import re
from functools import cache
from typing import Any

import yaml

from tests.test_guides_cloud_platform import ADMIN, CORE
from tests.test_guides_cloud_platform import section as _section

SHAPES = {"poc": "poc", "development": "standard", "production": "standard"}


def section(heading: str) -> str:
    return re.sub(r"\s+", " ", _section(ADMIN, heading))


@cache
def rendered(fixture: str, search: str | None) -> dict[str, str] | str:
    """The fixture's artefacts with `components.search` set (None: as the fixture has it), or the
    render's refusal in its own words."""
    from harness.render import render
    from tools.cp_policy_check import FIXTURES, _resolver

    from schemas.deployment import OspreyConfig

    raw = yaml.safe_load((FIXTURES / f"{fixture}.yaml").read_text(encoding="utf-8"))
    if search:
        raw.setdefault("components", {})["search"] = search
    try:
        return dict(render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts)
    except Exception as refusal:  # noqa: BLE001 - the refusal's words are what the guide must quote
        return str(refusal)


def artefacts(fixture: str, search: str | None = None) -> dict[str, str]:
    found = rendered(fixture, search)
    assert isinstance(found, dict), f"the render refused: {found}"
    return found


def values(fixture: str, search: str | None = None) -> dict[str, Any]:
    found: dict[str, Any] = yaml.safe_load(artefacts(fixture, search)["values.yaml"])
    return found


def jobs_of(v: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = (v.get("searchIndex") or {}).get("jobs") or []
    return found


def _has_address(env: list[dict[str, Any]] | None) -> bool:
    return any(e.get("name") == "OPENSEARCH_URL" for e in env or [])


def test_section_6a_says_which_shapes_make_the_opensearch_domain_as_rendered() -> None:
    six_a = section("## 6a")
    refused = rendered("poc", "opensearch")
    if isinstance(refused, str):
        assert refused.split(" (")[0] in six_a, "the poc shape's refusal, in its own words"
    else:
        assert "the poc shape makes no opensearch" not in six_a.lower()
        assert "makes the platform's OpenSearch domain" in section("### 6a.1")
    made = {f: "terraform/opensearch.tf" in artefacts(f, "opensearch") for f in SHAPES}
    row = next((line for line in ADMIN.splitlines() if line.startswith("| `opensearch.tf` |")), "")
    assert row, "§6a.3's row for opensearch.tf"
    every = all(made.values())
    assert row.startswith("| `opensearch.tf` | Every shape, when `components.search` is `opensearch`") is every
    assert ("The standard shape alone" in row) is (made == {f: s == "standard" for f, s in SHAPES.items()})
    assert ("In every shape the platform's OpenSearch 2.x domain is made by default" in six_a) is every


def test_section_6a_says_postgres_fulltext_makes_no_domain() -> None:
    none_made = all("terraform/opensearch.tf" not in artefacts(f, "postgres-fulltext") for f in SHAPES)
    assert ("`components.search: postgres-fulltext` makes none" in section("## 6a")) is none_made


def test_section_6a_names_the_pods_given_the_domain_s_address() -> None:
    given: set[str] = set()
    for f in SHAPES:
        v = values(f, "opensearch")
        given |= {w["name"] for w in v["workloads"] if _has_address(w.get("env"))}
        given |= {j["name"] for j in v.get("jobs") or [] if _has_address(j.get("env"))}
        if _has_address((v.get("searchIndex") or {}).get("env")):
            given |= {j["name"] for j in jobs_of(v)}
    text = section("## 6a")
    assert ("no pod is given its address" in text) is (not given)
    m = re.search(r"the pods that read the stores, (.*?), are given its address \(`OPENSEARCH_URL`\)", text)
    assert bool(m) is bool(given), "§6a's sentence naming the pods given the domain's address"
    if m:
        assert sorted(set(re.findall(r"`([a-z-]+)`", m.group(1)))) == sorted(given)


def test_section_6a8_ends_the_restore_with_the_index_rebuild_then_the_drift_check() -> None:
    poc = values("poc", "opensearch")
    jobs = [j["name"] for j in jobs_of(poc)]
    # The set's parts as the render names them: a search index in the set would be one of them.
    in_set = "search" in json.dumps(poc["backups"].get("shared") or []) + json.dumps(poc.get("storage") or {})
    text = section("### 6a.8")
    step = re.search(r"\d\. \*\*The search index rebuilt\*\*(.*?)(?= \d\. \*\*|\*\*It refuses)", text)
    assert bool(step) is bool(jobs), "§6a.8's restore step for the search index"
    resumed = re.search(r"6\. \*\*Everything started again\*\*(.*?)(?= 7\. \*\*)", text)
    assert resumed, "§6a.8's step 6"
    assert re.findall(r"`(ospreyflow-[a-z-]+)`", resumed.group(1)) == ["ospreyflow-backup", "ospreyflow-backup-claims"]
    if step:
        named = re.findall(r"`(ospreyflow-search-[a-z-]+)`", step.group(1))
        assert named == jobs, "the rebuild, then the drift check, by the CronJobs' own names"
        assert ("the index is not in a set" in step.group(1)) is (not in_set)
        # A CronJob the guide tells the operator to start must run a module the image holds: the
        # rebuild and the drift check arrive with rules' v0.5.2 index step, and until then this is red.
        modules = [next((a for a in j["command"] if a.startswith("scripts.")), j["name"]) for j in jobs_of(poc)]
        missing = [m for m in modules
                   if not (CORE / (m.replace(".", "/") + ".py")).is_file()
                   and not (CORE / m.replace(".", "/") / "__main__.py").is_file()]  # fmt: skip
        assert missing == [], "the CronJobs' modules, which the guide's step 7 runs"


def test_section_6a_names_the_standard_shape_s_shared_folders_as_mounted() -> None:
    mounted = {m["subPath"].split("/")[0] for w in values("development")["workloads"]
               for m in w.get("shared") or [] if "claim" not in m}  # fmt: skip
    m = re.search(r"\*\*The shared folders\*\*(.*?)(?=### |\*\*[A-Z]|$)", section("### 6a.1"))
    assert m, "§6a.1's paragraph on the shared folders"
    assert ("in the standard shape, the Ingest root (`ingest`" in m.group(1)) is ("ingest" in mounted)
    # Staging is the platform's bucket: no sentence in §6a puts it on the shared volume.
    if "staging" not in mounted:
        assert re.findall(r"[^.]*shared[^.]*\bstaging\b[^.]*\.", section("## 6a")) == []


# ---------------------------------------------------------------- the index's Jobs: their size and way out

JOBS_ROW = "| The search index's rebuild and drift check, when OpenSearch is used |"


def _row(text: str) -> list[str]:
    line = next((ln for ln in text.splitlines() if ln.startswith(JOBS_ROW)), "")
    return [cell.strip() for cell in line.strip("|").split("|")][1:] if line else []


def _cpu(value: str) -> str:
    return f"{int(value[:-1]) / 1000:g}" if value.endswith("m") else f"{float(value):g}"


def _mem(value: str) -> str:
    return value.replace("Gi", " GiB").replace("Mi", " MiB")


def test_section_6a2_sizes_the_index_jobs_as_rendered() -> None:
    """Each shape's `searchIndex.resources`, the Conduit's own size; the poc shape's CPU limit too."""
    six_a2 = section("### 6a.2")
    rows = _row(_section(ADMIN, "### 6a.2"))
    assert bool(rows) is any(jobs_of(values(f, "opensearch")) for f in SHAPES), "§6a.2's row for the index's Jobs"
    assert not any(jobs_of(values(f, "postgres-fulltext")) for f in SHAPES), "the row's 'when OpenSearch is used'"
    for f in SHAPES:
        size = values(f, "opensearch")["searchIndex"]["resources"]
        assert rows == ["—", "—", _cpu(size["requests"]["cpu"]), _mem(size["requests"]["memory"]),
                        _mem(size["limits"]["memory"])], f  # fmt: skip
    poc_limit = values("poc", "opensearch")["searchIndex"]["resources"]["limits"].get("cpu")
    assert (f"the search index's rebuild and drift check {_cpu(poc_limit)})" in six_a2) is bool(poc_limit)


#: The guide's words for what the index's Jobs reach, each against the render's egress row.
REACH = {
    "ArcadeDB": lambda r: "arcadedb" in {p["name"] for p in r.get("toPods") or []},
    "ClickHouse": lambda r: "clickhouse" in {p["name"] for p in r.get("toPods") or []},
    "the managed stores' networks": lambda r: bool(r.get("managed")),
    "S3 and STS": lambda r: {h.split(".")[0] for h in r.get("hosts") or []} >= {"s3", "sts"},
}


def test_section_6a5_gives_the_index_jobs_the_way_out_the_render_gives_them() -> None:
    cells = _row(_section(ADMIN, "### 6a.5"))
    assert cells, "§6a.5's row for the index's Jobs"
    for f in SHAPES:
        v = values(f, "opensearch")
        egress = {r["name"]: r for r in v["egress"]["workloads"]}
        for job in jobs_of(v):
            r = egress[job["label"]]
            assert {w for w, holds in REACH.items() if holds(r)} == {w for w in REACH if w in cells[0]}, (f, job)
            assert set(r) <= {"name", "toPods", "managed", "hosts"}, f"a way out the row does not name: {r}"
        assert ("(OpenSearch on 443)" in cells[0]) is (443 in v["egress"]["managedPorts"])


# ---------------------------------------------------------------- §13: a local restore rebuilds the index


def test_section_13_says_a_local_restore_rebuilds_the_index_last_where_there_is_one(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import inspect

    from harness import restore
    from harness.render import render as render_local

    from schemas.deployment import SearchBackend
    from tests.harness.test_search_index_render_and_restore import _config
    from tests.harness.test_render import _fake_resolver

    def rebuilds(search: SearchBackend) -> bool:
        compose = tmp_path / f"{search.value}.yaml"
        compose.write_text(render_local(_config(tmp_path, search), resolver=_fake_resolver).artefacts["compose.yaml"])
        ran: list[list[str]] = []
        monkeypatch.setattr(restore, "_run", lambda command, **_: ran.append(command) or "")
        restore.rebuild_search_index(compose)
        return any("scripts.rebuild_search_index" in c for c in ran)

    text = re.sub(r"\s+", " ", _section(ADMIN, "## 13"))
    assert "holds no index of OspreyFlow's yet" not in text
    said = "runs `python -m scripts.rebuild_search_index` in the Conduit's container"
    assert (said in text) is rebuilds(SearchBackend.OPENSEARCH)
    assert ("With `postgres-fulltext` there is no index to rebuild." in text) is (not rebuilds(SearchBackend.POSTGRES_FULLTEXT))
    last = inspect.getsource(restore.run_restore).rstrip().splitlines()[-2].strip()
    assert ("a restore's last step" in text) is (last == "rebuild_search_index(compose_file)")
