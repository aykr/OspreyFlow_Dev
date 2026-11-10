"""Each lane's Playwright port block (`scripts/lane_ports.tsv`, T2): every lane has its own, and no
block meets another, a stack's port or the owner's deployment's.

`OspreyFlow_Core/apps/lanePorts.ts` moves each config's port (its `lanePort(<port>)`) by 100 x the
slot; this reads those ports from Core's own source, so a config added later is covered.
- `test_every_lane_has_a_row_and_no_two_share_a_slot`
- `test_no_block_meets_another_a_stack_s_port_or_the_owner_s`
"""

from __future__ import annotations

import re
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"
STEP = 100
# The owner's deployment's ports, and the demo's live/ port.
OWNER = {2480, 5432, 80, 8000, 8080, 8081, 5173}


def _rows(path: Path) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.split("\t") for line in lines if line and not line.startswith("#")]


def slots(text: str | None = None) -> dict[str, int]:
    rows = (
        _rows(BUILD / "scripts" / "lane_ports.tsv")
        if text is None
        else [line.split("\t") for line in text.splitlines() if line and not line.startswith("#")]
    )
    return {lane: int(slot) for lane, slot in rows}


def base_ports() -> set[int]:
    found: set[int] = set()
    for path in (CORE / "apps").rglob("*.ts"):
        if "node_modules" in path.parts:
            continue
        found |= {
            int(n) for n in re.findall(r"lanePort\((\d+)\)", path.read_text(encoding="utf-8"))
        }
    return found


def clashes(table: dict[str, int], bases: set[int], spoken: set[int]) -> list[str]:
    owner: dict[int, str] = {}
    said: list[str] = []
    for lane, slot in [("main", 0), *table.items()]:
        for base in sorted(bases):
            port = base + STEP * slot
            if port in spoken:
                said.append(f"{lane}'s {port} is already spoken for")
            elif port in owner:
                said.append(f"{lane}'s {port} is also {owner[port]}'s")
            owner[port] = lane
    return said


def test_every_lane_has_a_row_and_no_two_share_a_slot() -> None:
    table = slots()
    lanes = {p.name for p in (BUILD / "process" / "lanes").iterdir() if (p / "BRIEF.md").is_file()}
    assert sorted(lanes - set(table)) == [], "a lane with no Playwright slot: add its row"
    assert len(set(table.values())) == len(table), table
    assert 0 not in table.values(), "slot 0 is the main checkout's"


def test_no_block_meets_another_a_stack_s_port_or_the_owner_s() -> None:
    bases = base_ports()
    assert {5183, 5184, 5185, 5186, 5191, 5192, 5193, 5194, 7217, 7218, 7219, 7220} <= bases, bases
    stacks = {int(row[3]) for row in _rows(BUILD / "scripts" / "lane_stacks.tsv")}
    assert clashes(slots(), bases, stacks | OWNER) == []


def test_the_check_finds_a_shared_slot_and_a_spoken_port() -> None:
    bases = {5185}
    assert clashes(slots("a\t1\nb\t1\n"), bases, set()) == ["b's 5285 is also a's"]
    assert clashes(slots("a\t247\n"), bases, {5432}) == []  # 5185 + 24700: clear
    assert clashes(slots("a\t2\n"), {5232}, {5432}) == ["a's 5432 is already spoken for"]
