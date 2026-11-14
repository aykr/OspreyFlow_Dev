"""The administration guide's §6a on search and the shared volume, held to the `cloud-platform` render
(ADR-148 Amendment 13 decisions 1 and 3; ADR-150). Amendment 13 removed the poc shape's refusal of
OpenSearch, gave the pods that read the stores the domain's address, and left the search index out of the
backup set, rebuilt from the graph at the end of a restore. The guide had said the opposite of each.
Each case reads the render, so the guide's words turn red when the render changes, either way (rule 12):

- which shapes make the OpenSearch domain (`terraform/opensearch.tf`), and that the poc shape refuses
  nothing; and that `postgres-fulltext` makes none;
- which pods are given the domain's address (`OPENSEARCH_URL`);
- the restore's last step: the index rebuilt, then the drift check, by the CronJobs' own names, the index
  not being in a set, each CronJob running a module the tree holds (rules' v0.5.2 index step brings them);
- the shared volume's folders in the standard shape (no staging folder on it).
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
ADMIN = (CORE / "docs" / "administration-guide.md").read_text(encoding="utf-8")
SHAPES = {"poc": "poc", "development": "standard", "production": "standard"}


def section(heading: str) -> str:
    """The section under `heading`, up to the next heading of its level or higher, whitespace folded."""
    level = len(heading) - len(heading.lstrip("#"))
    m = re.search(rf"^{re.escape(heading)}\b.*$", ADMIN, re.MULTILINE)
    assert m, heading
    nxt = re.compile(rf"^#{{1,{level}}} ", re.MULTILINE).search(ADMIN, m.end())
    return re.sub(r"\s+", " ", ADMIN[m.start() : nxt.start() if nxt else len(ADMIN)])


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


def values(fixture: str, search: str | None = None) -> dict[str, Any]:
    artefacts = rendered(fixture, search)
    assert isinstance(artefacts, dict), f"the render refused: {artefacts}"
    found: dict[str, Any] = yaml.safe_load(artefacts["values.yaml"])
    return found


def jobs_of(v: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = (v.get("searchIndex") or {}).get("jobs") or []
    return found


def test_section_6a_says_which_shapes_make_the_opensearch_domain_as_rendered() -> None:
    six_a = section("## 6a")
    refused = rendered("poc", "opensearch")
    if isinstance(refused, str):
        assert refused.split(" (")[0] in six_a, "the poc shape's refusal, in its own words"
    else:
        assert "the poc shape makes no OpenSearch" not in six_a
        assert "makes the platform's OpenSearch domain" in section("### 6a.1")
    made = {f: isinstance(rendered(f, "opensearch"), dict) and "terraform/opensearch.tf" in rendered(f, "opensearch")
            for f in SHAPES}  # fmt: skip
    row = next((line for line in ADMIN.splitlines() if line.startswith("| `opensearch.tf` |")), "")
    assert row, "§6a.3's row for opensearch.tf"
    every = all(made.values())
    assert row.startswith("| `opensearch.tf` | Every shape, when `components.search` is `opensearch`") is every
    assert ("The standard shape alone" in row) is (made == {f: s == "standard" for f, s in SHAPES.items()})


def test_section_6a_says_postgres_fulltext_makes_no_domain() -> None:
    none_made = all("terraform/opensearch.tf" not in values_or_artefacts for values_or_artefacts in
                    (rendered(f, "postgres-fulltext") for f in SHAPES))  # fmt: skip
    assert ("`components.search: postgres-fulltext` makes none" in section("## 6a")) is none_made


def test_section_6a_names_the_pods_given_the_domain_s_address() -> None:
    given = sorted({w["name"] for f in SHAPES for w in values(f, "opensearch")["workloads"]
                    if any(e.get("name") == "OPENSEARCH_URL" for e in w.get("env", []))})  # fmt: skip
    text = section("## 6a")
    m = re.search(r"are given its address \(`OPENSEARCH_URL`\)", text)
    assert ("no pod is given its address" in text) is (not given)
    if given:
        assert m, "§6a's sentence naming the pods given the domain's address"
        sentence = text[max(0, m.start() - 200) : m.start()]
        assert sorted(re.findall(r"\(`([a-z-]+)`\)", sentence)) == given


def test_section_6a8_ends_the_restore_with_the_index_rebuild_then_the_drift_check() -> None:
    poc = values("poc", "opensearch")
    jobs = [j["name"] for j in jobs_of(poc)]
    in_set = any("OPENSEARCH" in e.get("name", "") for e in poc["backups"].get("env") or [])
    text = section("### 6a.8")
    step = re.search(r"\d\. \*\*The search index rebuilt\*\*(.*?)(?= \d\. \*\*|\*\*It refuses)", text)
    assert bool(step) is bool(jobs), "§6a.8's restore step for the search index"
    if step:
        named = re.findall(r"`(ospreyflow-search-[a-z-]+)`", step.group(1))
        assert named == jobs, "the rebuild, then the drift check, by the CronJobs' own names"
        assert ("the index is not in a set" in step.group(1)) is (not in_set)
        # A CronJob the guide tells the operator to start must run a module the image holds: the
        # rebuild and the drift check arrive with rules' v0.5.2 index step, and until then this is red.
        modules = {j["name"]: next(a for a in j["command"] if a.startswith("scripts.")) for j in jobs_of(poc)}
        missing = [m for m in modules.values() if not (CORE / (m.replace(".", "/") + ".py")).is_file()]
        assert missing == [], "the CronJobs' modules, which the guide's step 7 runs"


def test_section_6a1_names_the_standard_shape_s_shared_folders_as_mounted() -> None:
    mounted = {m["subPath"].split("/")[0] for w in values("development")["workloads"]
               for m in w.get("shared") or [] if "claim" not in m}  # fmt: skip
    text = section("### 6a.1")
    m = re.search(r"\*\*The shared folders\*\*(.*?)(?=### |\*\*[A-Z]|$)", text)
    assert m, "§6a.1's paragraph on the shared folders"
    assert ("staging" in m.group(1)) is ("staging" in mounted)
    assert ("in the standard shape, the Ingest root (`ingest`" in m.group(1)) is ("ingest" in mounted)
