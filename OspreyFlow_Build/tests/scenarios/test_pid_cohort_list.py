"""The cohort list: `pid_cohort_list.txt`, the 40 identifiers the demo's add-many scene pastes
(ADR-128 decision 1, B2; Brief 3's acceptance on the PID; script J3).

`demo_fixtures.pid_files.cohort_list(plan)` builds it from the plan alone, and `write_files` writes
it. The brief's figures are asserted here from the plan and not from the list: the list is read the
way the product reads a typed identifier (`services.api.identifier_reading`), looked up in an index
of the plan's own identifiers, and counted the way the route counts (read, found, matched nothing,
repeated), so a list that drifts from the plan, or an identifier the product reads as another kind,
goes red.

- **Forty, mixed.** Prison numbers, National Insurance numbers, numbers (written as the plan writes
  them) and account references all appear; 38 of the 40 resolve to plan entities, 37 of them
  distinct; one that resolves is repeated, written another way; one that does not is made up (it
  reads as nothing); one is right-shaped and absent from both profiles' plans.
- **Written as plain text**: one identifier a line, UTF-8, `\\n` ends, no header, in the demo
  profile's output only, and in the manifest's `lists` with its lines, bytes and SHA-256.
- **Reproducible**: the same list for the same plan, built twice.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from services.api.identifier_reading import read_identifier, split_identifiers

from demo_fixtures import pid_files, pid_plan


@pytest.fixture(scope="module")
def demo() -> Any:
    return pid_plan.build_plan("demo")


@pytest.fixture(scope="module")
def scale() -> Any:
    return pid_plan.build_plan("scale")


def _index(plan: Any) -> dict[tuple[str, str], str]:
    """The plan's identifiers by `(kind, canonical)` as the product reads them: prison numbers and
    National Insurance numbers of people, and the normalised value of numbers and accounts."""
    out: dict[tuple[str, str], str] = {}
    for entity in plan.entities:
        props = entity.properties
        if entity.entity_type == "Person":
            if "prison_number" in props:
                out[("prison_number", str(props["prison_number"]))] = entity.key
            if "nino" in props:
                out[("nino", str(props["nino"]))] = entity.key
        elif entity.entity_type == "Endpoint" and props.get("endpoint_kind") in (
            "msisdn",
            "account",
        ):
            out[(str(props["endpoint_kind"]), str(props["value_normalised"]))] = entity.key
    return out


def test_the_list_is_forty_identifiers_and_each_is_one_identifier_to_the_product(demo: Any) -> None:
    listed = pid_files.cohort_list(demo)
    assert len(listed) == 40
    assert split_identifiers(["\n".join(listed)]) == listed, "a line the product would split"


def test_38_resolve_to_plan_entities_2_do_not_and_1_is_repeated(demo: Any) -> None:
    index = _index(demo)
    listed = pid_files.cohort_list(demo)
    readings = [read_identifier(t) for t in listed]
    resolved = [index.get(r.key) for r in readings]
    seen: set[tuple[str, str]] = set()
    repeated = 0
    for reading in readings:
        repeated += reading.key in seen
        seen.add(reading.key)
    assert len(listed) == 40
    assert sum(1 for k in resolved if k is not None) == 38
    assert sum(1 for k in resolved if k is None) == 2
    assert repeated == 1
    assert len({k for k in resolved if k is not None}) == 37, "distinct entities"


def test_the_kinds_are_mixed(demo: Any) -> None:
    kinds = Counter(read_identifier(t).kind for t in pid_files.cohort_list(demo))
    assert {"prison_number", "nino", "msisdn", "account", "unknown"} <= set(kinds)
    assert kinds["unknown"] == 1, "one made up, read as nothing"
    assert min(kinds[k] for k in ("prison_number", "nino", "msisdn", "account")) >= 4


def test_one_miss_is_made_up_and_the_other_is_right_shaped_but_in_no_plan(
    demo: Any, scale: Any
) -> None:
    listed = pid_files.cohort_list(demo)
    misses = [t for t in listed if _index(demo).get(read_identifier(t).key) is None]
    assert len(misses) == 2
    kinds = sorted(read_identifier(t).kind for t in misses)
    assert kinds == ["prison_number", "unknown"]
    absent = next(t for t in misses if read_identifier(t).kind == "prison_number")
    assert re.fullmatch(r"Z\d{4}ZZ", absent)
    for plan in (demo, scale):
        assert ("prison_number", absent) not in _index(plan)


def test_the_repeat_is_a_number_written_another_way(demo: Any) -> None:
    listed = pid_files.cohort_list(demo)
    keys = [read_identifier(t).key for t in listed]
    (twice,) = [k for k, n in Counter(keys).items() if n == 2]
    first, second = (t for t in listed if read_identifier(t).key == twice)
    assert twice[0] == "msisdn" and first != second, "the same number, spelled two ways"


def test_the_numbers_are_written_as_the_plan_writes_them(demo: Any) -> None:
    raw = {
        str(e.properties["value_raw"])
        for e in demo.entities
        if e.entity_type == "Endpoint" and e.properties.get("endpoint_kind") == "msisdn"
    }
    numbers = [t for t in pid_files.cohort_list(demo) if read_identifier(t).kind == "msisdn"]
    assert len(set(numbers) & raw) >= 4


def test_the_list_is_the_same_each_time(demo: Any) -> None:
    assert pid_files.cohort_list(demo) == pid_files.cohort_list(demo)
    assert pid_files.cohort_list(pid_plan.build_plan("demo")) == pid_files.cohort_list(demo)


def test_the_scale_profile_has_no_list(scale: Any) -> None:
    assert pid_files.cohort_list(scale) == []


def test_the_list_is_written_as_plain_lines_and_recorded_in_the_manifest(
    demo: Any, scale: Any, tmp_path: Path
) -> None:
    report = pid_files.write_files(demo, tmp_path / "demo")
    path = tmp_path / "demo" / "pid_cohort_list.txt"
    data = path.read_bytes()
    assert data.decode("utf-8").split("\n") == [*pid_files.cohort_list(demo), ""]
    assert b"\r" not in data
    manifest = json.loads((tmp_path / "demo" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lists"] == {
        "pid_cohort_list.txt": {
            "lines": 40, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()
        }
    }
    assert [(r.name, r.rows) for r in report.lists] == [("pid_cohort_list.txt", 40)]
    assert "pid_cohort_list.txt" not in manifest["files"], "it is not a CSV"
    pid_files.write_files(scale, tmp_path / "scale")
    assert not list((tmp_path / "scale").glob("*cohort*"))
    scale_manifest = json.loads((tmp_path / "scale" / "manifest.json").read_text(encoding="utf-8"))
    assert scale_manifest["lists"] == {}
