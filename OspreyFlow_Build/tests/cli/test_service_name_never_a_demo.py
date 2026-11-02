"""Step 9d finding 3: the GOV.UK header's `appearance.service_name` read "Prison Intelligence" on
every case of the GOV.UK deployment, the Ledger's included. The header names the service the whole
deployment is, and a deployment holds many cases; so nothing the product offers or writes may name
one demo case. That deployment's own `osprey.yaml` says so because its owner wrote it so (open
question 16); this holds everything else to it.

Every place a service name comes from in the product, and the case that catches a demo's name there:
- a starter's name, offered by the command and the guided page alike (`starters.DOMAINS`,
  `install_page.starter_rows`) — `test_no_offered_service_name_names_a_demo_case`;
- a seed or a demo pack writing one (none does: the look is the install's, never a seed's) —
  `test_no_seed_or_demo_fixture_writes_a_service_name`.

The demo cases are read from the pack registry (`scripts.demo_packs`), not a hand-written list, so
a new pack is covered when it is registered. `test_the_check_fails_for_the_govuk_deployments_own_name`
plants the GOV.UK deployment's own value, in the shape a starter carries it, and shows the check red.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from harness import install_page
from ospreyflow import starters
from scripts import demo_packs

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
#: Words that say what a case is rather than which one it is.
_GENERIC = {"synthetic", "demo", "dataset", "data", "real", "this", "machine", "only", "internal",
            "fixture", "public", "scale", "cohort", "corpus", "the", "a", "of", "and"}  # fmt: skip


def demo_case_names() -> list[str]:
    """Each registered demo pack's case, by its telling words ("prison intelligence", "operation
    ledger", "hmp", "enron" …), each once (the PID's two packs share one)."""
    names: set[str] = set()
    for pack in demo_packs.packs():
        head = re.split(r"[(:]", pack.case_name)[0]
        words = [w for w in re.findall(r"[a-z]+", head.lower()) if w not in _GENERIC]
        if words:
            names.add(" ".join(words))
    return sorted(names)


def _demo_named_in(service_name: str) -> list[str]:
    said = " ".join(re.findall(r"[a-z]+", service_name.lower()))
    return [name for name in demo_case_names() if re.search(rf"\b{re.escape(name)}\b", said)]


def offered_service_names() -> dict[str, str]:
    """Every service name the product offers, by where: each starter's, and the guided page's."""
    offered = {
        f"starter domain {d.id}": d.service_name
        for d in starters.DOMAINS.values()
        if d.service_name is not None
    }
    for row in install_page.starter_rows():
        if row["service_name"] is not None:
            offered[f"guided page {row['name']}"] = row["service_name"]
    return offered


def test_the_demo_cases_are_read_from_the_registry() -> None:
    names = demo_case_names()
    assert "prison intelligence" in names and "operation ledger" in names, names


def test_no_offered_service_name_names_a_demo_case() -> None:
    found = {where: _demo_named_in(name) for where, name in offered_service_names().items()}
    assert {where: hit for where, hit in found.items() if hit} == {}
    assert len(found) >= 8, "every GOV.UK starter offers a name, on the command and the page"


def test_no_seed_or_demo_fixture_writes_a_service_name() -> None:
    writers = [
        str(path.relative_to(CORE))
        for folder in ("scripts", "packages/demo_fixtures")
        for path in sorted((CORE / folder).rglob("*.py"))
        if re.search(r"service_name|appearance\s*[\[.:=]", path.read_text(encoding="utf-8"))
    ]
    # `scripts/refresh.py` reads the deployment's appearance to render the sign-in theme; it never
    # sets one.
    assert writers == ["scripts/refresh.py"], writers
    assert "service_name" not in (CORE / "scripts/refresh.py").read_text(encoding="utf-8")


def test_the_check_fails_for_the_govuk_deployments_own_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 15: the GOV.UK deployment's own value, "Prison Intelligence", planted where a starter
    carries its name — the check must name it, on the command's starter and on the guided page."""
    crime = starters.DOMAINS["crime"]
    planted = {**starters.DOMAINS, "crime": dataclasses.replace(crime, service_name="Prison Intelligence")}
    monkeypatch.setattr(starters, "DOMAINS", planted)
    found = {where: _demo_named_in(name) for where, name in offered_service_names().items()}
    hits = {where: hit for where, hit in found.items() if hit}
    assert hits == {
        "starter domain crime": ["prison intelligence"],
        "guided page govuk-crime": ["prison intelligence"],
    }
