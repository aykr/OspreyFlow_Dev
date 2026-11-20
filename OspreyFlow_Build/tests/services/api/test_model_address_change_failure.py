"""*Admin › Models*: a failed change of an engine's address never leaves gateway entries the record
does not agree with, and start-up checks every entry's address against the record (build SE5,
found on main by a read-only scout on 20 November 2026; ADR-135 Amendment 2 decision 1: a key
entered for one address is never sent to another).

**The fault.** An edit that moves an engine's address deletes the engine's credential, saves the
record without its key (still at the **old** address), rebuilds the engine's gateway entries at the
**new** address, then saves the new record. If that is refused the change is put back, best
effort; if the put-back fails too, only a log line was written. `_reconcile` then kept an entry
already held under the same id, whatever address it carried, and an entry names the engine's one
credential, so the next key set stored a key that the gateway sent to the **new** address while
the record said the old one.

**Pure.** The gateway is the stand-in that refuses as the pinned one was measured to (rule 15), with
a transport laid over it that refuses or loses an answer where a test says. The models record, the
audit and the gateway are all in memory or in a temporary folder; nothing is live. Every key is made
at run time (the owner's rules for keys): none is written in this file.

**Which test fails if each behaviour is violated (rule 12)**

- the reproduction, at the real call site (a failed move, a failed undo or a stopped process, then a
  later key set, and where the stand-in says the key was sent):
  `test_a_failed_move_never_lets_a_later_key_reach_an_address_the_record_does_not_hold`;
- part 1, a failed change withdraws what it made at the new address, whatever failed (an exception
  nobody named, an interruption, a second one while it is undone, a timeout after the gateway
  wrote, a record that cannot be saved):
  `test_a_failed_move_withdraws_the_new_address_entries_whatever_the_failure`;
- part 2, an undo that fails is said in words, the engine is marked unavailable, and the audit says
  so without the key, and a key entered again repairs it:
  `test_an_undo_that_fails_is_said_in_words_marks_the_engine_and_is_audited`;
- part 3, start-up compares every entry's address with the record, covering the process having
  died mid-change, a deployment the fault already reached, an entry for an engine the record does
  not hold (with and without a models file), and a withdrawal that cannot be made:
  `test_start_puts_right_what_a_stopped_change_left_at_another_address`,
  `test_a_deployment_the_fault_already_reached_is_put_right_at_start`,
  `test_an_entry_for_an_engine_the_record_does_not_hold_is_withdrawn_at_start`,
  `test_a_start_that_cannot_withdraw_says_so_in_words_and_marks_the_engine`;
- the key is not taken while an entry disagrees and cannot be withdrawn:
  `test_a_key_is_not_taken_while_an_entry_disagrees_and_cannot_be_withdrawn`;
- `_reconcile` no longer keeps an entry at another address, because it was held under the same id:
  `test_adding_an_engine_over_a_stale_entry_at_another_address_makes_it_at_the_new_one`;
- the fix does not rebuild what agrees (a check that a good deployment is left alone):
  `test_a_deployment_that_agrees_loses_no_entry_at_start_or_at_a_key_change`;
- the paths the scout found to send no key anywhere (`remove_key`, `remove_engine`, and a rotation
  the gateway refuses after the old key was removed):
  `test_the_paths_that_take_a_key_away_send_none_anywhere`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from services.api.app import app, get_principal
from services.api.model_admin import (
    GatewayAdmin,
    InMemoryModelAdminAudit,
    Installed,
    ModelAdmin,
    ModelAdminRefused,
    ModelSettingsFile,
)

from adapters.model_litellm.stand_in import StandInGateway, StandInProvider
from schemas.deployment import ModelProviderConfig
from schemas.domain import Principal

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])
ENGINES = "/v1/admin/models/engines"
OLD = "https://old-gateway.example.org/v1"
NEW = "https://collector.example.net/v1"
MODEL = "gemini-2.5-flash"
CALLED = f"gemini/{MODEL}"
ENGINE = {"name": "gemini", "label": "Gemini", "roles": {"extraction": MODEL}}


def a_key() -> str:
    """A key made now, for this run only."""
    return "sk-" + secrets.token_hex(16)


def provider(address: str | None, name: str = "gemini", **more: Any) -> ModelProviderConfig:
    body: dict[str, Any] = {**ENGINE, "name": name, "label": name.title(), **more}
    if address is not None:
        body["api_base"] = address
    return ModelProviderConfig.model_validate(body)


class Died(BaseException):
    """The process stopped between two steps: nothing in the Conduit catches it, as nothing can."""


class Faults(httpx.AsyncBaseTransport):
    """The real stand-in, with faults laid over it where a test says: a request refused as the real
    gateway refuses a write its database does not take (500), or its answer lost after it wrote."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner
        self.refuse: list[Callable[[httpx.Request], bool]] = []
        self.lose_answer: list[Callable[[httpx.Request], bool]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        if any(rule(request) for rule in self.refuse):
            return httpx.Response(
                500,
                json={
                    "error": {"message": "Internal Server Error", "type": "internal_server_error"}
                },
            )
        answer = await self.inner.handle_async_request(request)
        if any(rule(request) for rule in self.lose_answer):
            raise httpx.ReadTimeout("the answer was lost", request=request)
        return answer


def on(path: str) -> Callable[[httpx.Request], bool]:
    return lambda request: request.url.path == path


def refuse_the_update_then_every_removal() -> Callable[[httpx.Request], bool]:
    """The change is refused after the new entries are made (the engine's key update), and from then
    on the gateway's database refuses every removal, so the undo fails too."""
    seen: list[bool] = []

    def rule(request: httpx.Request) -> bool:
        if request.url.path == "/key/update":
            seen.append(True)
            return True
        return bool(seen) and request.url.path == "/model/delete"

    return rule


class Scene:
    """One deployment: a gateway, a models folder and an audit, which any number of Conduit
    processes (`process()`) are put over, one after another as a restart is."""

    def __init__(self, tmp_path: Path) -> None:
        self.folder = tmp_path / "model-settings"
        self.master = a_key()
        self.first = a_key()
        self.second = a_key()
        self.gateway = StandInGateway(
            master_key=self.master,
            salt_key=a_key(),
            providers={"gemini": StandInProvider(self.second, frozenset({MODEL}))},
        )
        self.audit = InMemoryModelAdminAudit()
        self.faults = Faults(self.gateway.transport())
        self.admin = self.process()

    def process(self, *, faulty: bool = True, retry_seconds: float = 30.0) -> ModelAdmin:
        http = httpx.AsyncClient(
            base_url="http://litellm:4000",
            transport=self.faults if faulty else self.gateway.transport(),
            headers={"Authorization": f"Bearer {self.master}"},
        )
        return ModelAdmin(
            installed=Installed(
                providers=[],
                defaults={},
                key_present={},
                local_only=False,
                sendable=["O"],
                locals={
                    "extraction": "qwen2.5:7b-instruct",
                    "vision": None,
                    "transcription": None,
                    "embedding": None,
                },
            ),  # fmt: skip
            settings_file=ModelSettingsFile(self.folder),
            gateway=GatewayAdmin(http),
            audit=self.audit,
            retry_seconds=retry_seconds,
        )

    async def set_up(self) -> None:
        """The engine at the old address, with its key."""
        await self.admin.add_engine("admin-1", provider(OLD))
        await self.admin.set_key("admin-1", "gemini", SecretStr(self.first))
        assert self.gateway.credential("osprey-gemini") == self.first

    def at(self) -> dict[str, str | None]:
        """Each entry the gateway holds and the address it carries."""
        return {
            i: self.gateway.stored_params(i).get("api_base")
            for i in sorted(self.gateway.stored_ids())
        }

    async def call(self) -> int:
        """An analyst's call, as the gateway receives it: the stand-in records where it sent which
        key."""
        async with httpx.AsyncClient(
            base_url="http://litellm:4000",
            transport=self.gateway.transport(),
            headers={"Authorization": f"Bearer {self.master}"},
        ) as client:
            answer = await client.post(
                "/chat/completions",
                json={"model": CALLED, "messages": [{"role": "user", "content": "x"}]},
            )
        return answer.status_code

    def addresses_reached_by(self, key: str) -> set[str | None]:
        return {base for base, sent in self.gateway.sent if sent == key}

    async def plant_entries_at(self, address: str) -> None:
        """What a deployment the fault already reached holds: the record says the old address, the
        engine's entries are at another (made through the real adapter, as the rebuild made
        them)."""
        gateway = self.admin._gateway
        for entry in list(self.gateway.stored_ids()):
            await gateway.delete_entry(entry)
        await gateway.add_entry(provider(address), MODEL)


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    return Scene(tmp_path)


@pytest.fixture
def routed(scene: Scene) -> Iterator[TestClient]:
    app.state.model_admin = scene.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.state.model_admin = None


# --- the reproduction (item 1) -----------------------------------------------------------------


@pytest.mark.parametrize(
    "how", ["the gateway refuses", "the record cannot be saved", "the process stops"]
)
async def test_a_failed_move_never_lets_a_later_key_reach_an_address_the_record_does_not_hold(
    scene: Scene, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    """(a) the address change is refused or interrupted after the new entries are made, (b) the
    undo fails or the process dies, then (c) a key is entered. The stand-in says where it sent
    it."""
    await scene.set_up()
    moved = provider(NEW)
    if how == "the gateway refuses":
        scene.faults.refuse.append(refuse_the_update_then_every_removal())
        with pytest.raises(ModelAdminRefused):
            await scene.admin.edit_engine("admin-1", "gemini", moved)
    elif how == "the record cannot be saved":
        saves: list[int] = []
        real = scene.admin._file.save

        def full(settings: Any) -> None:
            saves.append(1)
            if len(saves) == 2:  # the first save drops the key; the second is the new record
                raise OSError(28, "No space left on device")
            real(settings)

        monkeypatch.setattr(scene.admin._file, "save", full)
        # From the moment the save fails the gateway's database refuses every removal.
        scene.faults.refuse.append(lambda r: len(saves) > 1 and r.url.path == "/model/delete")
        with pytest.raises(ModelAdminRefused):
            await scene.admin.edit_engine("admin-1", "gemini", moved)
        monkeypatch.undo()
    else:

        async def stopped(*_args: Any, **_kwargs: Any) -> None:
            raise Died

        monkeypatch.setattr(scene.admin._gateway, "put_engine_key", stopped)
        with pytest.raises(Died):
            await scene.admin.edit_engine("admin-1", "gemini", moved)
        monkeypatch.undo()
    assert scene.admin.settings.providers[0].api_base == OLD, (
        "the record still holds the old address"
    )
    scene.faults.refuse.clear()
    scene.faults.lose_answer.clear()

    await scene.admin.set_key(
        "admin-1", "gemini", SecretStr(scene.second)
    )  # later, with the gateway well
    await scene.call()

    reached = scene.addresses_reached_by(scene.second)
    assert NEW not in reached, (
        f"the key went to an address the record was never given for: {scene.at()}"
    )
    assert reached == {OLD}, "and the engine answers at the address the record holds"
    assert scene.at() and set(scene.at().values()) == {OLD}


# --- part 1: whatever fails, what was made at the new address is withdrawn ---------------------


@pytest.mark.parametrize(
    "how",
    [
        "an exception nobody named",
        "an interruption",
        "an interruption, and another while it is undone",
        "a timeout after the gateway wrote",
        "the record cannot be saved",
    ],
)
async def test_a_failed_move_withdraws_the_new_address_entries_whatever_the_failure(
    scene: Scene, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    await scene.set_up()
    gateway = scene.admin._gateway
    real = gateway.put_engine_key
    first: list[bool] = []
    reached = asyncio.Event()

    async def fails_once(p: ModelProviderConfig, limits: Any) -> None:
        if not first:  # the new entries are made by now; the put-back's own call is the next
            first.append(True)
            if how == "an exception nobody named":
                raise RuntimeError("a garbled answer")
            if how.startswith("an interruption"):
                reached.set()
                await asyncio.sleep(3600)
        await real(p, limits)

    undoing = asyncio.Event()
    real_delete = gateway.delete_entry

    async def slow_delete(model_id: str) -> None:
        if reached.is_set() and not undoing.is_set():  # the undo's first removal
            undoing.set()
            await asyncio.sleep(0.05)
        await real_delete(model_id)

    moved = provider(NEW)
    if how in ("an exception nobody named", "an interruption"):
        monkeypatch.setattr(gateway, "put_engine_key", fails_once)
    elif how.startswith("an interruption, and"):
        monkeypatch.setattr(gateway, "put_engine_key", fails_once)
        monkeypatch.setattr(gateway, "delete_entry", slow_delete)
    elif how == "a timeout after the gateway wrote":
        wrote: list[bool] = []

        def lost_once(request: httpx.Request) -> bool:
            if request.url.path == "/model/new" and not wrote:
                wrote.append(True)
                return True
            return False

        scene.faults.lose_answer.append(lost_once)
    else:
        saves: list[int] = []
        saved = scene.admin._file.save

        def full(settings: Any) -> None:
            saves.append(1)
            if len(saves) == 2:
                raise OSError(28, "No space left on device")
            saved(settings)

        monkeypatch.setattr(scene.admin._file, "save", full)

    if how.startswith("an interruption"):
        task = asyncio.ensure_future(scene.admin.edit_engine("admin-1", "gemini", moved))
        await asyncio.wait_for(reached.wait(), 5)
        assert NEW in scene.at().values(), "the plant stops it with the new entries made"
        task.cancel()
        if how != "an interruption":
            await asyncio.wait_for(undoing.wait(), 5)
            task.cancel()  # asked to stop again while it is putting the gateway back
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ModelAdminRefused):
            await scene.admin.edit_engine("admin-1", "gemini", moved)
    monkeypatch.undo()
    scene.faults.lose_answer.clear()

    assert scene.at(), "the engine's entries are put back, not left withdrawn"
    assert set(scene.at().values()) == {OLD}, f"an entry is left at the new address: {scene.at()}"
    assert scene.admin.settings.providers[0].api_base == OLD
    assert scene.gateway.credential("osprey-gemini") is None, (
        "the old key is gone, not kept for the new"
    )
    assert scene.admin.key_state("gemini") == "none"


# --- part 2: an undo that fails is loud --------------------------------------------------------


@pytest.mark.parametrize("moved", [True, False], ids=["the address moved", "the address kept"])
def test_an_undo_that_fails_is_said_in_words_marks_the_engine_and_is_audited(
    scene: Scene, routed: TestClient, moved: bool
) -> None:
    asyncio.run(scene.set_up())
    scene.faults.refuse.append(on("/model/new"))  # the entries cannot be made, at either address
    answer = routed.put(
        f"{ENGINES}/gemini",
        json={"provider": {**ENGINE, "label": "Changed", "api_base": NEW if moved else OLD}},
    )
    assert answer.status_code in (500, 502), answer.text
    words = answer.json()["detail"]["detail"].lower()
    assert "unavailable" in words and "repaired" in words, "the engine is said to be unavailable"
    assert "restart" in words, "and what to do is said"
    assert scene.first not in answer.text

    view = routed.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] != "set", "the engine is marked, not shown as set"
    assert scene.admin.routes().engines["gemini"].key_present is False, "and offered to no analyst"

    last = scene.audit.entries[-1]
    assert (last.action, last.engine) == ("engine_edited", "gemini")
    assert last.outcome.startswith("refused") and "unavailable" in last.outcome, last.outcome
    recorded = json.dumps([e.model_dump(mode="json") for e in scene.audit.entries])
    assert scene.first not in recorded and scene.second not in recorded

    # Repaired as the words say: the gateway answers again, and the key is entered again.
    scene.faults.refuse.clear()
    asyncio.run(scene.admin.set_key("admin-1", "gemini", SecretStr(scene.second)))
    assert scene.admin.key_state("gemini") == "set"
    assert scene.admin.routes().engines["gemini"].key_present is True
    assert asyncio.run(scene.call()) == 200
    assert scene.addresses_reached_by(scene.second) == {OLD}


# --- part 3: start-up compares every entry with the record -------------------------------------


async def test_start_puts_right_what_a_stopped_change_left_at_another_address(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process died between two steps (nothing ran to undo): the next start, and then a key set,
    never send a key to the address the record was not given."""
    await scene.set_up()

    async def stopped(*_args: Any, **_kwargs: Any) -> None:
        raise Died

    monkeypatch.setattr(scene.admin._gateway, "put_engine_key", stopped)
    with pytest.raises(Died):
        await scene.admin.edit_engine("admin-1", "gemini", provider(NEW))
    monkeypatch.undo()
    assert NEW in scene.at().values(), "the plant leaves the new entries made"

    restarted = scene.process(faulty=False)
    await restarted.start()
    assert set(scene.at().values()) == {OLD}, scene.at()
    await restarted.set_key("admin-1", "gemini", SecretStr(scene.second))
    await scene.call()
    assert scene.addresses_reached_by(scene.second) == {OLD}


async def test_a_deployment_the_fault_already_reached_is_put_right_at_start(scene: Scene) -> None:
    """Record at the old address, a key held, entries at another: what main left behind."""
    await scene.set_up()
    await scene.plant_entries_at(NEW)
    assert set(scene.at().values()) == {NEW}

    await scene.process(faulty=False).start()
    assert set(scene.at().values()) == {OLD}, scene.at()
    assert scene.gateway.credential("osprey-gemini") == scene.first, "the key is kept for the old"
    await scene.call()
    assert scene.addresses_reached_by(scene.first) == {OLD}


@pytest.mark.parametrize("models_file", [False, True], ids=["no models file", "a models file"])
async def test_an_entry_for_an_engine_the_record_does_not_hold_is_withdrawn_at_start(
    scene: Scene, models_file: bool
) -> None:
    if models_file:
        await scene.set_up()
    stray = provider(NEW, name="openai", roles={"extraction": "gpt-4.1-mini"})
    await scene.admin._gateway.add_entry(stray, "gpt-4.1-mini")
    assert any(i.startswith("osprey-openai-") for i in scene.gateway.stored_ids())

    await scene.process(faulty=False).start()
    assert not any(i.startswith("osprey-openai-") for i in scene.gateway.stored_ids()), scene.at()
    if models_file:
        assert any(i.startswith("osprey-gemini-") for i in scene.gateway.stored_ids())


async def test_a_start_that_cannot_withdraw_says_so_in_words_and_marks_the_engine(
    scene: Scene, caplog: pytest.LogCaptureFixture
) -> None:
    await scene.set_up()
    await scene.plant_entries_at(NEW)
    scene.faults.refuse.append(on("/model/delete"))
    restarted = scene.process(retry_seconds=0.001)
    with caplog.at_level(logging.WARNING):
        await restarted.start()  # never stops the Conduit starting
    assert restarted.routes().engines["gemini"].key_present is False, "offered to no analyst"
    assert restarted.key_state("gemini") != "set"
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "gemini" in said and "address" in said and "unavailable" in said, said

    scene.faults.refuse.clear()  # the gateway answers again: the retry withdraws and makes them
    for _ in range(300):
        if set(scene.at().values()) == {OLD}:
            break
        await asyncio.sleep(0.01)
    await restarted.close()
    assert set(scene.at().values()) == {OLD}, scene.at()
    assert restarted.routes().engines["gemini"].key_present is True


async def test_a_key_is_not_taken_while_an_entry_disagrees_and_cannot_be_withdrawn(
    scene: Scene,
) -> None:
    await scene.set_up()
    await scene.plant_entries_at(NEW)
    scene.faults.refuse.append(on("/model/delete"))
    with pytest.raises(ModelAdminRefused):
        await scene.admin.set_key("admin-1", "gemini", SecretStr(scene.second))
    assert scene.gateway.credential("osprey-gemini") != scene.second, "the key was stored"
    scene.faults.refuse.clear()
    await scene.call()
    assert scene.second not in {k for _, k in scene.gateway.sent}


async def test_adding_an_engine_over_a_stale_entry_at_another_address_makes_it_at_the_new_one(
    scene: Scene,
) -> None:
    """`_reconcile` kept an entry held under the same id, whatever address it carried."""
    stray = provider(NEW, name="openai", roles={"extraction": "gpt-4.1-mini"})
    await scene.admin._gateway.add_entry(stray, "gpt-4.1-mini")
    await scene.admin.add_engine(
        "admin-1", provider(OLD, name="openai", roles={"extraction": "gpt-4.1-mini"})
    )
    assert set(scene.at().values()) == {OLD}, scene.at()


async def test_a_deployment_that_agrees_loses_no_entry_at_start_or_at_a_key_change(
    scene: Scene,
) -> None:
    """The check must not rebuild what already agrees: an entry deleted is cooled down and its calls
    refused for a while."""
    await scene.set_up()
    before = scene.at()
    scene.gateway.seen.clear()
    await scene.process(faulty=False).start()
    await scene.admin.set_key("admin-1", "gemini", SecretStr(scene.second))
    assert scene.at() == before
    assert not [line for line in scene.gateway.seen if "/model/delete" in line], (
        "an entry was removed"
    )
    assert not [line for line in scene.gateway.seen if "/model/new" in line], (
        "an entry was made again"
    )


# --- the other paths (item 4): read, and shown to send no key anywhere -------------------------


@pytest.mark.parametrize("how", ["remove_key", "remove_engine", "a rotation refused after removal"])
async def test_the_paths_that_take_a_key_away_send_none_anywhere(scene: Scene, how: str) -> None:
    """`remove_engine` reconciles, then deletes the key, then saves; `remove_key` deletes then
    saves; a rotation the gateway refuses after the old key was removed records the key as lost.
    After each, a call through the gateway carries no key to any address."""
    await scene.set_up()
    if how == "remove_key":
        await scene.admin.remove_key("admin-1", "gemini")
    elif how == "remove_engine":
        await scene.admin.remove_engine("admin-1", "gemini")
    else:
        scene.gateway.refuse_credentials = 500
        with pytest.raises(ModelAdminRefused):
            await scene.admin.set_key("admin-1", "gemini", SecretStr(scene.second))
        assert scene.admin.key_state("gemini") == "lost"
    await scene.call()
    assert scene.gateway.credential("osprey-gemini") is None
    assert {k for _, k in scene.gateway.sent} <= {None}, scene.gateway.sent
