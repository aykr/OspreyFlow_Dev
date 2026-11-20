"""*Admin › Models*: every point where a key or its credential exists and a later step can fail or be
interrupted, held as **rows** of `process/lanes/v062/slices/AD1a_KEY_PATHS_TABLE.md` (the owner's
rule, 20 November 2026: a fault that can send a key to an address it was not given for, show it
back, log it or audit it is never accepted; one that leaves an engine unavailable or the words wrong
is fixed here).

**One design, held by these cases.**

1. *A record of intent is written before a credential is deleted* (an engine whose key was set is
   saved lost first), so no way out of a change, a cancellation, a process that stops, a record
   save that fails or an answer that is lost, leaves "set" over a credential nobody can account for.
2. *The lost record is a property of the state.* **Every** reconcile (start, the retry, a key, a
   new engine, another engine's edit, the undo) removes the credential of an engine recorded lost
   before it makes any entry for it, and an engine whose credential the gateway will not remove is
   given no entry until it does (`ModelAdmin._reconcile`'s *withheld*). No caller can forget it.
3. *One decision for the words and the mark* across a refusal, an error, a cancellation and any
   other exception: "put back" only when it was (entries and credential); the key's removal said,
   with a `key_removed` audit, when it was saved; a key the gateway would not remove said held.
4. *Start-up* puts right what a stopped process left. It reads no credential (`GET /credentials`
   answers with two characters at each end of a key, so the Conduit never asks): the record of
   intent is what start reads.

**Each case plants its fault at the real call site** (the stand-in gateway, refusing as the pinned
one was measured to, with a transport over it that refuses, lets an answer be lost, garbles one,
raises raw, hangs, or stops the process where a test says), was red on the code before the fix
(`plants_key_paths_run.txt` beside `OWED.md`), and names its row. Every key is made at run time.

**Which test fails if each row's behaviour is violated (rule 12)**

row 3 `..._row_3`, row 15 `..._row_15`, row 16 and 39 `..._row_16_and_39`, row 17 `..._row_17`,
row 28 `..._row_28`, rows 29 and 30 `..._rows_29_and_30`, row 31 `..._row_31`, rows 32 and 33
`..._rows_32_and_33`, row 34 `..._row_34`, row 35 `..._row_35`, row 36 `..._row_36`,
row 37 `..._row_37`, row 38 `..._row_38`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from services.api.model_admin import ModelAdminRefused
from tests.services.api.test_model_address_change_failure import (
    MODEL,
    NEW,
    OLD,
    Died,
    Faults,
    Scene,
    a_key,
    provider,
)

from adapters.model_litellm.stand_in import _seal


class Plants(Faults):
    """`Faults`, and more: an answer garbled (200, not JSON), an exception raised raw (not an
    `httpx.HTTPError`, which the client would turn into words), a request answered and then the
    task made to wait (so a cancellation lands just after the gateway wrote), and the process
    stopped just after the gateway wrote."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        super().__init__(inner)
        self.garble: list[Callable[[httpx.Request], bool]] = []
        self.raw: list[tuple[Callable[[httpx.Request], bool], BaseException]] = []
        self.hang_after: list[Callable[[httpx.Request], bool]] = []
        self.die_after: list[Callable[[httpx.Request], bool]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        if self.dead:
            raise Died
        for rule, error in self.raw:
            if rule(request):
                raise error
        if any(rule(request) for rule in self.garble):
            return httpx.Response(200, content=b"<html>not json</html>")
        answer = await super().handle_async_request(request)
        for rule in list(self.hang_after):
            if rule(request):
                self.hang_after.remove(rule)  # once: the undo's own calls are not held too
                await asyncio.sleep(3600)
        for rule in list(self.die_after):
            if rule(request):
                self.die_after.remove(rule)
                self.dead = True  # the process stops here: nothing it would send afterwards is sent
                raise Died
        return answer


def credential_of(method: str, engine: str = "gemini") -> Callable[[httpx.Request], bool]:
    """The live engine's own credential, not a check's probe."""
    if method == "DELETE":
        return lambda r: r.method == "DELETE" and r.url.path == f"/credentials/osprey-{engine}"
    return (
        lambda r: r.method == "POST"
        and r.url.path == "/credentials"
        and json.loads(r.content)["credential_name"] == f"osprey-{engine}"
    )


def live(path: str) -> Callable[[httpx.Request], bool]:
    return lambda r: r.url.path == path and b".check" not in r.content


@pytest.fixture
def world(tmp_path: Path) -> Scene:
    scene = Scene(tmp_path)
    scene.faults = Plants(scene.gateway.transport())
    scene.admin = scene.process()
    return scene


def faults(scene: Scene) -> Plants:
    assert isinstance(scene.faults, Plants)
    return scene.faults


async def moved(scene: Scene, key: str | None = None) -> None:
    await scene.admin.edit_engine("admin-1", "gemini", provider(NEW), SecretStr(key or scene.second))


async def no_key_goes_to_the_old_address(scene: Scene, key: str, *, restart: bool = True) -> None:
    """Everything a person or the Conduit can do next, and where the gateway sent `key`."""
    scene.gateway.sent.clear()
    await scene.call()
    if restart:
        restarted = scene.process(faulty=False, retry_seconds=3600)
        await restarted.start()
        await restarted.close()
        await scene.call()
    assert (OLD, key) not in scene.gateway.sent, f"a key typed for the new address went to the old: {scene.at()}"
    assert (NEW, key) not in scene.gateway.sent


def recorded(scene: Scene) -> str:
    return json.dumps([e.model_dump(mode="json") for e in scene.audit.entries])


def audited(scene: Scene, action: str) -> list[str]:
    return [e.outcome for e in scene.audit.entries if e.action == action]


# --- row 3: the key-storing call's answer is lost after the gateway stored it --------------------


async def test_the_answer_to_the_key_being_stored_is_lost_row_3(world: Scene) -> None:
    """Row 3. The gateway stores the new key and the answer is lost (a read timeout): the code cannot
    tell the key is held. The credential is removed, and no later call, restart or key set sends the
    new key to the old address."""
    await world.set_up()
    faults(world).lose_answer.append(credential_of("POST"))
    with pytest.raises(ModelAdminRefused):
        await moved(world)
    faults(world).lose_answer.clear()
    assert world.gateway.credential("osprey-gemini") is None, "the new key was left held"
    assert set(world.at().values()) == {OLD}
    await no_key_goes_to_the_old_address(world, world.second)
    assert world.second not in recorded(world)


# --- row 15: the process dies after the key is stored and before the record is saved -------------


async def test_a_process_killed_after_the_key_and_before_the_record_row_15(world: Scene) -> None:
    """Row 15. The process dies between `_put_key` and the final save: nothing runs to clean up. The
    record says lost (written first), the credential holds the key typed for the new address, the
    old entries are withdrawn. A restart must not remake them on that credential, and a later key
    set sends only where the record says."""
    await world.set_up()
    stop = faults(world)

    async def killed(*_a: Any, **_k: Any) -> None:
        stop.dead = True
        raise Died

    real = world.admin._reconcile
    world.admin._reconcile = killed  # type: ignore[method-assign]
    with pytest.raises(Died):
        await moved(world)
    world.admin._reconcile = real  # type: ignore[method-assign]
    stop.dead = False
    assert world.gateway.credential("osprey-gemini") == world.second, "the plant: the key is held"
    assert not world.at(), "the plant: the old entries are withdrawn"
    assert world.admin.settings.keys["gemini"].lost, "and the record says lost"

    restarted = world.process(faulty=False, retry_seconds=3600)
    await restarted.start()
    await restarted.close()
    assert world.gateway.credential("osprey-gemini") is None, "start removed the credential"
    await no_key_goes_to_the_old_address(world, world.second)

    third = a_key()
    world.gateway.providers["gemini"] = type(world.gateway.providers["gemini"])(third, frozenset({MODEL}))
    world.gateway.sent.clear()
    again = world.process(faulty=False, retry_seconds=3600)
    await again.set_key("admin-1", "gemini", SecretStr(third))
    await world.call()
    assert world.addresses_reached_by(third) == {OLD}
    assert world.second not in {k for _, k in world.gateway.sent}


# --- rows 16 and 39: the gateway will not remove the new key -------------------------------------


async def test_a_key_the_gateway_will_not_remove_is_never_given_an_entry_rows_16_and_39(
    world: Scene,
) -> None:
    """Rows 16 and 39. A moved edit fails once its key is held, and the gateway then refuses to
    remove it: the credential may hold a key typed for the new address while the record gives the
    old. The engine is withheld by **every** later reconcile: a second engine added, a restart, the
    retry. None rebuilds an old-address entry on it, so `(OLD, new key)` is never sent. Once the
    gateway removes the key the entries come back, with no key, and entering a key repairs it."""
    await world.set_up()
    armed: list[bool] = []

    def refuse_the_entries(r: httpx.Request) -> bool:
        if live("/model/new")(r):
            armed.append(True)
            return True
        return False

    faults(world).refuse.append(refuse_the_entries)
    faults(world).refuse.append(lambda r: bool(armed) and credential_of("DELETE")(r))
    with pytest.raises(ModelAdminRefused) as raised:
        await moved(world)
    assert "may still be held" in raised.value.words, "said in words"
    assert world.second not in raised.value.words
    assert world.gateway.credential("osprey-gemini") == world.second, "the stand-in refused"
    assert not any(i.startswith("osprey-gemini-") for i in world.gateway.stored_ids())
    assert world.admin.routes().engines["gemini"].key_present is False
    assert "may still be held" in " ".join(audited(world, "engine_edited"))
    assert world.second not in recorded(world)
    faults(world).refuse[0] = lambda r: False  # the entries can be made again; the removal cannot

    # another engine is added: its reconcile runs over every engine, this one included
    await world.add(
        provider(OLD, name="openai", roles={"extraction": "gpt-4.1-mini"}),
        a_key(),
        frozenset({"gpt-4.1-mini"}),
    )
    assert not any(i.startswith("osprey-gemini-") for i in world.gateway.stored_ids()), (
        "another engine's change rebuilt an entry on a credential that may hold the new key"
    )
    # a restart, and the background retry
    restarted = world.process(retry_seconds=3600)
    await restarted.start()
    assert await restarted._start_once() is False, "the retry is not done while it is held"
    await restarted.close()
    assert not any(i.startswith("osprey-gemini-") for i in world.gateway.stored_ids())
    world.gateway.sent.clear()
    await world.call()
    assert (OLD, world.second) not in world.gateway.sent
    assert restarted.routes().engines["gemini"].key_present is False

    # the gateway removes it: the entries come back, with no key behind them
    faults(world).refuse.clear()
    healed = world.process(faulty=False, retry_seconds=3600)
    await healed.start()
    await healed.close()
    assert world.gateway.credential("osprey-gemini") is None
    assert any(i.startswith("osprey-gemini-") for i in world.gateway.stored_ids())
    assert healed.routes().engines["gemini"].key_present is False, "still to be entered again"
    await world.call()
    assert (OLD, world.second) not in world.gateway.sent


# --- row 17: any way out once the key is stored --------------------------------------------------


@pytest.mark.parametrize("how", ["a cancellation", "a JSON error", "another transport error"])
async def test_whatever_leaves_the_edit_once_the_key_is_stored_removes_it_row_17(
    world: Scene, how: str
) -> None:
    """Row 17. After the key is stored, the edit is left by a cancellation, by a gateway answer that
    is not JSON, or by a stream cut short (`asyncio.IncompleteReadError`, none of them a refusal or an `OSError`). Each takes
    the same road out: the credential is removed before anything is made on it, shielded from the
    cancellation, so no later call, restart or key set sends the key to the old address."""
    await world.set_up()
    stop = faults(world)
    if how == "a cancellation":
        reached = asyncio.Event()
        stop.hang_after.append(lambda r: live("/key/update")(r) and not reached.is_set() and not reached.set())
        task = asyncio.ensure_future(moved(world))
        await asyncio.wait_for(reached.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        stop.hang_after.clear()
        assert any("interrupted" in o for o in audited(world, "engine_edited")), audited(
            world, "engine_edited"
        )
    else:
        once: list[bool] = []

        def first(r: httpx.Request) -> bool:
            if r.url.path == "/key/list" and not once:
                once.append(True)
                return True
            return False

        if how == "a JSON error":
            stop.garble.append(first)
        else:
            stop.raw.append((first, asyncio.IncompleteReadError(b"", 10)))  # a stream cut short: not an OSError
        with pytest.raises(ModelAdminRefused):
            await moved(world)
    assert world.gateway.credential("osprey-gemini") is None, "the new key was left held"
    assert world.admin.key_state("gemini") == "lost"
    assert world.admin.routes().engines["gemini"].key_present is False
    await no_key_goes_to_the_old_address(world, world.second)
    assert world.second not in recorded(world)


# --- row 28: the SE5 case on this branch's edit path ---------------------------------------------


async def test_an_entry_at_the_new_address_that_survives_a_refused_put_back_row_28(
    world: Scene,
) -> None:
    """Row 28. A moved edit fails after entries are made at the new address; the put-back's removals
    are refused, so an entry at the **new** address survives. A later key set stores a key under
    the engine's credential, and the surviving entry would send it to the new address. Start and
    the key set both compare every entry's address with the record (SE5's check, kept): the key is
    not taken while the entry stands, and once the gateway removes it the key reaches only the
    address the record gives."""
    await world.set_up()
    armed: list[bool] = []

    def refuse_the_update_then_every_removal(r: httpx.Request) -> bool:
        if r.url.path == "/key/update":
            armed.append(True)
        return bool(armed) and live("/model/delete")(r)

    faults(world).refuse.append(refuse_the_update_then_every_removal)
    faults(world).refuse.append(lambda r: r.url.path == "/key/update" and b".check" not in r.content)
    with pytest.raises(ModelAdminRefused):
        await moved(world)
    assert NEW in world.at().values(), "the plant: an entry survives at the new address"
    faults(world).refuse.pop()  # the engine's key update works again; the removals do not

    third = a_key()
    world.gateway.providers["gemini"] = type(world.gateway.providers["gemini"])(third, frozenset({MODEL}))
    with pytest.raises(ModelAdminRefused):
        await world.admin.set_key("admin-1", "gemini", SecretStr(third))
    assert world.gateway.credential("osprey-gemini") != third, "the key was taken beside the entry"
    world.gateway.sent.clear()
    await world.call()
    assert third not in {k for _, k in world.gateway.sent}

    faults(world).refuse.clear()
    await world.admin.set_key("admin-1", "gemini", SecretStr(third))
    await world.call()
    assert world.addresses_reached_by(third) == {OLD}
    assert set(world.at().values()) == {OLD}


# --- rows 29 and 30: a record that cannot be saved, an exception, a cancellation, first ---------


@pytest.mark.parametrize("how", ["the record cannot be saved", "an exception nobody named", "a cancellation"])
async def test_a_moved_edit_that_stops_before_it_wrote_anything_leaves_the_key_rows_29_and_30(
    world: Scene, how: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows 29 and 30. The record of intent is written before the credential is touched, so a first
    save that fails (29) leaves the key set and held, and an exception nobody named or a
    cancellation just after it (30) gives the record back: the engine is offered still with its key,
    and the words say nothing was changed, never that anything was "put back"."""
    await world.set_up()
    before = world.at()
    reached = asyncio.Event()
    if how == "the record cannot be saved":

        def full(*_a: Any, **_k: Any) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(world.admin._file, "save", full)
    else:

        async def stops(*_a: Any, **_k: Any) -> None:
            if how == "a cancellation":
                reached.set()
                await asyncio.sleep(3600)
            raise RuntimeError("a garbled answer")

        monkeypatch.setattr(world.admin, "_withdraw_entries", stops)
    if how == "a cancellation":
        task = asyncio.ensure_future(moved(world))
        await asyncio.wait_for(reached.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        said = audited(world, "engine_edited")[-1].lower()
    else:
        with pytest.raises(ModelAdminRefused) as raised:
            await moved(world)
        said = raised.value.words.lower()
        assert audited(world, "engine_edited")[-1].lower().startswith("refused")
    monkeypatch.undo()
    assert "put back" not in said or "was not put back" in said, said
    if how != "the record cannot be saved":
        assert "nothing had been changed" in said, said
    assert world.gateway.credential("osprey-gemini") == world.first, "the old key is untouched"
    assert world.at() == before
    assert world.admin.key_state("gemini") == "set", "the intent was given back"
    assert world.admin.routes().engines["gemini"].key_present is True
    assert not audited(world, "key_removed")
    assert world.first not in recorded(world) and world.second not in recorded(world)


# --- row 31: the removal was saved and unsaid ----------------------------------------------------


async def test_a_not_saved_answer_says_when_the_key_removal_was_saved_row_31(world: Scene) -> None:
    """Row 31. A moved edit's last save fails: the engine keeps its address, and its key (replaced,
    then removed by the clean-up) is lost, which is saved. The answer says so, and a `key_removed`
    audit says it without the key."""
    await world.set_up()
    real = world.admin._file.save
    saves: list[int] = []

    def second_fails(settings: Any) -> None:
        saves.append(1)
        if len(saves) == 2:
            raise OSError(28, "No space left on device")
        real(settings)

    world.admin._file.save = second_fails  # type: ignore[method-assign]
    with pytest.raises(ModelAdminRefused) as raised:
        await moved(world)
    world.admin._file.save = real  # type: ignore[method-assign]
    words = raised.value.words.lower()
    assert "not saved" in words
    assert "key was removed" in words and "removal is saved" in words and "enter it again" in words
    assert audited(world, "key_removed"), "audited"
    assert world.first not in recorded(world) and world.second not in recorded(world)
    assert world.admin.key_state("gemini") == "lost"
    assert world.gateway.credential("osprey-gemini") is None


# --- rows 32 and 33: a rotation ------------------------------------------------------------------


async def test_a_rotation_that_cannot_record_its_intent_removes_nothing_rows_32_and_33(
    world: Scene,
) -> None:
    """Row 32. A rotation's record of intent cannot be saved: nothing is deleted, the key is still
    set and held, offered, and the answer is "not saved" (no credential sat unrecorded)."""
    await world.set_up()
    real = world.admin._file.save

    def full(*_a: Any, **_k: Any) -> None:
        raise OSError(28, "No space left on device")

    world.admin._file.save = full  # type: ignore[method-assign]
    with pytest.raises(ModelAdminRefused) as raised:
        await world.admin.set_key("admin-1", "gemini", SecretStr(world.second))
    world.admin._file.save = real  # type: ignore[method-assign]
    assert "not saved" in raised.value.words.lower()
    assert world.gateway.credential("osprey-gemini") == world.first
    assert world.admin.key_state("gemini") == "set"
    assert world.admin.routes().engines["gemini"].key_present is True


@pytest.mark.parametrize("how", ["an exception nobody named", "a cancellation"])
async def test_a_rotation_stopped_after_the_old_key_was_removed_says_it_rows_32_and_33(
    world: Scene, how: str
) -> None:
    """Row 33. The old key is removed and the store of the new one raises something nobody named,
    or the task is cancelled once the removal landed. The record says lost (written first), the
    engine is offered to no analyst, the answer or the audit says the key was removed and the
    removal saved (with a `key_removed` audit), and "put back" is said only because the gateway
    was: no credential, entries as the record says."""
    await world.set_up()
    stop = faults(world)
    if how == "an exception nobody named":
        stop.raw.append((lambda r: credential_of("POST")(r), RuntimeError("a garbled answer")))
        with pytest.raises(ModelAdminRefused) as raised:
            await world.admin.set_key("admin-1", "gemini", SecretStr(world.second))
        said = raised.value.words.lower()
        assert "not saved" in said
    else:
        stop.hang_after.append(credential_of("DELETE"))
        task = asyncio.ensure_future(
            world.admin.set_key("admin-1", "gemini", SecretStr(world.second))
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        said = " ".join(e.outcome for e in world.audit.entries).lower()
    stop.raw.clear()
    stop.hang_after.clear()
    assert "interrupted" in said or "not saved" in said
    assert "key was removed" in said and "enter it again" in said, said
    assert audited(world, "key_removed"), "a key_removed audit"
    assert world.admin.key_state("gemini") == "lost", "the record is not 'set' over no credential"
    assert world.admin.routes().engines["gemini"].key_present is False
    assert world.gateway.credential("osprey-gemini") is None
    if "put back" in said:
        assert "was not put back" not in said
    assert world.first not in recorded(world) and world.second not in recorded(world)


# --- row 34: remove a key ------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["the record cannot be saved", "a cancellation"])
async def test_a_removed_key_whose_record_is_not_saved_is_lost_not_set_row_34(
    world: Scene, how: str
) -> None:
    """Row 34. The credential is deleted and then the save fails, or the task is cancelled before
    the save. The record of intent was written first, so the file never says "set" over no
    credential, the engine is offered to no analyst, and the answer or audit says the key was
    removed (and the removal saved)."""
    await world.set_up()
    if how == "the record cannot be saved":
        real = world.admin._file.save
        saves: list[int] = []

        def second_fails(settings: Any) -> None:
            saves.append(1)
            if len(saves) == 2:
                raise OSError(28, "No space left on device")
            real(settings)

        world.admin._file.save = second_fails  # type: ignore[method-assign]
        with pytest.raises(ModelAdminRefused) as raised:
            await world.admin.remove_key("admin-1", "gemini")
        world.admin._file.save = real  # type: ignore[method-assign]
        assert "not saved" in raised.value.words.lower()
        assert "key was removed" in raised.value.words.lower()
    else:
        faults(world).hang_after.append(credential_of("DELETE"))
        task = asyncio.ensure_future(world.admin.remove_key("admin-1", "gemini"))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        faults(world).hang_after.clear()
        assert any("interrupted" in o for o in audited(world, "key_removed"))
    assert world.gateway.credential("osprey-gemini") is None
    assert world.admin.key_state("gemini") == "lost", "never 'set' over no credential"
    assert world.admin.routes().engines["gemini"].key_present is False
    assert audited(world, "key_removed")


async def test_a_removal_the_gateway_refuses_leaves_the_key_set_and_offered_row_34(
    world: Scene,
) -> None:
    """Row 34's other end. The gateway *answers* that it refuses the removal: the credential is held
    as it was, so the record of intent is given back and the engine is offered still."""
    await world.set_up()
    faults(world).refuse.append(credential_of("DELETE"))
    with pytest.raises(ModelAdminRefused):
        await world.admin.remove_key("admin-1", "gemini")
    faults(world).refuse.clear()
    assert world.gateway.credential("osprey-gemini") == world.first
    assert world.admin.key_state("gemini") == "set"
    assert world.admin.routes().engines["gemini"].key_present is True


# --- row 35: remove an engine --------------------------------------------------------------------


async def test_a_removed_engine_whose_record_is_not_saved_has_no_key_row_35(world: Scene) -> None:
    """Row 35. The engine's credential is deleted and then the save of the proposal fails: the file
    keeps the engine, with its key lost (written first), and it is offered to no analyst."""
    await world.set_up()
    real = world.admin._file.save
    saves: list[int] = []

    def second_fails(settings: Any) -> None:
        saves.append(1)
        if len(saves) == 2:
            raise OSError(28, "No space left on device")
        real(settings)

    world.admin._file.save = second_fails  # type: ignore[method-assign]
    with pytest.raises(ModelAdminRefused) as raised:
        await world.admin.remove_engine("admin-1", "gemini")
    world.admin._file.save = real  # type: ignore[method-assign]
    assert "not saved" in raised.value.words.lower()
    assert "key was removed" in raised.value.words.lower()
    assert [p.name for p in world.admin.settings.providers] == ["gemini"]
    assert world.admin.key_state("gemini") == "lost"
    assert world.admin.routes().engines["gemini"].key_present is False
    assert world.gateway.credential("osprey-gemini") is None
    assert audited(world, "key_removed")


# --- row 36: start-up after a kill between the delete and the save --------------------------------


@pytest.mark.parametrize("how", ["remove_key", "remove_engine"])
async def test_start_after_a_kill_between_the_delete_and_the_save_row_36(
    world: Scene, how: str
) -> None:
    """Row 36. The process is killed after the credential was deleted and before the record was
    saved. On restart the engine is **not** offered as set with no credential: the record of
    intent says lost, which start reads (it reads no credential)."""
    await world.set_up()
    faults(world).die_after.append(credential_of("DELETE"))
    call = (
        world.admin.remove_key("admin-1", "gemini")
        if how == "remove_key"
        else world.admin.remove_engine("admin-1", "gemini")
    )
    with pytest.raises(Died):
        await call
    faults(world).dead = False
    assert world.gateway.credential("osprey-gemini") is None, "the plant: the credential is gone"
    restarted = world.process(faulty=False, retry_seconds=3600)
    await restarted.start()
    await restarted.close()
    assert restarted.key_state("gemini") == "lost"
    assert restarted.routes().engines["gemini"].key_present is False


# --- row 37: start-up and the unpriced rebuild -----------------------------------------------------


async def test_an_engine_whose_unpriced_rebuild_did_not_finish_is_not_offered_row_37(
    world: Scene,
) -> None:
    """Row 37. An entry made before ADR-135 Amendment 3 is not priced a unit a token, so start deletes
    and makes it again; the gateway refuses the new entry. The engine is marked and offered to no
    analyst while the entries are missing (never a log line alone), and offered again once the retry
    makes them."""
    await world.set_up()
    for model_id in world.gateway.stored_ids():
        world.gateway._db[model_id].sealed["input_cost_per_token"] = _seal(
            world.gateway.salt_key, "0"
        )
    faults(world).refuse.append(live("/model/new"))
    restarted = world.process(retry_seconds=3600)
    await restarted.start()
    assert not world.at(), "the plant: the entries were deleted and not made again"
    assert restarted.routes().engines["gemini"].key_present is False
    assert await restarted._start_once() is False

    faults(world).refuse.clear()
    assert await restarted._start_once() is True
    await restarted.close()
    assert world.at()
    assert restarted.routes().engines["gemini"].key_present is True
    assert restarted.key_state("gemini") == "set"


# --- row 38: a reconcile clears only what it made whole ------------------------------------------


async def test_another_engines_change_does_not_offer_an_engine_with_no_key_row_38(
    world: Scene,
) -> None:
    """Row 38. An engine's credential was deleted and its record save failed (marked lost, not set);
    a later change to **another** engine reconciles successfully and used to clear every mark. This
    engine is still not offered, and its entries are the record's."""
    await world.set_up()
    real = world.admin._file.save
    saves: list[int] = []

    def second_fails(settings: Any) -> None:
        saves.append(1)
        if len(saves) == 2:
            raise OSError(28, "No space left on device")
        real(settings)

    world.admin._file.save = second_fails  # type: ignore[method-assign]
    with pytest.raises(ModelAdminRefused):
        await world.admin.remove_key("admin-1", "gemini")
    world.admin._file.save = real  # type: ignore[method-assign]
    await world.add(
        provider(OLD, name="openai", roles={"extraction": "gpt-4.1-mini"}),
        a_key(),
        frozenset({"gpt-4.1-mini"}),
    )
    assert world.admin.routes().engines["openai"].key_present is True
    assert world.admin.key_state("gemini") == "lost"
    assert world.admin.routes().engines["gemini"].key_present is False
    world.gateway.sent.clear()
    await world.call()
    assert {k for _, k in world.gateway.sent} <= {None}
