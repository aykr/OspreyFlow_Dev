"""*Admin › Models*: an engine's access token on the gateway outlives the engine on four routes,
and the specification and the test that holds removal say so, naming each (the owner, 21 November
2026, AD1a's option (c), carried by AD1b; the fourth route added on the owner's ruling of 23
November, option A).

**What was false.** ADR-135 Amendment 14 point 9, and the docstring of
`test_model_key_paths.py::test_an_engine_s_removal_clears_its_virtual_key_n4`, said an engine's
removal deletes its derived key before the record forgets the engine, "so no key outlives its
record". Removal is the only route that deletes it. The engine's access token on the gateway (the
virtual key derived under the current master key and tagged with the engine's name) stays when the
engine leaves the record any other way, and the text now names four: the deployment switched to
local-only, a models file restored, a re-render that drops an engine, and an Add whose record cannot
be saved is undone (the token was put on the gateway before the record was saved, and the undo
withdraws the entries and not the token; the 15-minute sweep removes only a check's own key). AD1c
closes that last route; this slice builds no clearing route. The token reaches
no model unless an engine of the same name is added again. The note of intent covers the
credential, which is another thing; a changed master key (open row N6) has no route and stays named
beside them. **No clearing route is built (the owner's ruling).**

**Two halves, so the sentence cannot be made true by words alone and the words cannot go stale.**

1. *The routes really leave a token* (`test_each_route_leaves_the_token_and_the_engine_is_gone`). A
   stand-in gateway holds an engine's derived virtual key; the engine leaves the record by each
   route, driven the way the code does it (the start-up path, which runs `_reconcile`; never an
   internal helper called alone): the deployment switched to local-only, a models file restored
   without it, a re-render that drops a declared engine, an Add whose record cannot be saved (the
   file refuses the write, as a full disk does). After each, the engine is no longer served
   and its token is **still** on the stand-in. The stand-in models the real gateway's refusals, not
   only its grants (`test_the_stand_in_refuses_what_the_real_gateway_refuses`: a delete of a key it
   does not hold is a 404, a delete its database does not take a 500, a call with a deleted key a
   401), so a token cannot seem removed because a stand-in accepts anything.
   `test_a_clearing_route_would_turn_this_red` puts a clearing route into `_reconcile` and shows
   the first half see it.
2. *The words name exactly those routes*
   (`test_the_words_name_exactly_the_routes_that_leave_a_token`).
   The specification and the sibling test's docstring are read; each must say the engine's access
   token is **not** removed when the engine leaves the record any other way, and list exactly the
   routes of the first half (a route in the registry that the text does not name is red; so is a
   route the text names that no driver leaves). No text in the specification, either administration
   guide or the sibling test may say that no key or access token outlives its record without naming
   each of the four. The plants (rule 15) are at the shape the text takes: the false sentence put
   back (`test_the_false_sentence_put_back_is_red`), a route in the registry and not named
   (`test_a_route_not_named_is_red`: a fifth, driven for real as the local-only switch is, under a
   phrase the text lacks), each of the four cases taken out (`test_a_case_taken_out_is_red`), and a
   route the text names that no driver shows (`test_a_route_named_that_no_driver_shows_is_red`,
   each in turn). The text also says the 15-minute sweep does not remove the fourth route's token;
   that is driven (`test_the_sweep_does_not_remove_an_unsaved_adds_token`).

**The keys.** Every key is made at run time (the owner's rules): none is written in this file. After
every route nothing the test provokes (the log, the audit, the models file, the view, the routes)
holds the master key, the typed key or the token
(`test_no_route_puts_a_key_in_a_log_an_answer_or_the_audit`).

**Which test fails if each statement is violated (rule 12)**

- an engine's removal deletes its derived key:
  `test_model_key_paths.py::test_an_engine_s_removal_clears_its_virtual_key_n4`;
- the other four routes leave it: `test_each_route_leaves_the_token_and_the_engine_is_gone`, and
  it reaches no model until the engine is added again:
  `test_a_left_token_reaches_no_model_until_the_engine_is_added_again`;
- the text names exactly those routes: `test_the_words_name_exactly_the_routes_that_leave_a_token`.

**Walks.** The words are read from four named files (the specification's decision log, the two
administration guides and the sibling test); nothing is globbed or walked. The temporary folder is
the test's own.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from services.api.model_admin import (
    GatewayAdmin,
    InMemoryModelAdminAudit,
    Installed,
    ModelAdmin,
    ModelAdminRefused,
    ModelSettings,
    ModelSettingsFile,
    gateway_model_name,
)

from adapters.model_litellm.stand_in import (
    StandInClientGateway,
    StandInGateway,
    StandInProvider,
)
from adapters.model_litellm.usage import engine_key
from schemas.deployment import ModelProviderConfig

BUILD = Path(__file__).resolve().parents[3]
CORE = BUILD.parent / "OspreyFlow_Core"
SPEC = BUILD / "spec" / "06_DECISIONS.md"
SIBLING = BUILD / "tests" / "services" / "api" / "test_model_key_paths.py"
GUIDES = (
    BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md",
    CORE / "docs" / "administration-guide.md",
)

MODEL = "gemini-2.5-flash"
CLIENT_MODEL = "gpt-4o-mini"
CLIENT_BASE = "https://ai-gateway.client.example/v1"
KEYED = {"name": "gemini", "label": "Gemini", "roles": {"extraction": MODEL}}
BY_ROLE = {
    "name": "acme",
    "label": "Acme AI gateway",
    "kind": "gateway",
    "auth": "iam_role",
    "api_base": CLIENT_BASE,
    "roles": {"extraction": CLIENT_MODEL},
}
ADMIN = "admin-1"


def a_key() -> str:
    """A key made now, for this run only."""
    return "sk-" + secrets.token_hex(16)


# --- a deployment: one gateway, one models folder, one audit, any number of Conduit processes ----


class Site:
    def __init__(self, tmp_path: Path) -> None:
        self.folder = tmp_path / "model-settings"
        self.master = a_key()
        self.typed = a_key()
        self.client_token = a_key()
        self.gateway = StandInGateway(
            master_key=self.master,
            salt_key=a_key(),
            providers={"gemini": StandInProvider(self.typed, frozenset({MODEL}))},
            client_gateways={
                CLIENT_BASE: StandInClientGateway(self.client_token, frozenset({CLIENT_MODEL}))
            },
        )
        self.audit = InMemoryModelAdminAudit()
        self.processes: list[ModelAdmin] = []
        #: The check's 15 minutes run on this clock, which a test moves.
        self.now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)

    def process(
        self, *, local_only: bool = False, declared: tuple[dict[str, object], ...] = ()
    ) -> ModelAdmin:
        """A Conduit over this deployment, as a restart makes one: `local_only` and `declared` are
        what `osprey.yaml` says to it."""
        http = httpx.AsyncClient(
            base_url="http://litellm:4000",
            transport=self.gateway.transport(),
            headers={"Authorization": f"Bearer {self.master}"},
        )
        admin = ModelAdmin(
            installed=Installed(
                providers=[ModelProviderConfig.model_validate(d) for d in declared],
                defaults={},
                key_present={},
                local_only=local_only,
                sendable=["O"],
                locals={
                    "extraction": "qwen2.5:7b-instruct",
                    "vision": None,
                    "transcription": None,
                    "embedding": None,
                },
            ),
            settings_file=ModelSettingsFile(self.folder),
            gateway=GatewayAdmin(http),
            audit=self.audit,
            retry_seconds=3600,
            now=lambda: self.now,
        )
        self.processes.append(admin)
        return admin

    async def added(self, admin: ModelAdmin) -> None:
        """The engine added as the screen adds it: its key and model proved by a check, then Add."""
        checked = await admin.check(
            ADMIN, ModelProviderConfig.model_validate(KEYED), SecretStr(self.typed)
        )
        assert checked.ok and checked.check, checked.words
        await admin.add_checked(ADMIN, checked.check)

    def tokens(self, engine: str) -> list[str]:
        """The gateway's virtual keys tagged with `engine`'s name (what `put_engine_key` makes),
        read from the stand-in's own state, not derived here."""
        return [
            key
            for key, held in self.gateway.virtual_keys().items()
            if held.metadata.get("osprey_engine") == engine
        ]

    def entries(self) -> set[str]:
        return self.gateway.stored_ids()

    async def call(self, token: str, model: str) -> int:
        """A call as the token's holder makes it, straight at the gateway."""
        async with httpx.AsyncClient(
            base_url="http://litellm:4000",
            transport=self.gateway.transport(),
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            answer = await client.post(
                "/chat/completions",
                json={"model": model, "messages": [{"role": "user", "content": "x"}]},
            )
        return answer.status_code

    def shown(self, admin: ModelAdmin, caplog: pytest.LogCaptureFixture) -> str:
        """Everything the routes provoked that a person, a log or the record could be shown."""
        return " ".join(
            [
                caplog.text,
                json.dumps([e.model_dump(mode="json") for e in self.audit.entries]),
                admin.settings.model_dump_json(),
                admin.view().model_dump_json(),
                repr(admin.routes()),
            ]
        )


@pytest.fixture
def site(tmp_path: Path) -> Site:
    return Site(tmp_path)


async def finished(*admins: ModelAdmin) -> None:
    for admin in admins:
        await admin.close()


# --- the three routes, each driven through the start-up path (`start`, which runs `_reconcile`) ---


@dataclass(frozen=True)
class Route:
    """One way an engine leaves the record other than its removal. `phrase` is how the text names
    it, word for word; `leave` drives it and returns the engine's name."""

    phrase: str
    leave: Callable[[Site], Awaitable[str]]


async def local_only(site: Site) -> str:
    """The deployment switched to local-only: the next start keeps no hosted entry."""
    first = site.process()
    await first.start()
    await site.added(first)
    await finished(first)
    switched = site.process(local_only=True)
    await switched.start()
    await finished(switched)
    return "gemini"


async def restored(site: Site) -> str:
    """A models file restored from before the engine was added: the next start finds the record
    without it. The file is written back byte for byte, as a restore writes it."""
    ModelSettingsFile(site.folder).save(ModelSettings())
    older = (site.folder / "models.yaml").read_bytes()
    before = site.process()
    await before.start()
    await site.added(before)
    await finished(before)
    assert b"gemini" in (site.folder / "models.yaml").read_bytes(), (
        "the plant: the engine is recorded"
    )
    (site.folder / "models.yaml").write_bytes(older)
    after = site.process()
    await after.start()
    await finished(after)
    return "gemini"


async def re_rendered(site: Site) -> str:
    """A declared engine (an IAM-role one, made at start from `osprey.yaml` with no models file)
    dropped by a re-render: the next start declares none."""
    declared = site.process(declared=(BY_ROLE,))
    await declared.start()
    await finished(declared)
    dropped = site.process()
    await dropped.start()
    await finished(dropped)
    return "acme"


async def unsaved_add(site: Site) -> str:
    """An **Add** whose record cannot be saved (the owner's ruling of 23 November, option A: a
    fourth route, named). The engine's key is made by `_reconcile` before the record is saved, the
    undo withdraws the entries and not the key, and the record never held the engine: so a token
    outlives an engine that was never in the record. Driven through the screen's own two steps (a
    check, then Add), with the file's write refused as a full disk refuses it."""
    admin = site.process()
    await admin.start()
    checked = await admin.check(
        ADMIN, ModelProviderConfig.model_validate(KEYED), SecretStr(site.typed)
    )
    assert checked.ok and checked.check, checked.words
    real = admin._file.save

    def cannot_save(settings: ModelSettings) -> None:
        if any(p.name == "gemini" for p in settings.providers):
            raise OSError(28, "No space left on device")
        real(settings)

    admin._file.save = cannot_save  # type: ignore[method-assign]
    with pytest.raises(ModelAdminRefused):
        await admin.add_checked(ADMIN, checked.check)
    await finished(admin)
    return "gemini"


ROUTES = (
    Route("when the deployment is switched to local-only", local_only),
    Route("when a models file is restored", restored),
    Route("when a re-render drops an engine", re_rendered),
    Route("when an Add whose record cannot be saved is undone", unsaved_add),
)


def made(site: Site, name: str) -> None:
    assert len(site.tokens(name)) == 1, "the plant: the engine's token is on the gateway"


# --- half 1: the routes really leave a token ------------------------------------------------------


def engine_is_gone(site: Site, name: str) -> bool:
    return not any(i.startswith(f"osprey-{name}-") for i in site.entries())


def token_left(site: Site, name: str) -> bool:
    """The engine's access token is on the gateway: tagged with the engine's name, and the one the
    master key derives for it."""
    return site.tokens(name) == [engine_key(site.master, name)]


@pytest.mark.parametrize("route", ROUTES, ids=lambda r: r.phrase)
async def test_each_route_leaves_the_token_and_the_engine_is_gone(site: Site, route: Route) -> None:
    """The engine's entries are withdrawn, nothing serves it, and its access token is **still** on
    the gateway: tagged with the engine's name, and the one the master key derives for it."""
    name = await route.leave(site)
    assert engine_is_gone(site, name), (
        f"{route.phrase}: the engine still has entries on the gateway"
    )
    assert token_left(site, name), (
        f"{route.phrase}: the engine's access token is not on the gateway, so the text that names "
        "this route as leaving it is wrong"
    )


@pytest.mark.parametrize("route", ROUTES, ids=lambda r: r.phrase)
async def test_a_left_token_reaches_no_model_until_the_engine_is_added_again(
    site: Site, route: Route
) -> None:
    name = await route.leave(site)
    [token] = site.tokens(name)
    held = site.gateway.virtual_key(token)
    assert held is not None and held.models, (
        "the plant: the token is limited to the engine's models"
    )
    for model in held.models:
        assert await site.call(token, model) != 200, f"{route.phrase}: a left token reached {model}"


async def test_a_left_token_works_again_when_an_engine_of_the_same_name_is_added(
    site: Site,
) -> None:
    """The one half of 'unless an engine of the same name is added again' the routes can show with
    nothing built: the deployment switched back from local-only serves the engine, and the very
    token that was left calls it."""
    name = await local_only(site)
    [token] = site.tokens(name)
    model = gateway_model_name(name, MODEL)
    assert await site.call(token, model) != 200
    back = site.process()
    await back.start()
    await finished(back)
    assert site.tokens(name) == [token], "the same token, not a new one"
    assert await site.call(token, model) == 200


async def test_the_stand_in_refuses_what_the_real_gateway_refuses(site: Site) -> None:
    """Rule 15: a stand-in that accepted any delete would let 'the token is gone' be proved by the
    stand-in. The pinned gateway was measured (`stand_in.py`'s docstring) to answer a delete of a
    key it does not hold with a 404, a delete its database does not take with a 500, and a call
    with a deleted key with a 401."""
    admin = site.process()
    await admin.start()
    await site.added(admin)
    [token] = site.tokens("gemini")
    master = httpx.AsyncClient(
        base_url="http://litellm:4000",
        transport=site.gateway.transport(),
        headers={"Authorization": f"Bearer {site.master}"},
    )
    async with master:
        unknown = await master.post("/key/delete", json={"keys": [a_key()]})
        assert unknown.status_code == 404
        site.gateway.refuse_key_delete = 500
        refused = await master.post("/key/delete", json={"keys": [token]})
        assert refused.status_code == 500
        assert site.tokens("gemini") == [token], "a refused delete removed nothing"
        site.gateway.refuse_key_delete = None
        deleted = await master.post("/key/delete", json={"keys": [token]})
        assert deleted.status_code == 200
    assert site.tokens("gemini") == []
    assert await site.call(token, gateway_model_name("gemini", MODEL)) == 401
    await finished(admin)


async def test_removal_is_the_one_route_that_clears_it(site: Site) -> None:
    """The contrast that makes 'the only route' a measured statement: the same engine, removed."""
    admin = site.process()
    await admin.start()
    await site.added(admin)
    made(site, "gemini")
    await admin.remove_engine(ADMIN, "gemini")
    await finished(admin)
    assert site.tokens("gemini") == []


async def test_a_clearing_route_would_turn_this_red(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, for the first half: a reconcile that also deleted the key of each engine it
    withdrew (what a later clearing route would be) makes `each_route_leaves_the_token` fail, so
    that test can see a token go. The owner ruled that none is built; if one ever is, this shows
    which test and which sentence must change with it."""
    real = ModelAdmin._reconcile

    async def clearing(self: ModelAdmin, settings, held=None, rebuilt=frozenset()):  # type: ignore[no-untyped-def]
        before = {p.name for p in self.settings.providers}
        done = await real(self, settings, held, rebuilt)
        for name in before - {p.name for p in self._hosted(settings).providers}:
            await self._gateway.delete_engine_key(name)
        return done

    monkeypatch.setattr(ModelAdmin, "_reconcile", clearing)
    name = await local_only(site)
    assert engine_is_gone(site, name), "the plant: the engine left by the route as before"
    assert not token_left(site, name), "the first half did not see the clearing reconcile's removal"


@pytest.mark.parametrize("route", ROUTES, ids=lambda r: r.phrase)
async def test_no_route_puts_a_key_in_a_log_an_answer_or_the_audit(
    site: Site, route: Route, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    name = await route.leave(site)
    [token] = site.tokens(name)
    watcher = site.process()
    await watcher.start()
    await finished(watcher)
    shown = site.shown(watcher, caplog)
    for what, secret in (
        ("the master key", site.master),
        ("the typed key", site.typed),
        ("the client gateway's token", site.client_token),
        ("the engine's access token", token),
    ):
        assert secret not in shown, f"{route.phrase}: {what} reached a log, an answer or the audit"


# --- half 2: the words name exactly those routes --------------------------------------------------

LEAD = "therefore not removed when the engine leaves the record any other way:"
FALSE = "so no key outlives its record"
#: What the corrected text says in place of `FALSE`, from its first sentence to its last, in the
#: specification and in the docstring alike (the sibling's docstring is worded to the same words).
TRUE_SPAN = re.compile(r"That is the only route\..*?an engine of the same name is added again\.")
BEFORE = "before the record forgets the engine"
CLAIM = re.compile(
    r"\bno (?:key|access token|token|virtual key)s?\s+(?:ever\s+)?"
    r"(?:outlives?|survives?|remains?\s+after)\s+(?:its|the|an engine's)\s+record\b",
    re.IGNORECASE,
)


def plain(text: str) -> str:
    """The words as read: emphasis and code marks dropped, every run of space one space (the
    specification wraps its lines, and a docstring wraps its own)."""
    return " ".join(re.sub(r"[*`]", "", text).split())


def routes_named(text: str) -> list[str] | None:
    """The routes the text says leave a token: the list after `LEAD`, as its items, or None where
    the text does not say the token is not removed on any other route."""
    words = plain(text)
    at = words.find(LEAD)
    if at < 0:
        return None
    sentence = words[at + len(LEAD) :].strip().split(". ")[0].rstrip(".")
    # An item's own explanation, in brackets, is not another item.
    sentence = re.sub(r"\s*\([^)]*\)", "", sentence)
    return [i.strip() for i in re.split(r",\s*(?:or\s+)?(?=when\b)", sentence) if i.strip()]


def problems_in(
    routes: tuple[Route, ...], spec: str, sibling: str, guides: tuple[tuple[str, str], ...]
) -> list[str]:
    """Every way the words differ from the routes the first half found."""
    found = {r.phrase for r in routes}
    problems: list[str] = []
    for where, text in (("the specification", spec), ("the sibling test's docstring", sibling)):
        named = routes_named(text)
        if named is None:
            problems.append(
                f"{where}: does not say the engine's access token is not removed when the engine "
                "leaves the record any other way"
            )
            continue
        problems += [
            f"{where}: a route that leaves a token is not named: {phrase}"
            for phrase in sorted(found - set(named))
        ]
        problems += [
            f"{where}: names a route no driver shows leaving a token: {phrase}"
            for phrase in sorted(set(named) - found)
        ]
        if not re.search(r"\bN6\b", plain(text)):
            problems.append(f"{where}: the changed master key (row N6) is not named beside them")
    for where, text in (("the specification", spec), ("the sibling test", sibling), *guides):
        words = plain(text)
        for claim in CLAIM.finditer(words):
            around = words[max(0, claim.start() - 600) : claim.end() + 600]
            missing = sorted(r.phrase for r in routes if r.phrase not in around)
            if missing:
                problems.append(
                    f"{where}: says '{claim.group(0)}' without naming: " + "; ".join(missing)
                )
    return problems


def words_as_they_are() -> tuple[str, str, tuple[tuple[str, str], ...]]:
    return (
        SPEC.read_text(encoding="utf-8"),
        SIBLING.read_text(encoding="utf-8"),
        tuple((g.name, g.read_text(encoding="utf-8")) for g in GUIDES),
    )


def the_false_sentence_put_back(text: str) -> str:
    """The corrected text turned back into the old one, at the shape the text takes: the three
    sentences that name the routes cut out, and `FALSE` said after the removal."""
    words = plain(text)
    cut = TRUE_SPAN.sub("", words, count=1)
    assert cut != words, "the plant: the text has the corrected sentences to replace"
    assert BEFORE in cut
    return cut.replace(BEFORE, f"{BEFORE}, {FALSE}", 1)


def test_the_words_name_exactly_the_routes_that_leave_a_token() -> None:
    spec, sibling, guides = words_as_they_are()
    assert problems_in(ROUTES, spec, sibling, guides) == []


def test_the_specification_still_names_the_one_route_with_no_clearing_at_all() -> None:
    """Row N6, the changed master key, stays named beside the three."""
    spec, _, _ = words_as_they_are()
    assert "What has no route (open row N6" in plain(spec)


def test_the_false_sentence_put_back_is_red() -> None:
    """Plant 1: the old sentence back, in the specification and then in the docstring."""
    spec, sibling, guides = words_as_they_are()
    problems = problems_in(ROUTES, the_false_sentence_put_back(spec), sibling, guides)
    assert any("the specification" in p and "does not say" in p for p in problems), problems
    assert any("the specification: says 'no key outlives its record'" in p for p in problems)
    problems = problems_in(ROUTES, spec, the_false_sentence_put_back(sibling), guides)
    assert any("docstring" in p and "does not say" in p for p in problems), problems
    assert any("the sibling test: says 'no key outlives its record'" in p for p in problems)


@pytest.mark.parametrize(
    "claim", ["no key outlives its record", "no access token outlives its record"]
)
def test_the_false_sentence_in_a_guide_is_red(claim: str) -> None:
    spec, sibling, guides = words_as_they_are()
    guide = ("an administration guide", f"Removing an engine ends its key, so {claim}.")
    problems = problems_in(ROUTES, spec, sibling, (*guides, guide))
    assert problems and all("an administration guide" in p for p in problems), problems


def test_the_claim_with_the_three_cases_beside_it_is_not_red() -> None:
    """The check reads what is said, not the sentence's mere presence: a text that says it and
    names each of the three beside it is as true as the corrected one."""
    spec, sibling, guides = words_as_they_are()
    beside = (
        "a guide",
        f"Removal ends its key, {FALSE} except " + "; ".join(r.phrase for r in ROUTES),
    )
    assert problems_in(ROUTES, spec, sibling, (*guides, beside)) == []


@pytest.mark.parametrize("dropped", [r.phrase for r in ROUTES])
def test_a_route_named_that_no_driver_shows_is_red(dropped: str) -> None:
    """The other direction, for each route in turn: the text names a route the registry no longer
    shows leaving a token."""
    spec, sibling, guides = words_as_they_are()
    problems = problems_in(tuple(r for r in ROUTES if r.phrase != dropped), spec, sibling, guides)
    assert any(dropped in p and "no driver" in p for p in problems), problems


@pytest.mark.parametrize("taken", [r.phrase for r in ROUTES])
def test_a_case_taken_out_is_red(taken: str) -> None:
    """Plant 3: one of the three cases removed from the text, in the specification and then in the
    docstring; each is red for that case, naming it."""
    spec, sibling, guides = words_as_they_are()
    cut_from = re.compile(rf",?\s*(?:or\s+)?{re.escape(taken)}")
    for where, text in (("the specification", spec), ("the sibling test's docstring", sibling)):
        words = plain(text)
        assert taken in words, f"the plant: {where} names '{taken}'"
        cut = cut_from.sub("", words, count=1)
        planted = (cut, sibling) if text is spec else (spec, cut)
        problems = problems_in(ROUTES, planted[0], planted[1], guides)
        assert any(where in p and taken in p and "not named" in p for p in problems), problems


#: A fifth route, for the plant only: a phrase the text lacks, with a driver that really leaves a
#: token (the local-only switch), so the registry and the gateway agree and only the words differ.
UNNAMED = Route("when an engine's record is edited by hand", local_only)


async def test_the_unnamed_plant_does_leave_a_token(site: Site) -> None:
    """The plant below is a registry entry whose driver leaves a real token: it is red for being
    unnamed, not because its driver does nothing."""
    name = await UNNAMED.leave(site)
    assert engine_is_gone(site, name)
    assert token_left(site, name)


def test_a_route_not_named_is_red() -> None:
    """Plant 2: a route in the registry (the stand-in leaves its token), not in the text."""
    spec, sibling, guides = words_as_they_are()
    problems = problems_in((*ROUTES, UNNAMED), spec, sibling, guides)
    assert any(UNNAMED.phrase in p and "not named" in p for p in problems if "specification" in p)
    assert any(UNNAMED.phrase in p and "not named" in p for p in problems if "docstring" in p)


async def test_the_sweep_does_not_remove_an_unsaved_adds_token(site: Site) -> None:
    """The text says the 15-minute sweep removes only a check's own key, so it does not remove the
    token of an Add that could not be saved. Driven: the check lapses, the sweep runs (the held
    check is gone and its credential with it), and the engine's token is still on the gateway."""
    name = await unsaved_add(site)
    assert token_left(site, name)
    site.now += timedelta(minutes=16)
    sweeper = site.process()
    await sweeper.sweep_checks()
    await finished(sweeper)
    assert not sweeper.settings.checks, "the plant: the sweep ran and removed the lapsed check"
    assert token_left(site, name), "the sweep removed the engine's token, so the text is wrong"
