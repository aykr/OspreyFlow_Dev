"""*Admin › Models*: every point where a key or its credential exists and a later step can fail or
be interrupted, held as **rows** of `process/lanes/v062/slices/AD1a_KEY_PATHS_TABLE.md` (the owner's
rule, 20 November 2026: a fault that can send a key to an address it was not given for, show it
back, log it or audit it is never accepted; one that leaves an engine unavailable or the words wrong
is fixed here).

**One design, held by these cases (the owner's ruling on the round-6 table, 20 November 2026).**

1. *A note of intent is saved before any credential is deleted or stored and cleared when the change
   is complete* (`ModelSettings.intents`, in the models file, so every replica and every restart
   sees it). Places: an edit moved or not, a rotation, remove key, remove engine, cancel a check,
   a check's own credential, a check's probe. No way out of a change (a cancellation, a process
   that stops, a record save that fails, an answer that is lost) leaves "set" over a credential
   nobody can account for.
2. *A note outstanding is a property of the state.* Every reconcile, and the undo, first settles
   it (the credential removed, the key recorded lost, the note cleared); an engine whose credential
   the gateway will not remove is given no entry until it does (`ModelAdmin._reconcile`'s
   *withheld*). No caller can forget it.
3. *One decision for the words and the mark* across a refusal, an error, a cancellation and any
   other exception: "put back" only when the entries **and** the credential were (a rotation's or a
   removal's undo removes the credential and never restores it, so it never says so); the key's
   removal said, with a `key_removed` audit, when it was saved; a key the gateway would not remove
   said held.
4. *Start-up* marks unavailable every engine with a note outstanding and settles it. **It reads no
   credential** (`GET /credentials` answers with two characters at each end of a key, so the
   Conduit never asks: `credential_reads` stays 0): the note is what start reads. It removes a
   check's probe credential whether or not there is a models file.
5. *A key is stored only where no entry disagrees with the record*: `set_key`, an edit that carries
   a key and a check for a new engine each withdraw such entries first, and a refused withdrawal
   refuses the key. A moved edit withdraws the engine's old entries **before** anything is
   recorded or removed, so a refused withdrawal leaves the old key working (row 40).

**Each case plants its fault at the real call site** (the stand-in gateway, refusing as the pinned
one was measured to, with a transport over it that refuses, lets an answer be lost, garbles one,
raises raw, hangs, or stops the process where a test says), was red on the code before the fix
(`plants_key_paths_run.txt` beside `OWED.md`), and names its row. Every key is made at run time.

**Which test fails if each row's behaviour is violated (rule 12)**

row 3 `..._row_3`, row 15 `..._row_15`, row 16 and 39 `..._row_16_and_39`, row 17 `..._row_17`,
row 28 `..._row_28`, rows 29 and 30 `..._rows_29_and_30`, row 31 `..._row_31`, rows 32 and 33
`..._rows_32_and_33`, row 34 `..._row_34`, row 35 `..._row_35`, row 36 `..._row_36`,
row 37 `..._row_37`, row 38 `..._row_38`, row 40 `..._row_40`, row 41 `..._row_41`, row 21
`..._row_21`, and the put-back words (rows 30, 33, 34) `..._put_back_words`.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from services.api.model_admin import ModelAdminRefused

from adapters.model_litellm.stand_in import _seal
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
    return lambda r: (
        r.method == "POST"
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
    await scene.admin.edit_engine(
        "admin-1", "gemini", provider(NEW), SecretStr(key or scene.second)
    )


async def no_key_goes_to_the_old_address(scene: Scene, key: str, *, restart: bool = True) -> None:
    """Everything a person or the Conduit can do next, and where the gateway sent `key`."""
    scene.gateway.sent.clear()
    await scene.call()
    if restart:
        restarted = scene.process(faulty=False, retry_seconds=3600)
        await restarted.start()
        await restarted.close()
        await scene.call()
    assert (OLD, key) not in scene.gateway.sent, (
        f"a key typed for the new address went to the old: {scene.at()}"
    )
    assert (NEW, key) not in scene.gateway.sent


def recorded(scene: Scene) -> str:
    return json.dumps([e.model_dump(mode="json") for e in scene.audit.entries])


def audited(scene: Scene, action: str) -> list[str]:
    return [e.outcome for e in scene.audit.entries if e.action == action]


def says_put_back(words: str) -> bool:
    """Whether `words` say the gateway **was** put back (a "was not"/"could not be" is no claim)."""
    return "put back" in re.sub(r"not (be )?put back", "", words.lower())


def everything_said(scene: Scene, answer: str = "") -> str:
    """The answer and every audit outcome: what a person and the record were told."""
    return answer + " " + " ".join(e.outcome for e in scene.audit.entries)


# --- row 3: the key-storing call's answer is lost after the gateway stored it --------------------


async def test_the_answer_to_the_key_being_stored_is_lost_row_3(world: Scene) -> None:
    """Row 3. The gateway stores the new key and the answer is lost (a read timeout): the code
    cannot
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
    assert "gemini" in world.admin.settings.intents, "and the note of intent is outstanding"
    assert world.admin.key_state("gemini") == "lost", "so no replica offers it on the old record"

    restarted = world.process(faulty=False, retry_seconds=3600)
    await restarted.start()
    await restarted.close()
    assert world.gateway.credential("osprey-gemini") is None, "start removed the credential"
    await no_key_goes_to_the_old_address(world, world.second)

    third = a_key()
    world.gateway.providers["gemini"] = type(world.gateway.providers["gemini"])(
        third, frozenset({MODEL})
    )
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
    is not JSON, or by a stream cut short (`asyncio.IncompleteReadError`): none a refusal or an
    `OSError`. Each takes
    the same road out: the credential is removed before anything is made on it, shielded from the
    cancellation, so no later call, restart or key set sends the key to the old address."""
    await world.set_up()
    stop = faults(world)
    if how == "a cancellation":
        reached = asyncio.Event()
        stop.hang_after.append(
            lambda r: live("/key/update")(r) and not reached.is_set() and not reached.set()
        )
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
            stop.raw.append(
                (first, asyncio.IncompleteReadError(b"", 10))
            )  # a stream cut short: not an OSError
        with pytest.raises(ModelAdminRefused):
            await moved(world)
    assert world.gateway.credential("osprey-gemini") is None, "the new key was left held"
    assert world.admin.key_state("gemini") == "lost"
    assert world.admin.routes().engines["gemini"].key_present is False
    # the undo removed the key and restored nothing of it: it never says the gateway was put back
    assert not says_put_back(everything_said(world)), everything_said(world)
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
    faults(world).refuse.append(
        lambda r: r.url.path == "/key/update" and b".check" not in r.content
    )
    with pytest.raises(ModelAdminRefused):
        await moved(world)
    assert NEW in world.at().values(), "the plant: an entry survives at the new address"
    faults(world).refuse.pop()  # the engine's key update works again; the removals do not

    third = a_key()
    world.gateway.providers["gemini"] = type(world.gateway.providers["gemini"])(
        third, frozenset({MODEL})
    )
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


@pytest.mark.parametrize(
    "how", ["the record cannot be saved", "an exception nobody named", "a cancellation"]
)
async def test_a_moved_edit_that_stops_before_it_wrote_anything_leaves_the_key_rows_29_and_30(
    world: Scene, how: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows 29 and 30. The note of intent is written before the credential is touched, so a first
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

    def the_move_fails(settings: Any) -> None:
        if settings.providers[0].api_base == NEW:  # the record that gives the engine its move
            raise OSError(28, "No space left on device")
        real(settings)

    world.admin._file.save = the_move_fails  # type: ignore[method-assign]
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
    """Row 32. A rotation's note of intent cannot be saved: nothing is deleted, the key is still
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
    assert not says_put_back(everything_said(world, said)), everything_said(world, said)
    assert world.first not in recorded(world) and world.second not in recorded(world)


# --- row 34: remove a key ------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["the record cannot be saved", "a cancellation"])
async def test_a_removed_key_whose_record_is_not_saved_is_lost_not_set_row_34(
    world: Scene, how: str
) -> None:
    """Row 34. The credential is deleted and then the save fails, or the task is cancelled before
    the save. The note of intent was written first, so the file never says "set" over no
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
    assert not says_put_back(everything_said(world)), everything_said(world)


async def test_a_removal_the_gateway_refuses_leaves_the_key_set_and_offered_row_34(
    world: Scene,
) -> None:
    """Row 34's other end. The gateway *answers* that it refuses the removal: the credential is held
    as it was, so the note of intent is given back and the engine is offered still."""
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
    intent is outstanding, which start reads (it reads no credential)."""
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


# --- row 37: start-up and the unpriced rebuild ----------------------------------------------


async def test_an_engine_whose_unpriced_rebuild_did_not_finish_is_not_offered_row_37(
    world: Scene,
) -> None:
    """Row 37. An entry made before ADR-135 Amendment 3 is not priced a unit a token, so start
    deletes
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


# --- row 28 again, on the edit path: a key typed for the old address, an entry at the new ---------


async def test_an_edit_that_keeps_the_address_and_carries_a_key_withdraws_entries_first_row_28(
    world: Scene,
) -> None:
    """Row 28, on `edit_engine` and not only on `set_key`. A moved edit fails after entries are made
    at the NEW address and every removal is refused afterwards, so an entry at NEW survives and the
    record says OLD. An edit that **keeps OLD and carries a key** stored that key under the engine's
    credential with no withdrawal first (`set_key` does it), so the surviving entry sent a key typed
    for OLD to NEW, and the record was settled to "set" before the reconcile that failed. The key is
    now refused while the entry stands; `(NEW, the key)` is never sent, and once the gateway removes
    the entry the key reaches OLD alone."""
    await world.set_up()
    armed: list[bool] = []

    def refuse_the_update_then_every_removal(r: httpx.Request) -> bool:
        if r.url.path == "/key/update":
            armed.append(True)
        return bool(armed) and live("/model/delete")(r)

    faults(world).refuse.append(refuse_the_update_then_every_removal)
    faults(world).refuse.append(
        lambda r: r.url.path == "/key/update" and b".check" not in r.content
    )
    with pytest.raises(ModelAdminRefused):
        await moved(world)
    assert NEW in world.at().values(), "the plant: an entry survives at the new address"
    faults(world).refuse.pop()  # the engine's key update works again; the removals do not

    third = a_key()
    world.gateway.providers["gemini"] = type(world.gateway.providers["gemini"])(
        third, frozenset({MODEL})
    )
    with pytest.raises(ModelAdminRefused):
        await world.admin.edit_engine("admin-1", "gemini", provider(OLD), SecretStr(third))
    assert world.gateway.credential("osprey-gemini") != third, "the key was taken beside the entry"
    world.gateway.sent.clear()
    await world.call()
    assert (NEW, third) not in world.gateway.sent
    assert third not in {k for _, k in world.gateway.sent}, "the key was sent somewhere"
    # another replica reads the file: it must not offer the engine on the strength of a key
    other = world.process(faulty=False, retry_seconds=3600)
    assert other.routes().engines["gemini"].key_present is False

    faults(world).refuse.clear()
    await world.admin.edit_engine("admin-1", "gemini", provider(OLD), SecretStr(third))
    await world.call()
    assert world.addresses_reached_by(third) == {OLD}
    assert set(world.at().values()) == {OLD}


async def test_a_check_for_a_new_engine_withdraws_a_stray_entry_before_its_key_row_28(
    world: Scene,
) -> None:
    """Row 28, the other caller that stores a key. An entry for an engine the record does not hold
    (left by an interrupted removal) names the credential a new engine of that name will have, and
    sends whatever is stored there to its own address. A check for such an engine withdraws it
    first, and a removal the gateway refuses refuses the key: nothing is stored beside it."""
    await world.set_up()
    stray = provider(NEW, name="openai", roles={"extraction": "gpt-4.1-mini"})
    await world.admin._gateway.add_entry(stray, "gpt-4.1-mini")
    assert "osprey-openai-gpt-4.1-mini" in world.gateway.stored_ids(), "the plant: a stray entry"
    key = a_key()
    world.gateway.providers = {
        **world.gateway.providers,
        "openai": type(world.gateway.providers["gemini"])(key, frozenset({"gpt-4.1-mini"})),
    }
    engine = provider(OLD, name="openai", roles={"extraction": "gpt-4.1-mini"})

    faults(world).refuse.append(live("/model/delete"))
    with pytest.raises(ModelAdminRefused):
        await world.admin.check("admin-1", engine, SecretStr(key))
    assert world.gateway.credential("osprey-openai") is None, "the key was stored beside the stray"
    faults(world).refuse.clear()

    checked = await world.admin.check("admin-1", engine, SecretStr(key))
    assert checked.ok
    assert "osprey-openai-gpt-4.1-mini" not in world.gateway.stored_ids(), "withdrawn first"


# --- row 40: a refused withdrawal must leave the old key working ----------------------------------


@pytest.mark.parametrize("how", ["the gateway refuses it", "the answer is lost after it landed"])
async def test_a_moved_edit_whose_withdrawal_fails_leaves_the_old_key_working_row_40(
    world: Scene, how: str
) -> None:
    """Row 40. A moved edit saved its intent (key lost) before it withdrew the old entries, and
    every reconcile removes a lost engine's credential first: so a withdrawal the gateway refused,
    before any new key was sent, made the undo delete the engine's **working old key**. The old
    entries are withdrawn first, with nothing recorded and nothing removed; a failed withdrawal
    leaves the old key held and set. (The rows 29 and 30 case stubs the withdrawal with a call that
    sends no write, so it covers nothing of this.)"""
    await world.set_up()
    if how == "the gateway refuses it":
        faults(world).refuse.append(live("/model/delete"))
    else:
        faults(world).lose_answer.append(live("/model/delete"))
    with pytest.raises(ModelAdminRefused) as raised:
        await moved(world)
    faults(world).refuse.clear()
    faults(world).lose_answer.clear()
    assert world.gateway.credential("osprey-gemini") == world.first, "the old key was deleted"
    assert world.admin.settings.keys["gemini"].lost is False
    assert world.admin.key_state("gemini") in ("set", "lost")
    assert "was removed by this change" not in raised.value.words, raised.value.words
    assert not audited(world, "key_removed")
    assert world.second not in recorded(world) and world.first not in recorded(world)

    healed = world.process(faulty=False, retry_seconds=3600)
    await healed.start()
    await healed.close()
    assert world.gateway.credential("osprey-gemini") == world.first
    assert healed.key_state("gemini") == "set"
    assert healed.routes().engines["gemini"].key_present is True
    world.gateway.sent.clear()
    await world.call()
    assert world.addresses_reached_by(world.first) == {OLD}


# --- row 36: the note of intent is what start reads; it never reads a credential ------------------


async def test_start_marks_an_engine_with_a_note_outstanding_and_reads_no_credential_row_36(
    world: Scene,
) -> None:
    """Row 36, the owner's ruling (20 November 2026): a note of intent is saved before a credential
    is deleted and cleared when the change is complete; start-up marks unavailable every engine
    with a note outstanding. It lists no credential, because the listing returns part of each key.
    The process stops after the credential was deleted and before the record was saved; the
    restart, with the gateway refusing every credential removal, still does not offer the engine,
    and once the gateway lets it, settles the note."""
    await world.set_up()
    faults(world).die_after.append(credential_of("DELETE"))
    with pytest.raises(Died):
        await world.admin.remove_key("admin-1", "gemini")
    faults(world).dead = False
    assert world.gateway.credential("osprey-gemini") is None, "the plant: the credential is gone"
    assert set(world.admin.settings.intents) == {"gemini"}, "the note was saved before the delete"

    refusing = Plants(world.gateway.transport())
    refusing.refuse.append(
        lambda r: r.method == "DELETE" and r.url.path.startswith("/credentials/")
    )
    world.faults = refusing
    restarted = world.process(retry_seconds=3600)
    await restarted.start()
    assert "gemini" in restarted._unavailable, "start marked it before it settled anything"
    assert restarted.key_state("gemini") == "lost"
    assert restarted.routes().engines["gemini"].key_present is False
    assert await restarted._start_once() is False, "the note is outstanding: retry"

    refusing.refuse.clear()
    assert await restarted._start_once() is True
    await restarted.close()
    assert not restarted.settings.intents, "settled, so cleared"
    assert restarted.key_state("gemini") == "lost"
    assert restarted.routes().engines["gemini"].key_present is False
    assert world.gateway.credential_reads == 0, "a credential was listed"


# --- row 41: cancel a check ----------------------------------------------------------------------


@pytest.mark.parametrize("how", ["the record cannot be saved", "the process is killed"])
async def test_a_cancelled_check_whose_removal_is_not_saved_cannot_be_added_row_41(
    world: Scene, how: str
) -> None:
    """Row 41. `cancel_check` deleted the check's credential before it saved the record that removes
    the check, with no note of intent first. A save that failed, or a process killed between, left
    the check `passed` and its key gone: **Add** then recorded a key as set and offered an engine
    with no credential behind it. The note is saved first, so the next change or start settles it:
    the check goes with its key, and Add is refused."""
    await world.set_up()
    key = a_key()
    world.gateway.providers = {
        **world.gateway.providers,
        "openai": type(world.gateway.providers["gemini"])(key, frozenset({"gpt-4.1-mini"})),
    }
    engine = provider(OLD, name="openai", roles={"extraction": "gpt-4.1-mini"})
    checked = await world.admin.check("admin-1", engine, SecretStr(key))
    assert checked.ok and checked.check
    check_id = checked.check
    real = world.admin._file.save
    if how == "the record cannot be saved":

        def full_for_the_removal(settings: Any) -> None:
            if check_id not in settings.checks:  # the record that takes the check away
                raise OSError(28, "No space left on device")
            real(settings)

        world.admin._file.save = full_for_the_removal  # type: ignore[method-assign]
        with pytest.raises(ModelAdminRefused):
            await world.admin.cancel_check("admin-1", check_id)
        world.admin._file.save = real  # type: ignore[method-assign]
        again = world.admin
    else:
        faults(world).die_after.append(credential_of("DELETE", "openai"))
        with pytest.raises(Died):
            await world.admin.cancel_check("admin-1", check_id)
        faults(world).dead = False
        again = world.process(faulty=False, retry_seconds=3600)
        await again.start()
        await again.close()
    assert world.gateway.credential("osprey-openai") is None, "the plant: its key is gone"
    with pytest.raises(ModelAdminRefused):
        await again.add_checked("admin-1", check_id)
    assert "openai" not in again.routes().engines, "an engine was offered with no key behind it"
    assert all(p.name != "openai" for p in again.settings.providers)
    assert not again.settings.intents


# --- row 21: a probe credential left before any models file exists --------------------------------


async def test_a_probe_credential_left_before_any_models_file_is_removed_at_start_row_21(
    tmp_path: Path,
) -> None:
    """Row 21. An edit made before any models file exists runs its check, which puts the typed key
    into `osprey-<engine>.check` (no note can be written without taking `osprey.yaml`'s place); a
    process stopped there left the credential, and every later start returned before the probe
    sweep, so the key stayed until someone edited that engine again. Start removes every probe
    credential, models file or none."""
    scene = Scene(tmp_path)
    scene.faults = Plants(scene.gateway.transport())
    declared = [provider(OLD)]
    scene.admin = scene.process(declared=declared)
    probe = "osprey-gemini.check"
    faults(scene).die_after.append(
        lambda r: (
            r.method == "POST"
            and r.url.path == "/credentials"
            and json.loads(r.content)["credential_name"] == probe
        )
    )
    with pytest.raises(Died):
        await scene.admin.edit_engine("admin-1", "gemini", provider(NEW), SecretStr(scene.second))
    faults(scene).dead = False
    assert scene.gateway.credential(probe) == scene.second, "the plant: the probe holds the key"
    assert not (scene.folder / "models.yaml").exists(), "the plant: no models file"

    restarted = scene.process(faulty=False, declared=declared, retry_seconds=3600)
    await restarted.start()
    await restarted.close()
    assert scene.gateway.credential(probe) is None, "the probe credential was left holding a key"
    assert scene.gateway.credential_reads == 0


async def test_a_probe_credential_the_gateway_would_not_remove_is_noted_row_21(
    world: Scene,
) -> None:
    """Row 21, with a models file. The check's own credential cannot be removed when the check ends
    (the gateway refuses): the note saved before it was stored stays, so the next start settles it
    and a restart retries until the gateway lets it go."""
    await world.set_up()
    stored: list[bool] = []

    def refuse_the_probe_s_removal_once_it_holds_a_key(r: httpx.Request) -> bool:
        if r.method == "POST" and r.url.path == "/credentials":
            stored.append(json.loads(r.content)["credential_name"] == "osprey-gemini.check")
        return (
            bool(stored)
            and any(stored)
            and r.method == "DELETE"
            and r.url.path == "/credentials/osprey-gemini.check"
        )

    faults(world).refuse.append(refuse_the_probe_s_removal_once_it_holds_a_key)
    with pytest.raises(ModelAdminRefused):
        await moved(world)
    assert "gemini.check" in world.admin.settings.intents
    assert world.gateway.credential("osprey-gemini.check") == world.second, "the plant"
    faults(world).refuse.clear()
    restarted = world.process(faulty=False, retry_seconds=3600)
    await restarted.start()
    await restarted.close()
    assert world.gateway.credential("osprey-gemini.check") is None
    assert not restarted.settings.intents
    assert world.gateway.credential("osprey-gemini") == world.first, "the engine's own key stands"


async def test_a_refused_key_set_does_not_clear_a_note_an_earlier_change_left_rows_16_and_39(
    world: Scene,
) -> None:
    """Rows 16 and 39, the other end. A moved edit fails with its key held and the gateway will not
    remove it, so the note stays and the engine is withheld. A key entered for it while the gateway
    still refuses is refused too, and **must not give back the note that was already there**: the
    credential still holds the key typed for the new address. Once the gateway lets go, the key
    entered reaches the old address alone and the note is cleared."""
    await world.set_up()
    armed: list[bool] = []

    def refuse_the_entries(r: httpx.Request) -> bool:
        if live("/model/new")(r):
            armed.append(True)
            return True
        return False

    faults(world).refuse.append(refuse_the_entries)
    faults(world).refuse.append(lambda r: bool(armed) and credential_of("DELETE")(r))
    with pytest.raises(ModelAdminRefused):
        await moved(world)
    faults(world).refuse[0] = lambda r: False
    assert "gemini" in world.admin.settings.intents
    assert world.gateway.credential("osprey-gemini") == world.second, "the plant: still held"

    third = a_key()
    world.gateway.providers["gemini"] = type(world.gateway.providers["gemini"])(
        third, frozenset({MODEL})
    )
    with pytest.raises(ModelAdminRefused):
        await world.admin.set_key("admin-1", "gemini", SecretStr(third))
    assert "gemini" in world.admin.settings.intents, "a refused step gave back an earlier note"
    assert world.admin.routes().engines["gemini"].key_present is False
    assert not any(i.startswith("osprey-gemini-") for i in world.gateway.stored_ids())

    faults(world).refuse.clear()
    await world.admin.set_key("admin-1", "gemini", SecretStr(third))
    assert not world.admin.settings.intents
    world.gateway.sent.clear()
    await world.call()
    assert world.addresses_reached_by(third) == {OLD}
    assert (OLD, world.second) not in world.gateway.sent


# --- the first check: a new engine's key held for a check that did not finish ---------------------


async def test_a_check_killed_after_its_key_was_stored_is_settled_at_start_row_21(
    world: Scene,
) -> None:
    """The first check's credential (a new engine's key, held under its name until **Add**).
    The check's record carries a note of intent in the same save that precedes the key, so a
    process killed after the gateway stored the key leaves a note: the next start removes the key
    and the unfinished check at once, where before the key stayed until the 15 minutes' sweep.
    Nothing is read back from the gateway."""
    await world.set_up()
    key = a_key()
    world.gateway.providers = {
        **world.gateway.providers,
        "openai": type(world.gateway.providers["gemini"])(key, frozenset({"gpt-4.1-mini"})),
    }
    engine = provider(OLD, name="openai", roles={"extraction": "gpt-4.1-mini"})
    faults(world).die_after.append(credential_of("POST", "openai"))
    with pytest.raises(Died):
        await world.admin.check("admin-1", engine, SecretStr(key))
    faults(world).dead = False
    assert world.gateway.credential("osprey-openai") == key, "the plant: the key is held"
    assert set(world.admin.settings.intents) == {"openai"}
    assert any(not c.passed for c in world.admin.settings.checks.values())

    restarted = world.process(faulty=False, retry_seconds=3600)
    await restarted.start()
    await restarted.close()
    assert world.gateway.credential("osprey-openai") is None, "the key outlived its check"
    assert not restarted.settings.checks and not restarted.settings.intents
    assert world.gateway.credential_reads == 0


# --- rows 4 and 5: a rotation killed between its steps; a probe key whose store was lost ----------


@pytest.mark.parametrize("where", ["after the old key was removed", "after the new key was stored"])
async def test_a_rotation_killed_between_its_steps_is_settled_at_start_row_4(
    world: Scene, where: str
) -> None:
    """Row 4. A rotation deletes the old credential, then stores the new one, then saves. The
    process stops after either step: the note of intent saved first is what start reads, so the
    restart does not offer an engine whose record says "set" over a credential that is gone or that
    holds a key the record has not been given (rows 4 and 36)."""
    await world.set_up()
    stop = faults(world)
    stop.die_after.append(credential_of("DELETE" if where.startswith("after the old") else "POST"))
    with pytest.raises(Died):
        await world.admin.set_key("admin-1", "gemini", SecretStr(world.second))
    stop.dead = False
    assert set(world.admin.settings.intents) == {"gemini"}, "the plant: the note is outstanding"
    held = world.gateway.credential("osprey-gemini")
    assert held in (None, world.second), "the plant"

    restarted = world.process(faulty=False, retry_seconds=3600)
    await restarted.start()
    await restarted.close()
    assert not restarted.settings.intents
    assert world.gateway.credential("osprey-gemini") is None, "no key the record did not name"
    assert restarted.key_state("gemini") == "lost"
    assert restarted.routes().engines["gemini"].key_present is False
    assert world.gateway.credential_reads == 0


async def test_a_probe_key_whose_store_was_lost_is_removed_row_5(world: Scene) -> None:
    """Row 5. The gateway stores the check's own credential and the answer is lost: the store reads
    as refused, and the probe was not removed (the removal began after the store). The removal is
    now asked whatever stopped the store, so the typed key never stays held."""
    await world.set_up()
    faults(world).lose_answer.append(
        lambda r: (
            r.method == "POST"
            and r.url.path == "/credentials"
            and json.loads(r.content)["credential_name"] == "osprey-gemini.check"
        )
    )
    with pytest.raises(ModelAdminRefused):
        await moved(world)
    faults(world).lose_answer.clear()
    assert world.gateway.credential("osprey-gemini.check") is None, "the probe still holds a key"
    assert world.gateway.credential("osprey-gemini") == world.first
    assert world.second not in recorded(world)
