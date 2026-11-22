"""The owner's file 010 (22 November 2026): the line's stop on an account near its limit moves from 90% to 95%. An
account at or above 95% of a window starts no new slice; below it, it does. Nothing else about the stop changes: per
account, for a new slice's builder and verifier accounts, the owner decides and work is not moved to another account.
"""
from __future__ import annotations

import json

import pytest

from test_gates import started, world  # noqa: F401  (world is a fixture)


def at(w, share, account="default"):
    acc = w["data"] / "accounts"
    acc.mkdir(exist_ok=True)
    (acc / f"{account}.json").write_text(json.dumps({"windows": {"five_hour": {"utilization": share,
                                                                               "resetsAt": 4102444800}}}))


@pytest.mark.parametrize("share", [0.93, 0.949])
def test_below_95_percent_a_new_slice_starts(world, share):
    w = world
    at(w, share)
    p, _ = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (w["data"] / "records/S1/frozen.json").exists()


@pytest.mark.parametrize("share", [0.95, 0.99])
def test_at_or_above_95_percent_no_new_slice_starts_and_the_owner_decides(world, share):
    w = world
    at(w, share)
    p, _ = started(w)
    said = p.stdout + p.stderr
    assert p.returncode != 0 and f"{share:.0%} of its five-hour limit" in said, said
    assert "The owner decides; work is not moved to another account." in said
    assert not (w["data"] / "records/S1/frozen.json").exists()
