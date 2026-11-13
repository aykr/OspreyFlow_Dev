"""The guides against the `cloud-platform` profile as built: the ADR-148 audit of 13 November 2026
(`process/lanes/AUDIT_ADR148_2026-11-13.md`) and the rulings list (`RULINGS_SINCE_1NOV.md`) found the guides saying
things the profile does not do, or leaving out what it refuses. The docs lane's v0.5.2 sweep, part one
(`process/lanes/docs/v052-sweep/README.md`), corrected them. Each case below holds a correction to the code it
describes, so the words cannot drift from it unnoticed (rule 12):

- on Entra ID nothing can act as its owner: every guide section describing something that runs as its owner (a
  pipeline's schedule and watched folder, `ospreyflow run`, *Run now* in Operations, a rule's schedule, a list's
  refresh schedule, a watch, another analyst's hotlist at a load) says so, pointing at §6a.7, and §6a.7 quotes the
  refusal in the scheduler's own words; no guide says such a run is "marked stopped", which it is not;
- *Admin › People* on Entra ID refuses what Entra holds, and §9 quotes each refusal as `entra_people.py` words it;
- the point-in-time restore's days, and one S3 read's object cap, are the code's numbers.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
DOCS = CORE / "docs"
ADMIN = (DOCS / "administration-guide.md").read_text(encoding="utf-8")
DEVELOPER = (DOCS / "developer-guide.md").read_text(encoding="utf-8")
USER = (DOCS / "user-guide.md").read_text(encoding="utf-8")
GUIDES = {"administration": ADMIN, "developer": DEVELOPER, "user": USER,
          "architecture": (DOCS / "architecture-guide.md").read_text(encoding="utf-8")}  # fmt: skip


def section(text: str, heading: str) -> str:
    """The section under `heading` (a line starting with it), up to the next heading of its level or higher."""
    level = len(heading) - len(heading.lstrip("#"))
    m = re.search(rf"^{re.escape(heading)}\b.*$", text, re.MULTILINE)
    assert m, f"no heading {heading!r}"
    end = re.search(rf"^#{{1,{level}}} ", text[m.end() :], re.MULTILINE)
    return text[m.start() : m.end() + end.start()] if end else text[m.start() :]


def _literals(path: Path, call: str) -> list[str]:
    """Every string literal passed as the first argument of `call(...)` in a module, joined as Python joins them."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == call:
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                found.append(node.args[0].value)
    return found


# ---------------------------------------------------------------- nothing acts as its owner on Entra ID

#: Each guide section describing something that runs as its owner, and so stops on Entra ID.
OWNER_RUNS = [
    ("administration", "### 9.5"),   # a screening list's refresh schedule
    ("administration", "### 9.11"),  # Operations' Run now, as the schedule's owner
    ("developer", "### 6.3"),        # a pipeline's schedule and watched folder
    ("user", "### 7.5"),             # watches, and another analyst's hotlist at a load
    ("user", "### 7.11"),            # a rule's schedule
]  # fmt: skip


def owner_runs_without_the_entra_note(guides: dict[str, str]) -> list[str]:
    found = [f"{g} {h}" for g, h in OWNER_RUNS if "6a.7" not in section(guides[g], h)]
    run_row = next((line for line in guides["administration"].splitlines() if line.startswith("| `ospreyflow run ")), "")
    if "6a.7" not in run_row:
        found.append("administration: the `ospreyflow run` row")
    return found


def test_every_owner_run_says_it_stops_on_entra() -> None:
    assert owner_runs_without_the_entra_note(GUIDES) == []


def test_the_owner_run_check_flags_a_section_without_its_note() -> None:
    planted = dict(GUIDES, developer=GUIDES["developer"].replace("6a.7", "6a.8"))
    assert owner_runs_without_the_entra_note(planted) == ["developer ### 6.3"]


#: The scheduler's own refusal, for a pipeline's run, when its owner cannot be resolved.
SCHEDULER_WORDS = next(w for w in _literals(CORE / "services/api/scheduler.py", "_Refused")
                       if "could not be reached to act as the schedule" in w)  # fmt: skip


def test_section_6a7_quotes_the_scheduled_runs_refusal_as_the_scheduler_words_it() -> None:
    assert SCHEDULER_WORDS in re.sub(r"\s+", " ", section(ADMIN, "### 6a.7"))


def test_entra_owner_resolution_is_refused_in_the_code_the_guide_describes() -> None:
    """The fact §6a.7 rests on: the resolver refuses every owner on an Entra mapping."""
    source = (CORE / "packages/principal_auth/__init__.py").read_text(encoding="utf-8")
    assert "owner resolution is unavailable with Entra ID sign-in" in source


def test_no_guide_says_an_entra_scheduled_run_is_marked_stopped() -> None:
    """It is refused at every slot, and the refusals never pause it (`scheduler.py`: `about_the_owner=False`)."""
    found = [g for g, text in GUIDES.items() if re.search(r"such a run is marked\s+stopped", text)]
    assert found == []


# ---------------------------------------------------------------- Admin › People on Entra ID


def entra_refusals() -> list[str]:
    path = CORE / "services/api/entra_people.py"
    words = _literals(path, "_refused")
    assert len(words) >= 4, "entra_people.py's refusals were not found where this test reads them"
    return words


def test_section_9_quotes_each_entra_people_refusal() -> None:
    people = section(ADMIN, "## 9. People")
    assert [w for w in entra_refusals() if w not in re.sub(r"\s+", " ", people)] == []


def test_the_people_check_flags_a_refusal_left_out() -> None:
    first = entra_refusals()[0]
    people = re.sub(r"\s+", " ", section(ADMIN, "## 9. People")).replace(first, "")
    assert first not in people


# ---------------------------------------------------------------- the code's numbers


def _rendered(setting: str, file: str) -> str:
    """`setting`'s value in the rendered Terraform's `file`, the one value every fixture renders: read from what
    the `cloud-platform` profile renders, never from a literal in the renderer's source (an argument built from a
    constant, as `str(EXPIRE_DAYS)` is, has no literal to read)."""
    import yaml
    from harness.render import render
    from tools.cp_policy_check import FIXTURES, _resolver

    from schemas.deployment import OspreyConfig

    values: set[str] = set()
    for fixture in sorted(FIXTURES.glob("*.yaml")):
        config = OspreyConfig.model_validate(yaml.safe_load(fixture.read_text(encoding="utf-8")))
        text = render(config, resolver=_resolver).artefacts[f"terraform/{file}"]
        values |= set(re.findall(rf"^\s*{setting}\s*=\s*(\d+)\s*$", text, re.MULTILINE))
    assert len(values) == 1, f"{setting} in {file}: rendered as {sorted(values) or 'nothing'}"
    return values.pop()


def test_section_6a8_gives_rds_point_in_time_restore_its_rendered_days() -> None:
    days = _rendered("backup_retention_period", "rds.tf")
    text = re.sub(r"\s+", " ", section(ADMIN, "### 6a.8"))
    assert f"point-in-time restore for {days} days" in text
    sets = _rendered("days", "backups.tf")  # the sets' own expiry, the bucket's lifecycle rule
    assert f"against the sets' {sets}:" in text
    # A set outliving RDS's window cannot be restored with its database, and §6a.8 must say which; one that does not
    # outlive it can, and §6a.8 must not warn of a window that does not exist (in any of the old warning's words).
    caveat = f"only a set finished in the last {days} days"
    if int(days) < int(sets):
        assert caveat in text
    else:
        stale = ["only a set finished in the last", "no database to pair with it", "is not to be restored"]
        assert [words for words in stale if words in text] == []


def test_section_6a5_gives_one_s3_reads_cap_as_the_connector_holds_it() -> None:
    m = re.search(r"^MAX_OBJECTS = ([\d_]+)$", (CORE / "services/ingest/connectors/s3_connector.py").read_text(), re.M)
    assert m
    cap = f"{int(m.group(1).replace('_', '')):,}"
    assert f"more than {cap} objects" in re.sub(r"\s+", " ", section(ADMIN, "### 6a.5"))


# ---------------------------------------------------------------- what a backup set holds (§6a.8)


def test_section_6a8_names_what_the_set_holds_as_the_render_backs_it_up() -> None:
    """ADR-148 Amendment 13 decision 4: the shared claim's folders the deployment cannot make again join
    the set's claims part, in every shape. §6a.8 names each folder the render backs up, says the claims run
    is in every shape when it is, and never says the shared volume is not backed up while a part of it is."""
    from tests.harness.test_cloud_platform_render import _config, _values

    shapes = ["poc", "development", "production"]
    shared = {s: [p["subPath"] for p in _values(_config(s))["backups"].get("shared") or []] for s in shapes}
    text = re.sub(r"\s+", " ", section(ADMIN, "### 6a.8"))
    folders = sorted({folder for parts in shared.values() for folder in parts})
    assert [f for f in folders if f"(`{f}`" not in text] == []
    # ...and names no folder the render does not back up (one dropped from the set, still named here).
    holds = re.search(r"The claims part holds(.*?)The pods that mount them", text)
    named = re.findall(r"\(`([^`]+)`", holds.group(1)) if holds else []
    assert [f for f in named if f not in folders] == []
    if all(shared.values()):
        assert "`ospreyflow-backup-claims` (the claims part, in every shape" in text
        assert "in the poc shape, `ospreyflow-backup-claims`" not in text
    if folders:
        assert not re.search(r"`ospreyflow-shared`[^.]{0,40}is not backed up", text)
