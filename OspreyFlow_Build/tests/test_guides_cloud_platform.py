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
- the point-in-time restore's days, and one S3 read's object cap, are the code's numbers;
- §6a.8 says what a backup set holds, and what it leaves out, in each shape as the render backs it up.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

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


# ---------------------------------------------------------------- a run as its owner on Entra ID (ADR-148 Am 16)

#: Each guide section describing something that runs as its owner, and so points to §6a.7's rule on Entra ID.
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


def test_every_owner_run_points_to_the_entra_rule() -> None:
    assert owner_runs_without_the_entra_note(GUIDES) == []


#: What the guides said while nothing acted as its owner on Entra ID (docs' v0.5.2 sweep, part one), and
#: no longer may: since ADR-148 Amendment 16 a run acts as its owner's stored identity (D1, inverted).
STOPS_ON_ENTRA = [
    "nothing acts as its owner", "nothing can act as", "nobody can be acted as", "loads are started by hand",
    "cannot act as you while you are away", "a watch's own runs do not happen", "as every scheduled run is",
    "owner resolution is unavailable",
]  # fmt: skip


def owner_runs_said_to_stop(guides: dict[str, str]) -> list[str]:
    """The guides' own text, their history rows left out: a row records what a version said."""
    def body(text: str) -> str:
        kept = [line for line in text.splitlines() if not re.match(r"\| \d+\.\d+ \| \d{4}-\d{2}-\d{2} \|", line)]
        return re.sub(r"\s+", " ", "\n".join(kept)).lower()

    return [f"{g}: {words}" for g, text in guides.items() for words in STOPS_ON_ENTRA if words in body(text)]


def test_no_guide_says_an_owner_run_stops_on_entra() -> None:
    assert owner_runs_said_to_stop(GUIDES) == []


def test_the_stop_check_flags_the_old_words_put_back() -> None:
    planted = dict(GUIDES, user=GUIDES["user"] + "\nOn Entra ID nothing can act as you, so loads are started by\nhand.\n")
    assert owner_runs_said_to_stop(planted) == ["user: nothing can act as", "user: loads are started by hand"]


def test_the_owner_run_check_flags_a_section_without_its_note() -> None:
    planted = dict(GUIDES, developer=GUIDES["developer"].replace("6a.7", "6a.8"))
    assert owner_runs_without_the_entra_note(planted) == ["developer ### 6.3"]


def test_section_6a7_quotes_the_24_hour_refusal_as_the_code_words_it() -> None:
    """The words every run as its owner says when its owner's access is out of date (`ACCESS_OUT_OF_DATE_WORDS`),
    after the scheduler's "the schedule's owner, <id>,"."""
    from principal_auth import ACCESS_OUT_OF_DATE_WORDS

    text = re.sub(r"\s+", " ", section(ADMIN, "### 6a.7"))
    assert f"the schedule's owner, <id>, {ACCESS_OUT_OF_DATE_WORDS}" in text


def test_section_6a7_gives_the_hours_the_code_trusts_a_sign_in_for() -> None:
    from principal_auth import ACCESS_FRESH

    hours = int(ACCESS_FRESH.total_seconds() // 3600)
    text = re.sub(r"\s+", " ", section(ADMIN, "### 6a.7"))
    assert f"has not signed in within the last {hours} hours" in text
    assert "So a schedule runs only on the days its owner signs in." in text


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
    the set's claims part. §6a.8 names, as the render has it in each shape, the folders in the set, the
    shape whose Ingest root is a claim of its own, the claims run's shapes, and the shared volume's
    folders left out of every set; each sentence held both ways, so the render changing either side
    of it is red."""
    from tests.harness.test_cloud_platform_render import _config, _values

    standard = ["development", "production"]
    values = {s: _values(_config(s)) for s in ["poc", *standard]}
    parts = {s: [p["subPath"] for p in v["backups"].get("shared") or []] for s, v in values.items()}
    claims = {s: [c["name"] for c in (v.get("storage") or {}).get("claims") or []] for s, v in values.items()}

    def mounted(v: dict[str, Any]) -> set[str]:
        return {m["subPath"] for w in v["workloads"] for m in w.get("shared") or [] if "claim" not in m}

    def left_out(s: str) -> set[str]:
        """The shared volume's top folders no part of the set lies in or under (`data` holds a part)."""
        tops = {sub.split("/")[0] for sub in mounted(values[s])}
        return {t for t in tops if not any(p == t or p.startswith(t + "/") for p in parts[s])}

    text = re.sub(r"\s+", " ", section(ADMIN, "### 6a.8"))
    folders = sorted({f for found in parts.values() for f in found})

    holds = re.search(r"cannot make again\*\*: (.*?); and, in the poc shape", text)
    assert holds, "§6a.8's sentence naming the set's folders"
    assert sorted(set(re.findall(r"\(`([^`]+)`", holds.group(1)))) == folders
    every = all(parts.values())
    assert ("The claims part holds, in every shape" in text) is every
    assert ("`ospreyflow-backup-claims` (the claims part, in every shape" in text) is every
    assert ("in the poc shape, `ospreyflow-backup-claims`" in text) is (not every)
    poc_alone = bool(claims["poc"]) and not any(claims[s] for s in standard)
    assert ("; and, in the poc shape, the Ingest root's claim" in text) is poc_alone

    outside = re.search(r"\*\*Not in a set\*\*: (.*?) A restore leaves those", text)
    assert outside, "§6a.8's sentence naming what no set holds"
    named = {n.split(":")[0] for n in re.findall(r"\(`([^`]+)`", outside.group(1))}
    assert named == left_out("poc") | {f for s in standard for f in left_out(s)}
    in_standard_only = all("ingest" in left_out(s) for s in standard) and "ingest" not in left_out("poc")
    assert ("in the standard shape, the Ingest root (`ingest`" in outside.group(1)) is in_standard_only
    assert bool(re.search(r"`ospreyflow-shared`[^.]{0,40}is not backed up", text)) is (not folders)
