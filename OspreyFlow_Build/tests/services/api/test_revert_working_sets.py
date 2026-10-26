"""ADR-127 decision 6 (B2-4c2): what a revert does in the Conduit's own stores, from outside the
Conduit.

The revert runs as a script, in its own process, so it reaches the working-set store, the stored
history and Pub/Sub directly, as `scripts/strip_change_provenance.py` does. Three things it must do
that a reader's own removal does not:

- remove the load's elements from every case holding them and **publish** each case's stored
  removal on that case's channel, so every Conduit instance holding a socket projects it for its
  reader (`WorkingSetReverter.remove`);
- take them out of every stored history step (`InvestigationHistoryStore.remove_elements`, proved
  live in `test_history_relabel.py`);
- clear every kept result the Conduit holds (`invalidate_every_cache`): the explore panel's figures
  are in the shared Valkey under `cache:explore:`, so one process clearing them clears them for all.

What a mistake would do, and the case that catches it:

- a removal that reaches the stores and tells no connected reader
  (`test_every_case_changed_is_told_on_its_own_channel_with_the_stored_form`);
- the stored history keeping what was taken back (`test_the_stored_history_is_scrubbed_of_the_same_ids`);
- the revert's process clearing a cache the Conduit does not read, or one prefix of three
  (`test_a_cache_is_cleared_for_a_second_process`);
- a new kept result added later that the revert never clears
  (`test_every_cache_the_conduit_keeps_is_one_the_revert_clears`)."""

from __future__ import annotations

import ast
import fnmatch
import json
from pathlib import Path
from typing import Any

from services.api.cache import CACHE_PREFIXES, CachedQuery, invalidate_every_cache
from services.api.working_set.models import DeltaRemove, decode_delta
from services.api.working_set.service import WorkingSetService
from services.api.working_set_revert import WorkingSetReverter

from schemas.domain import Principal, Subgraph

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node


class SharedValkey:
    """One Valkey as two processes see it: published messages, and a key space both read and
    write. Only what the caches and the notify channel use."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.kv[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[str]]:
        return 0, [k for k in self.kv if fnmatch.fnmatch(k, match)]

    async def delete(self, *keys: str) -> int:
        return sum(self.kv.pop(k, None) is not None for k in keys)


class History:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], list[str]]] = []

    async def remove_elements(self, node_ids: Any, edge_ids: Any) -> int:
        self.calls.append((list(node_ids), list(edge_ids)))
        return 0


async def _world() -> tuple[FakeWorkingSetStore, WorkingSetReverter, SharedValkey, History]:
    store = FakeWorkingSetStore()
    await store.add_nodes("case-a", [node("n1"), node("n-secret", "SECRET"), node("keep")])
    await store.add_edges("case-a", [edge("e1", "n1", "keep")])
    await store.add_nodes("case-b", [node("n1")])
    await store.add_nodes("case-c", [node("unrelated")])
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)
    valkey, history = SharedValkey(), History()
    return store, WorkingSetReverter(service, valkey, history), valkey, history  # type: ignore[arg-type]


async def test_every_case_changed_is_told_on_its_own_channel_with_the_stored_form() -> None:
    store, reverter, valkey, _ = await _world()
    cases = await reverter.remove(["n1", "n-secret"], ["e1"])
    assert cases == 2
    channels = sorted(channel for channel, _ in valkey.published)
    assert channels == ["ws:case-a:notify", "ws:case-b:notify"], "case-c holds none: no message"
    by_channel = {c: decode_delta(json.loads(m)) for c, m in valkey.published}
    delta = by_channel["ws:case-a:notify"]
    assert isinstance(delta, DeltaRemove)
    assert delta.removed is not None, "the stored form, record included, so each socket projects it"
    assert {"n1", "n-secret"} == set(delta.node_ids) and "e1" in delta.edge_ids
    assert delta.removed.nodes["n-secret"].handling.classification == "SECRET"
    assert await store.current_seq("case-a") == delta.seq


async def test_the_stored_history_is_scrubbed_of_the_same_ids() -> None:
    _, reverter, _, history = await _world()
    await reverter.remove(["n1", "n-secret"], ["e1"])
    assert history.calls == [(["n1", "n-secret"], ["e1"])]
    # Even when no case holds them any more (a closed case's steps keep bodies too): scrubbed again.
    await reverter.remove(["n1", "n-secret"], ["e1"])
    assert len(history.calls) == 2


async def test_a_rerun_publishes_nothing() -> None:
    _, reverter, valkey, _ = await _world()
    await reverter.remove(["n1"], [])
    sent = len(valkey.published)
    assert await reverter.remove(["n1"], []) == 0
    assert len(valkey.published) == sent


async def test_a_cache_is_cleared_for_a_second_process() -> None:
    """The Conduit (one process) keeps results under `cache:<prefix>:`; the revert is another
    process on the same Valkey. Clearing there clears here, for each of the three kept kinds, and
    leaves every other key alone."""
    valkey = SharedValkey()
    reader = Principal(id="a", clearance="OFFICIAL", org_unit="unit-1")
    conduit = {
        prefix: CachedQuery(valkey, prefix=prefix, ttl_seconds=300)  # type: ignore[arg-type]
        for prefix in CACHE_PREFIXES
    }
    for prefix, cache in conduit.items():
        await cache.put("q", reader, {"kept": prefix})
        assert await cache.get("q", reader) == {"kept": prefix}
    valkey.kv["ws:case-a:seq"] = "7"
    await invalidate_every_cache(SharedValkey_second_process(valkey))  # type: ignore[arg-type]
    for cache in conduit.values():
        assert await cache.get("q", reader) is None
    assert valkey.kv == {"ws:case-a:seq": "7"}


def SharedValkey_second_process(valkey: SharedValkey) -> SharedValkey:
    """Another client of the same server: it shares the key space, and nothing in-process."""
    other = SharedValkey()
    other.kv = valkey.kv
    other.published = valkey.published
    return other


def kept_result_calls(root: Path) -> tuple[set[str], list[str]]:
    """Every `CachedQuery` in the Python files under `root`: the constant prefixes it is built with,
    and each place it is not built with one. A prefix that is not a constant keyword (a positional
    one, a variable, a `**` spread), and a `CachedQuery` reached by another name (an aliased import,
    an attribute of a module, an assignment of the class) are all the second kind: the revert
    clears `CACHE_PREFIXES`, and a prefix this cannot read is a kept result it cannot promise to
    clear."""
    prefixes: set[str] = set()
    unreadable: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts or "node_modules" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {"CachedQuery"}
        for found in ast.walk(tree):
            if isinstance(found, ast.ImportFrom):
                names |= {a.asname for a in found.names if a.name == "CachedQuery" and a.asname}
        for found in ast.walk(tree):
            where = f"{path.name}:{getattr(found, 'lineno', 0)}"
            if isinstance(found, ast.Assign) and isinstance(found.value, ast.Name):
                if found.value.id in names:
                    unreadable.append(f"{where} assigns the class to another name")
            if not isinstance(found, ast.Call):
                continue
            func = found.func
            called = (isinstance(func, ast.Name) and func.id in names) or (
                isinstance(func, ast.Attribute) and func.attr == "CachedQuery"
            )
            if not called:
                continue
            keyword = [k for k in found.keywords if k.arg == "prefix"]
            if (
                len(found.args) > 1
                or any(k.arg is None for k in found.keywords)
                or len(keyword) != 1
                or not isinstance(keyword[0].value, ast.Constant)
            ):
                unreadable.append(f"{where} builds a CachedQuery with no constant prefix keyword")
            else:
                prefixes.add(str(keyword[0].value.value))
    return prefixes, unreadable


def test_every_cache_the_conduit_keeps_is_one_the_revert_clears() -> None:
    """A kept result added later under a prefix the revert does not clear would serve a reverted
    load's figures until it expires. Every `CachedQuery` under `services/` is built with a constant
    `prefix=` keyword, and each is one of `CACHE_PREFIXES`."""
    services = Path(__file__).resolve().parents[4] / "OspreyFlow_Core" / "services"
    used, unreadable = kept_result_calls(services)
    assert unreadable == []
    assert "explore" in used, "the scan finds the explore cache the Conduit builds"
    assert used <= set(CACHE_PREFIXES)


def test_the_scan_flags_each_way_a_prefix_could_escape_it(tmp_path: Path) -> None:
    """Rule 15 for the test above: it can only fail for a shape it reads, so each shape that would
    hide a prefix is planted and shown to be reported."""
    shapes = {
        "constant.py": "from services.api.cache import CachedQuery\n"
        "c = CachedQuery(client, prefix='explore', ttl_seconds=1)\n",
        "variable.py": "from services.api.cache import CachedQuery\n"
        "p = 'x'\nc = CachedQuery(client, prefix=p, ttl_seconds=1)\n",
        "positional.py": "from services.api.cache import CachedQuery\n"
        "c = CachedQuery(client, 'x', 1)\n",
        "spread.py": "from services.api.cache import CachedQuery\n"
        "c = CachedQuery(client, **options)\n",
        "aliased.py": "from services.api.cache import CachedQuery as CQ\n"
        "c = CQ(client, prefix=prefix, ttl_seconds=1)\n",
        "attribute.py": "import services.api.cache as cache\n"
        "c = cache.CachedQuery(client, prefix=other, ttl_seconds=1)\n",
        "assigned.py": "from services.api.cache import CachedQuery\n"
        "make = CachedQuery\nc = make(client, prefix='y', ttl_seconds=1)\n",
        "missing.py": "from services.api.cache import CachedQuery\nc = CachedQuery(client)\n",
    }
    for name, source in shapes.items():
        (tmp_path / name).write_text(source)
    prefixes, unreadable = kept_result_calls(tmp_path)
    assert prefixes == {"explore"}, "only the constant keyword is read as a prefix"
    flagged = {line.split(":")[0] for line in unreadable}
    assert flagged == {
        "variable.py",
        "positional.py",
        "spread.py",
        "aliased.py",
        "attribute.py",
        "assigned.py",
        "missing.py",
    }
