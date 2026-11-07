"""A screening list's refresh, and the re-screening it starts (`06_DECISIONS.md` ADR-133 decision 4,
stage (c)).

**Refresh.** A subscribed list is read from its file in the ingest folder through its connector (a
Knowledge Adapter with golden files, `knowledge_adapters/screening_lists.py`; rule 8) and applied
as a new version: the store replaces its entries whole and says which it added, changed and
removed (`ScreeningListStore.apply_update`). Every refresh is recorded — updated, unchanged,
refused or failed, in words — and a refused or failed one is the list's failure on the Lists
screen until a later refresh succeeds. Nothing of a refused or failed file is kept.

**Rule 9, before anything is read into the store.** A list is synthetic only when every file it is
read from is one of the repository's own synthetic files, known by its SHA-256 in
`packages/demo_fixtures/screening_lists/synthetic.sha256` — a flag a file carries about itself is
not trusted. Any other list is real, must name its dataset, and that dataset must be in this
device's `real_data_exceptions.yaml` for the subscription's use (ADR-035 §C3); otherwise it is
refused and nothing is loaded.

**Re-screening, against the changed entries only.** Each active `kyc_screening` rule in the
deployment re-screens, as its own deployer, every person and organisation of its case that the
deployer may read (`GraphPort.list_nodes`, paged to the end, access filtered in the adapter —
rule 3), against the entries the update added or changed, at the rule's own `min_score`. A match is
the rule's finding exactly as at onboarding: the listed party, a scored `SAME_AS` written
`inferred` (rule 5, never a merge — rule 6), and a `kyc_screening` alert in the case's one queue at
screening severity. An entry the update left unchanged is not read, and a match already alerted is
not alerted again. A listed party is not itself a customer and is never screened.

**When it runs.** A refresh is started by an administrator (the Lists screen's *Refresh now*,
`POST /v1/admin/screening-lists/{name}/refresh`), an operator (`python -m
scripts.refresh_screening_list <name>`), or the list's own schedule (ADR-133 stage (d),
`list_schedule.py`), run as the person who set it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.screening_lists import LIST_ADAPTERS, ListedParty, ParsedList
from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.domain import KycScreeningParams, Principal, TypologyRule
from schemas.screening import ScreeningListStatus, ScreeningListUpdate

from .alerts import AlertStore
from .audit import AuditWriter
from .dataset_scope import scope_to_case, set_case_datasets
from .ingest_sources import ingest_root, is_inside
from .screening import ListDiff, ScreeningEntry, ScreeningListStore, UnitCounts, screen

#: Each connector's licence, as the Lists screen says it (`00_ARCHITECTURE.md` §7 cites each).
LICENCES: dict[str, str] = {
    "ofac_sdn": "US Government work, in the public domain (17 U.S.C. §105)",
    "ofsi_consolidated": (
        "Open Government Licence v3.0. The OFSI Consolidated List closed on 28 January 2026; "
        "the UK Sanctions List replaces it"
    ),
    "uk_sanctions_list": (
        "Open Government Licence v3.0 (Crown copyright; the FCDO's UK Sanctions List, gov.uk)"
    ),
    "un_consolidated": (
        "United Nations terms of use; no open licence is stated for the list — check before reuse"
    ),
    "eu_consolidated": "European Commission reuse notice (Decision 2011/833/EU)",
    "opensanctions": "CC BY-NC 4.0: non-commercial use only, unless licensed by OpenSanctions",
}

#: The owner's answer of 1 November 2026 (ADR-133 Amendment 3's licence findings): the connectors
#: whose licence for a customer's screening is not confirmed, each with the reason in words. Until
#: it is, they read OspreyFlow's synthetic lists only; a real file is refused, whatever this
#: device's exceptions admit. `apps/workspace/src/alerts/ListsPanel.tsx` says the same words, held
#: in step by `test_the_glass_says_the_same_licence_reasons_as_the_conduit`.
LICENCE_NOT_CONFIRMED: dict[str, str] = {
    "un_consolidated": (
        "no open licence was found for the UN consolidated list, and the UN's general terms allow "
        "personal, non-commercial use only; its terms are to be confirmed with the UN"
    ),
    "opensanctions": (
        "OpenSanctions is CC BY-NC 4.0, and screening in a business is commercial use, which needs "
        "OpenSanctions' own data licence"
    ),
}

#: ADR-133 Amendment 6: the connectors whose publisher has closed the list they read, with the words
#: the Lists tab says beside each. The connector's code is kept (ADR-133 Amendment 3), so a file
#: already held can still be read, but nothing new will ever be published to it.
#: `apps/workspace/src/alerts/ListsPanel.tsx` says the same words, held in step by
#: `test_the_glass_says_the_same_closed_list_words_as_the_conduit`.
CLOSED_LISTS: dict[str, str] = {
    "ofsi_consolidated": (
        "this connector reads a closed list: the OFSI Consolidated List closed on 28 January 2026 "
        "and is no longer updated, and the FCDO's UK Sanctions List is now the only source of UK "
        "designations"
    ),
}

SYNTHETIC_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "demo_fixtures"
    / "screening_lists"
    / "synthetic.sha256"
)

#: The OFAC files read beside `SDN.CSV` when they are there.
_OFAC_COMPANIONS = {"alt_csv": "ALT.CSV", "add_csv": "ADD.CSV"}


class ListRefused(Exception):
    """The list may not be read, in words: outside the ingest folder, missing, or real data this
    device has not admitted (rule 9)."""


class ListNotSubscribed(Exception):
    pass


def synthetic_digests(manifest: Path = SYNTHETIC_MANIFEST) -> set[str]:
    """The SHA-256 of every synthetic list file the repository holds."""
    if not manifest.exists():
        return set()
    lines = manifest.read_text(encoding="utf-8").splitlines()
    return {ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def admit(
    files: dict[str, bytes],
    status: ScreeningListStatus,
    use: str,
    *,
    manifest: Path = SYNTHETIC_MANIFEST,
    exceptions_path: Path | None = None,
) -> bool:
    """Whether the list is synthetic (`True`) or a real list this device admits (`False`); refuses
    it otherwise (rule 9). Synthetic means every file is one of the repository's own."""
    known = synthetic_digests(manifest)
    if files and all(_digest(c) in known for c in files.values()):
        return True
    if not status.dataset:
        raise ListRefused(
            "this is not one of OspreyFlow's synthetic lists, so it is real data and must name its "
            "dataset; nothing was loaded (rule 9)"
        )
    from scripts.real_data_exceptions import is_permitted

    permitted = (
        is_permitted(status.dataset, use)
        if exceptions_path is None
        else is_permitted(status.dataset, use, config_path=exceptions_path)
    )
    if not permitted:
        raise ListRefused(
            f"“{status.dataset}” is real data and is not in this device's "
            f"real_data_exceptions.yaml for {use.replace('_', ' ')}; nothing was loaded (rule 9)"
        )
    # A real list this device admits is still refused while its connector's licence is not
    # confirmed (the owner's answer of 1 November 2026).
    unconfirmed = LICENCE_NOT_CONFIRMED.get(status.source)
    if unconfirmed is not None:
        raise ListRefused(
            f"this list's licence is not confirmed: {unconfirmed}. Until it is, only OspreyFlow's "
            "synthetic list may be read through this connector; nothing was loaded"
        )
    return False


def check_location(location: str, root: Path | None = None) -> Path:
    """The location resolved inside the ingest folder (links followed first), or refused in words
    that do not say whether anything is there."""
    root = root if root is not None else ingest_root()
    resolved = (root / location).resolve()
    if not is_inside(root, resolved):
        raise ListRefused("the list's location is outside the ingest folder; nothing was read")
    return resolved


def read_files(status: ScreeningListStatus, root: Path | None = None) -> dict[str, bytes]:
    """The subscription's file, and for OFAC its companions, read from inside the ingest folder
    only; a location outside it is refused in words that do not say whether it exists."""
    root = root if root is not None else ingest_root()
    main = check_location(status.location, root)
    if not main.is_file():
        raise ListRefused(f"there is no file at {status.location} in the ingest folder")
    files = {"main": main.read_bytes()}
    if status.source == "ofac_sdn":
        for key, name in _OFAC_COMPANIONS.items():
            for candidate in (main.parent / name, main.parent / name.lower()):
                resolved = candidate.resolve()
                if is_inside(root, resolved) and resolved.is_file():
                    files[key] = resolved.read_bytes()
                    break
    return files


def parse(source: str, files: dict[str, bytes]) -> ParsedList:
    """The connector over the files' text; a file that is not UTF-8 is refused like any other
    malformed one."""
    try:
        text = {k: v.decode("utf-8-sig") for k, v in files.items()}
    except UnicodeDecodeError as error:
        raise NormalisationError(
            source, "", f"the file is not UTF-8 text ({error.reason})"
        ) from error
    adapter = LIST_ADAPTERS[source]
    return adapter(text.pop("main"), **text)


def entries_of(list_name: str, parsed: ParsedList, *, synthetic: bool) -> list[ScreeningEntry]:
    def one(p: ListedParty) -> ScreeningEntry:
        return ScreeningEntry(
            id=f"{list_name}:{p.ref}",
            list_name=list_name,
            listing=p.listing,
            entity_type=p.entity_type,
            name=p.name,
            date_of_birth=date.fromisoformat(p.date_of_birth) if p.date_of_birth else None,
            country=p.country,
            synthetic=synthetic,
            aliases=p.aliases,
        )

    return [one(p) for p in parsed.entries]


# --- re-screening ---------------------------------------------------------------------------------


class ScreeningRules(Protocol):
    async def list_active_of_typology(self, typology: str) -> list[TypologyRule]: ...


class CaseDatasets(Protocol):
    """What a re-screening asks of the dataset store: a case's read set and layer, scoped as a
    request is (`scope_to_case`); what it chose, so a composite case's alert goes into its layer;
    and whether a rule's own dataset is a composite (ADR-099 Amendment 15)."""

    async def ids_of_case(self, investigation_id: str) -> list[str]: ...
    async def layer_of_case(self, investigation_id: str) -> str | None: ...
    async def chosen_of_case(self, investigation_id: str) -> list[Any]: ...
    async def composites_among(self, dataset_ids: Sequence[str]) -> set[str]: ...


@dataclass
class RescreenReport:
    """The whole re-screening (the operator's command and the audit), and each unit's own part of
    it: a rule's customers, alerts and failure belong to its deployer's unit, which alone reads
    them (the owner's answer of 1 November 2026). A rule whose deployer cannot be resolved has no
    unit, so its failure is in the whole report alone."""

    rules: int = 0
    customers: int = 0
    alerts: int = 0
    failures: list[str] = field(default_factory=list)
    by_unit: dict[str, UnitCounts] = field(default_factory=dict)

    def unit(self, org_unit: str) -> UnitCounts:
        return self.by_unit.setdefault(org_unit, UnitCounts())


@dataclass
class Rescreener:
    """Everything a re-screening reads and writes through: the rules, each case's datasets, the
    graph as each deployer, and the queue the alerts go to."""

    rules: ScreeningRules
    datasets: CaseDatasets
    graph: GraphPort
    scheme: HandlingScheme
    alert_store: AlertStore
    audit: AuditWriter
    valkey: Valkey
    principal_for_owner: Callable[[str], Awaitable[Principal | None]]
    #: Who the audit names as running it: the administrator or operator who refreshed the list.
    runner: Principal
    page_size: int = 500

    async def __call__(self, diff: ListDiff) -> RescreenReport:
        report = RescreenReport()
        changed = diff.to_screen
        if not changed:
            return report
        for rule in await self.rules.list_active_of_typology("kyc_screening"):
            report.rules += 1
            unit: str | None = None
            try:
                deployer = await self.principal_for_owner(rule.owner_id)
                if deployer is None:
                    raise RuntimeError(
                        "its deployer could not be resolved, so it could not run as them"
                    )
                unit = deployer.org_unit
                customers, raised = await self._rule(rule, deployer, changed, diff)
            except Exception as error:  # noqa: BLE001 - one rule's trouble never stops the rest
                said = f"rule “{rule.name}” could not re-screen: {error}"
                report.failures.append(said)
                if unit is not None:
                    report.unit(unit).failures.append(said)
                continue
            report.customers += customers
            report.alerts += raised
            counts = report.unit(unit)
            counts.rescreened += customers
            counts.alerts += raised
        return report

    async def _rule(
        self,
        rule: TypologyRule,
        deployer: Principal,
        changed: Sequence[ScreeningEntry],
        diff: ListDiff,
    ) -> tuple[int, int]:
        from .kyc_rules import CUSTOMER_TYPES, KycContext, party_name, screening_finding
        from .rule_evaluation import RuleGate

        params = rule.params
        assert isinstance(params, KycScreeningParams)
        # The rule reads within its case's datasets, as at onboarding (ADR-099): its own dataset,
        # else the case's. Whatever it writes belongs to the first of them. A rule made in a case
        # reading a composite names the composite's own id, which holds nothing of its own: it reads
        # as its case, scoped as a request is, so its alert goes into the case's analyst layer
        # (ADR-099 Amendment 15 item 2, `rule_evaluation.write_alert_node`), never the composite.
        if rule.dataset_id and not await self.datasets.composites_among([rule.dataset_id]):
            reach = [rule.dataset_id]
            deployer = deployer.model_copy(update={"datasets": reach})
            set_case_datasets(reach)
        else:
            deployer = await scope_to_case(
                deployer, rule.investigation_id, self.datasets  # type: ignore[arg-type]
            )
        gate = RuleGate(
            rules=[rule],
            investigation_id=rule.investigation_id,
            graph=self.graph,
            analytics=None,
            scheme=self.scheme,
            alert_store=self.alert_store,
            audit=self.audit,
            valkey=self.valkey,
            principal_for_owner=self.principal_for_owner,
            loader=self.runner,
        )
        context = KycContext(
            graph=self.graph, scheme=self.scheme, screening=None, compute=None,
            today=datetime.now(UTC).date(),
        )  # fmt: skip
        customers = raised = 0
        try:
            for entity_type in CUSTOMER_TYPES:
                entries = [e for e in changed if e.entity_type == entity_type]
                if not entries:
                    continue
                cursor: str | None = None
                while True:
                    page = await self.graph.list_nodes(
                        entity_type, deployer, cursor=cursor, limit=self.page_size
                    )
                    for node in page.nodes:
                        if node.properties.get("listing"):
                            continue  # a listed party, not a customer
                        customers += 1
                        dob = node.properties.get("date_of_birth")
                        born = _date(dob)
                        for hit in screen(
                            party_name(node), born, entries, min_score=params.min_score
                        ):
                            finding = await screening_finding(
                                rule, deployer, node, node, hit, context
                            )
                            if await gate.seen(finding):
                                continue
                            await gate.raise_committed(finding)
                            raised += 1
                    if page.next_cursor is None:
                        break
                    cursor = page.next_cursor
        finally:
            set_case_datasets(None)
        await self.audit.record(
            principal=self.runner,
            action="rule_evaluated",
            investigation_id=rule.investigation_id,
            resolved_query={"rule_id": rule.id, "trigger": "list_update",
                            "list_name": diff.list_name, "version": diff.version,
                            "entries": len(changed), "findings": raised},
            result_cardinality=raised,
        )  # fmt: skip
        return customers, raised


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


# --- one refresh ----------------------------------------------------------------------------------


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


async def refresh(
    list_name: str,
    *,
    store: ScreeningListStore,
    rescreen: Callable[[ListDiff], Awaitable[RescreenReport]],
    root: Path | None = None,
    manifest: Path = SYNTHETIC_MANIFEST,
    exceptions_path: Path | None = None,
    trigger: Literal["manual", "schedule"] = "manual",
) -> ScreeningListUpdate:
    """Reads, admits, parses and applies the list, re-screens against what changed, and records
    the outcome in words, with how it was started (by a person, or by the list's schedule)."""
    status = await store.subscription(list_name)
    if status is None:
        raise ListNotSubscribed(list_name)
    now = datetime.now(UTC)

    async def record(outcome: str, words: str, **counts: object) -> ScreeningListUpdate:
        update = ScreeningListUpdate(
            id=new_id(), list_name=list_name, at=now, outcome=outcome,  # type: ignore[arg-type]
            words=words, trigger=trigger, **counts,  # type: ignore[arg-type]
        )  # fmt: skip
        await store.record_update(update)
        return update

    try:
        files = read_files(status, root)
        synthetic = admit(
            files, status, await store.use_of(list_name),
            manifest=manifest, exceptions_path=exceptions_path,
        )  # fmt: skip
    except ListRefused as refused:
        return await record("refused", f"Refused: {refused}.", version=status.version)
    try:
        parsed = parse(status.source, files)
    except NormalisationError as error:
        return await record(
            "failed",
            f"The file could not be read as {status.source}: {error.reason}. The list was left "
            f"as it was (version {status.version or 'none'}).",
            version=status.version,
        )
    diff = await store.apply_update(
        list_name, parsed.version, entries_of(list_name, parsed, synthetic=synthetic),
        synthetic=synthetic,
    )  # fmt: skip
    counts = {"version": diff.version, "previous_version": diff.previous_version,
              "added": len(diff.added), "changed": len(diff.changed),
              "delisted": len(diff.removed)}  # fmt: skip
    skipped = (
        f" {_plural(parsed.skipped, 'entry', 'entries')} neither a person nor an organisation "
        "(a vessel, an aircraft or a ship) not screened."
        if parsed.skipped
        else ""
    )
    if not diff.to_screen and not diff.removed:
        return await record(
            "unchanged",
            f"Version {diff.version}: no entry changed, so no one was re-screened.{skipped}",
            **counts,
        )
    report = await rescreen(diff)
    list_words = (
        f"Version {diff.version}: {len(diff.added):,} added, {len(diff.changed):,} changed, "
        f"{len(diff.removed):,} removed.{skipped}"
    )
    words = (
        f"Version {diff.version}: {len(diff.added):,} added, {len(diff.changed):,} changed, "
        f"{len(diff.removed):,} removed. {_plural(report.customers, 'customer')} re-screened "
        f"against {_plural(len(diff.to_screen), 'changed entry', 'changed entries')}; "
        f"{_plural(report.alerts, 'alert')} raised.{skipped}"
    )
    if report.failures:
        words += " " + " ".join(f"{f[0].upper()}{f[1:]}." for f in report.failures)
    update = ScreeningListUpdate(
        id=new_id(), list_name=list_name, at=now, outcome="updated", words=words,
        trigger=trigger, rescreened=report.customers, alerts=report.alerts, **counts,  # type: ignore[arg-type]
    )  # fmt: skip
    # The whole refresh for the operator's command and the audit; each unit's own part beside it,
    # which is all a route reads (`ScreeningListStore.update_for`).
    await store.record_update(update, list_words=list_words, by_unit=report.by_unit)
    return update


__all__ = [
    "CLOSED_LISTS",
    "LICENCES",
    "LICENCE_NOT_CONFIRMED",
    "ListNotSubscribed",
    "ListRefused",
    "RescreenReport",
    "Rescreener",
    "admit",
    "check_location",
    "read_files",
    "refresh",
    "synthetic_digests",
]
