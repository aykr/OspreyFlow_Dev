"""Operation Ledger — the synthetic financial-fraud fixture (ADR-108 Amendment 4; rule 9:
synthetic, in-repo, never real). A structuring ring in the West Midlands: twenty-six cash
deposits, each under the £10,000 reporting threshold, paid into a shell company's account by
three money mules over eleven banking days; £84,000 moved to a second shell within 48 hours of
the last deposit; £82,500 invoiced back to the ringleader's real firm. Ordinary trading noise
runs alongside so the timeline reads as a drumbeat inside normal activity, not a lone bar chart.

Everything loads through the real engine from the four `ledger_*_recipe.yaml` templates — FIBO
`Account`s found again by number, temporal `TRANSACTED` links whose events feed the timeline, the
SAR narrative as held content the reader opens — plus a handful of direct writes for what no
single source row carries: the ring's associations, NAIR's role, the carter home, and HALE's
*inferred* control of the shell (rule 5: model-derived, drawn dashed until a person confirms it).

The phone number is an Ofcom drama-range MSISDN; every name, company, account and address is
invented; the coordinates are real places only so the local basemap has something true to draw
under synthetic markers (tier 1 data only, rule 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ports.graph import GraphPort
from ports.media import MediaStore
from schemas.analytics import EventRecord, GeometryKind, GeometryRecord
from schemas.domain import (
    EdgeWrite,
    Handling,
    NodeWrite,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

FIXTURES = Path(__file__).parent
INVESTIGATION_SCOPE = "ledger-fixture"
SOURCE = "ledger-fixture"

_HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-fincrime", owning_unit="verify"
)

#: The geometry partition's rows and the `geometry_ref` strings the nodes carry — minted here,
#: opaque everywhere else. Real places under synthetic markers (tier 1 only).
POINTS: dict[str, tuple[float, float]] = {
    "ledger:colmore-row": (-1.9005, 52.4809),  # Brightpath's mail-forwarding office, Birmingham
    "ledger:pleck": (-1.9994, 52.5743),  # Hale Logistics' depot, Walsall
    "ledger:fenchurch": (-0.0807, 51.5119),  # Crescent Imports, London
    "ledger:dunstall": (-2.1416, 52.5848),  # CARTER's home, Wolverhampton
    "ledger:branch-birmingham": (-1.8988, 52.4802),
    "ledger:branch-london": (-0.0792, 51.5126),
    "ledger:branch-walsall": (-1.9979, 52.5736),
    "ledger:branch-wolverhampton": (-2.1301, 52.5852),
    # ADR-109 phase C: the layered structure's registered offices (real towns, invented firms).
    "ledger:road-town": (-64.6208, 18.4286),  # Road Town, Tortola, British Virgin Islands
    "ledger:limassol": (33.0413, 34.6786),  # Limassol, Cyprus
}

SAR_TEXT = (
    "Suspicious activity report, 12 September 2026. Over eleven banking days, twenty-six cash "
    "deposits of between £9,400 and £9,850 were made into the Barclays account of Brightpath "
    "Consulting Ltd, each below the £10,000 reporting threshold, at branches in Birmingham, "
    "Walsall and Wolverhampton. The deposits were made by Jamal Carter, Sofia Ruiz and Tomas "
    "Zelinsky. Within 48 hours of the final deposit, £84,000 was transferred to Crescent Imports "
    "Ltd, and £82,500 returned to Hale Logistics Ltd against invoice CI-2026-118 for logistics "
    "services. The sole listed director of Brightpath Consulting Ltd is Elena Petrov; branch "
    "staff state the account was opened in the company of Marcus Hale, who was contactable on "
    "07700 900461 and m.hale@halelogistics.example.co.uk. The registered office, Suite 14, 83 "
    "Colmore Row, Birmingham, is a mail-forwarding address."
)

#: iban -> (institution, display name, branch geometry ref)
ACCOUNTS: dict[str, tuple[str, str, str]] = {
    "GB29 NWBK 6016 1331 9268 19":
        ("NatWest", "Hale Logistics · NatWest …68 19", "ledger:branch-walsall"),
    "GB94 BARC 2003 5538 2998 12":
        ("Barclays", "Brightpath · Barclays …98 12", "ledger:branch-birmingham"),
    "GB33 HBUK 4012 7612 3456 01":
        ("HSBC", "Crescent · HSBC …56 01", "ledger:branch-london"),
    "GB58 LOYD 3096 1700 7099 43":
        ("Lloyds", "Carter · Lloyds …99 43", "ledger:branch-wolverhampton"),
    "GB82 MONZ 0400 0412 8831 22":
        ("Monzo", "Ruiz · Monzo …31 22", "ledger:branch-walsall"),
    "GB21 SRLG 6083 0199 2204 87":
        ("Starling", "Zelinsky · Starling …04 87", "ledger:branch-wolverhampton"),
    "GB44 NWBK 6016 1331 7700 02":
        ("NatWest", "Kesterton Freight · NatWest …00 02", "ledger:branch-walsall"),
    "GB17 BARC 2003 5538 4411 09":
        ("Barclays", "Midland Pallets · Barclays …11 09", "ledger:branch-birmingham"),
    "GB63 HBUK 4012 7612 9902 44":
        ("HSBC", "Arden Fuel Cards · HSBC …02 44", "ledger:branch-birmingham"),
}

HALE_BIZ = "GB29 NWBK 6016 1331 9268 19"
BRIGHTPATH_ACC = "GB94 BARC 2003 5538 2998 12"
CRESCENT_ACC = "GB33 HBUK 4012 7612 3456 01"
MULE_ACCOUNTS = {
    "Carter": "GB58 LOYD 3096 1700 7099 43",
    "Ruiz": "GB82 MONZ 0400 0412 8831 22",
    "Zelinsky": "GB21 SRLG 6083 0199 2204 87",
}
TRADING_ACCOUNTS = [
    "GB44 NWBK 6016 1331 7700 02",
    "GB17 BARC 2003 5538 4411 09",
    "GB63 HBUK 4012 7612 9902 44",
]


def _kyc(
    family: str, given: str, dob: str, iban: str, phone: str = "", email: str = ""
) -> dict[str, str]:
    institution, name, branch = ACCOUNTS[iban]
    return {
        "family_name": family, "given_names": given, "date_of_birth": dob, "iban": iban,
        "institution": institution, "account_name": name, "branch_geometry_ref": branch,
        "phone": phone, "email": email,
    }


def kyc_rows() -> list[dict[str, str]]:
    return [
        _kyc(
            "Hale", "Marcus", "1981-03-07", HALE_BIZ,
            "07700 900461", "m.hale@halelogistics.example.co.uk",
        ),
        _kyc("Carter", "Jamal", "1999-11-23", MULE_ACCOUNTS["Carter"]),
        _kyc("Ruiz", "Sofia", "2001-06-14", MULE_ACCOUNTS["Ruiz"]),
        _kyc("Zelinsky", "Tomas", "1997-01-30", MULE_ACCOUNTS["Zelinsky"]),
        # NAIR and PETROV hold no account in this export; they arrive via the direct writes below
        # and the companies register. The three trading counterparties give the timeline its noise.
    ]


def company_rows() -> list[dict[str, str]]:
    def row(name: str, number: str, iban: str, office: str, office_ref: str,
            owner: str = "", percent: str = "", given: str = "") -> dict[str, str]:
        institution, account_name, branch = ACCOUNTS[iban]
        return {
            "company_name": name, "company_number": number, "iban": iban,
            "institution": institution, "account_name": account_name, "branch_geometry_ref": branch,
            "office_name": office, "office_geometry_ref": office_ref,
            "owner_family_name": owner, "owner_given_names": given, "owner_percent": percent,
        }

    return [
        row("Hale Logistics Ltd", "09418821", HALE_BIZ,
            "Unit 6, Pleck Industrial Estate, Walsall", "ledger:pleck", "Hale", "100", "Marcus"),
        row("Brightpath Consulting Ltd", "14092733", BRIGHTPATH_ACC,
            "Suite 14, 83 Colmore Row, Birmingham", "ledger:colmore-row", "Petrov", "100", "Elena"),
        row("Crescent Imports Ltd", "13550917", CRESCENT_ACC,
            "Level 2, 71 Fenchurch Street, London", "ledger:fenchurch"),
        row("Kesterton Freight Ltd", "08771204", TRADING_ACCOUNTS[0],
            "Kesterton Yard, Darlaston Road, Walsall", "ledger:branch-walsall"),
        row("Midland Pallets Ltd", "07012985", TRADING_ACCOUNTS[1],
            "Bordesley Green Trading Estate, Birmingham", "ledger:branch-birmingham"),
        row("Arden Fuel Cards Ltd", "10233471", TRADING_ACCOUNTS[2],
            "Fort Dunlop, Birmingham", "ledger:branch-birmingham"),
    ]


def ownership_rows() -> list[dict[str, str]]:
    """ADR-109 phase C: who stands behind Crescent Imports — a BVI holding company, a Cyprus trust
    owned by PETROV and NAIR, a nominee holding an unstated share, and a cross-holding that makes
    a circle. `link_kind` says which link each row writes: a person's or a company's, with a
    stated share or without (an empty percentage is never written as one)."""

    def row(owned: str, link_kind: str, owner_company: str = "", owner_person: str = "",
            percent: str = "", office: str = "", office_ref: str = "") -> dict[str, str]:
        return {
            "owned_company": owned, "link_kind": link_kind, "owner_company": owner_company,
            "owner_person": owner_person, "percent": percent, "office_name": office,
            "office_geometry_ref": office_ref,
        }

    return [
        row("Tamarind Holdings Ltd", "company_owns", owner_company="Aegean Fiduciary Trust",
            percent="70", office="Craigmuir Chambers, Road Town, Tortola",
            office_ref="ledger:road-town"),
        row("Crescent Imports Ltd", "company_owns", owner_company="Tamarind Holdings Ltd",
            percent="90"),
        row("Aegean Fiduciary Trust", "person_owns", owner_person="Petrov", percent="60",
            office="Agiou Andreou 12, Limassol", office_ref="ledger:limassol"),
        row("Aegean Fiduciary Trust", "person_owns", owner_person="Nair", percent="40"),
        row("Crescent Imports Ltd", "person_owns", owner_person="Petrov", percent="10"),
        row("Aegean Fiduciary Trust", "company_owns", owner_company="Tamarind Holdings Ltd",
            percent="15"),
        row("Tamarind Holdings Ltd", "company_owns_unstated",
            owner_company="Kestrel Nominees Ltd"),
    ]  # fmt: skip


#: Day of September -> how many sub-threshold deposits landed (sums to twenty-six; the gaps are
#: the weekends the SAR's "eleven banking days" steps over).
STRUCTURING_DAYS: list[tuple[int, int]] = [
    (1, 2), (2, 3), (3, 3), (5, 3), (8, 3), (9, 3), (10, 3), (11, 3), (12, 3),
]
STRUCTURED_DEPOSITS = sum(count for _, count in STRUCTURING_DAYS)
#: Rotating sub-threshold amounts; every one in the SAR's £9,400–£9,850 band.
_DEPOSIT_AMOUNTS = ["9400", "9750", "9600", "9850", "9500", "9700", "9450", "9800", "9550"]


def transaction_rows() -> list[dict[str, str]]:
    """The deposits, the two large transfers, and ordinary trading — in time order."""
    rows: list[dict[str, str]] = []
    mules = list(MULE_ACCOUNTS.values())
    deposit_index = 0
    for day, count in STRUCTURING_DAYS:
        for n in range(count):
            rows.append({
                "payer_iban": mules[deposit_index % len(mules)],
                "payee_iban": BRIGHTPATH_ACC,
                "amount": _DEPOSIT_AMOUNTS[deposit_index % len(_DEPOSIT_AMOUNTS)],
                "at": f"2026-09-{day:02d}T{9 + 2 * n:02d}:{12 + 7 * n:02d}:00Z",
                "transaction_type": "CASH_IN",
            })
            deposit_index += 1
    assert deposit_index == STRUCTURED_DEPOSITS
    rows.append({
        "payer_iban": BRIGHTPATH_ACC, "payee_iban": CRESCENT_ACC,
        "amount": "84000", "at": "2026-09-13T16:20:00Z", "transaction_type": "TRANSFER",
    })
    rows.append({
        "payer_iban": CRESCENT_ACC, "payee_iban": HALE_BIZ,
        "amount": "82500", "at": "2026-09-14T09:10:00Z", "transaction_type": "TRANSFER",
    })
    # Ordinary trading, August into late September: clients pay Hale Logistics weekly; it pays
    # its suppliers — the background the drumbeat stands out of.
    for week, day in enumerate((3, 10, 17, 24, 31, 7, 21, 28)):
        month = 8 if week < 5 else 9
        rows.append({
            "payer_iban": TRADING_ACCOUNTS[week % 3], "payee_iban": HALE_BIZ,
            "amount": str(11800 + 900 * (week % 4)),
            "at": f"2026-{month:02d}-{day:02d}T11:05:00Z", "transaction_type": "PAYMENT",
        })
        rows.append({
            "payer_iban": HALE_BIZ, "payee_iban": TRADING_ACCOUNTS[(week + 1) % 3],
            "amount": str(3400 + 650 * (week % 5)),
            "at": f"2026-{month:02d}-{day:02d}T15:40:00Z", "transaction_type": "PAYMENT",
        })
    rows.sort(key=lambda row: row["at"])
    return rows


def sar_rows() -> list[dict[str, str]]:
    return [{"company_name": "Brightpath Consulting Ltd", "sar_text": SAR_TEXT}]


def geometry_records() -> list[GeometryRecord]:
    return [
        GeometryRecord(
            geometry_ref=ref, version=1, kind=GeometryKind.POINT,
            lon=lon, lat=lat, source_crs="EPSG:4326", source_x=lon, source_y=lat,
            handling=_HANDLING,
        )
        for ref, (lon, lat) in POINTS.items()
    ]


@dataclass
class LedgerGraphResult:
    events: list[EventRecord]
    sar_document_id: str | None
    transactions_loaded: int


async def build_ledger_graph(
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    principal: Principal,
    investigation_scope: str = INVESTIGATION_SCOPE,
    load_id_prefix: str = "load-ledger",
    media: MediaStore | None = None,
) -> LedgerGraphResult:
    """Runs the four recipes in dependency order (people before the register that references its
    owners; accounts before the transactions that find them again), then the direct writes no
    single source row carries. One transaction per recipe, committed before the next — the same
    `find_node`-visibility reasoning `hmp_graph._run_structural_recipes` records. The SAR recipe
    runs only when a media store is given (its text lives there, never in the graph)."""
    events: list[EventRecord] = []
    sar_document_id: str | None = None
    transactions = 0

    recipe_runs: list[tuple[str, list[dict[str, str]]]] = [
        ("ledger_kyc_recipe.yaml", kyc_rows()),
        ("ledger_companies_recipe.yaml", company_rows()),
        ("ledger_transactions_recipe.yaml", transaction_rows()),
    ]
    if media is not None:
        recipe_runs.append(("ledger_sar_recipe.yaml", sar_rows()))

    for recipe_file, rows in recipe_runs:
        recipe = load_recipe(FIXTURES / recipe_file)
        tx = await graph.begin_transaction()
        try:
            report, recipe_events = await run_recipe(
                recipe, rows, graph=graph, ontology=ontology, tx=tx, principal=principal,
                load_id=f"{load_id_prefix}-{recipe.id}",
                investigation_scope=investigation_scope,
                source=f"{SOURCE}:{recipe.id}", media=media,
            )
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        if report.rejections:
            await graph.rollback_transaction(tx)
            raise AssertionError(f"{recipe_file} rejected rows: {report.rejections}")
        await graph.commit_transaction(tx)
        events.extend(recipe_events)
        if recipe.id == "ledger-transactions":
            transactions = report.rows_read
        if recipe.id == "ledger-sar":
            sar_document_id = next(
                (node_id for node_id in report.created_node_ids if node_id.startswith("content:")),
                None,
            )

    await _direct_writes(graph, principal, load_id_prefix)
    # ADR-109 phase C: the layered structure, after the people it names exist (NAIR is a direct
    # write).
    recipe = load_recipe(FIXTURES / "ledger_ownership_recipe.yaml")
    tx = await graph.begin_transaction()
    try:
        report, _ = await run_recipe(
            recipe, ownership_rows(), graph=graph, ontology=ontology, tx=tx, principal=principal,
            load_id=f"{load_id_prefix}-{recipe.id}", investigation_scope=investigation_scope,
            source=f"{SOURCE}:{recipe.id}",
        )
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    if report.rejections:
        await graph.rollback_transaction(tx)
        raise AssertionError(f"ledger_ownership_recipe.yaml rejected rows: {report.rejections}")
    await graph.commit_transaction(tx)
    return LedgerGraphResult(
        events=events, sar_document_id=sar_document_id, transactions_loaded=transactions
    )


async def _direct_writes(graph: GraphPort, principal: Principal, load_id_prefix: str) -> None:
    """What no single source row carries: NAIR and PETROV as people, the ring's associations,
    NAIR's role, CARTER's home — and HALE's control of Brightpath, written *inferred* with its
    extractor named, never asserted (rule 5)."""
    now = now_utc()
    asserted = Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id=SOURCE, locator="direct", excerpt_hash="")],
        first_seen=now,
    )

    def node(node_type: str, properties: dict[str, object]) -> NodeWrite:
        return NodeWrite(
            id=new_node_id(), type=node_type, properties=properties, provenance=asserted,
            handling=_HANDLING, created_by=principal.id, created_at=now,
            load_id=f"{load_id_prefix}-direct",
        )

    tx = await graph.begin_transaction()
    try:
        # PETROV is the companies register's own (Brightpath's owner): found, never made twice —
        # a second node would split her ownership between two (ADR-109 phase C found it).
        nair = node("Person", {"family_name": "Nair", "given_names": "Priya"})
        home = node(
            "Location", {"name": "Dunstall Road, Wolverhampton", "geometry_ref": "ledger:dunstall"}
        )
        (nair_id, home_id) = await graph.upsert_nodes([nair, home], tx)

        async def need(node_type: str, key: str, value: str) -> str:
            found = await graph.find_node(node_type, key, value, principal)
            if found is None:
                raise AssertionError(f"{node_type} {value!r} missing before the direct writes")
            return found.id

        hale = await need("Person", "family_name", "Hale")
        carter = await need("Person", "family_name", "Carter")
        ruiz = await need("Person", "family_name", "Ruiz")
        zelinsky = await need("Person", "family_name", "Zelinsky")
        hale_logistics = await need("Organisation", "name", "Hale Logistics Ltd")
        brightpath = await need("Organisation", "name", "Brightpath Consulting Ltd")

        def edge(edge_type: str, source: str, target: str,
                 properties: dict[str, object] | None = None,
                 provenance: Provenance = asserted) -> EdgeWrite:
            return EdgeWrite(
                id=new_edge_id(), type=edge_type, source=source, target=target,
                properties=properties or {}, provenance=provenance, handling=_HANDLING,
                created_by=principal.id, created_at=now, load_id=f"{load_id_prefix}-direct",
            )

        inferred = Provenance(
            state=ProvenanceState.INFERRED,
            sources=[SourceRef(document_id=SOURCE, locator="sar:2026-0412", excerpt_hash="")],
            extracted_by="model:spacy:en_core_web_sm-3.8.0",
            extraction_confidence=0.82,
            first_seen=now,
        )
        await graph.upsert_edges(
            [
                edge("ASSOCIATE_OF", hale, nair_id),
                edge("ASSOCIATE_OF", hale, carter),
                edge("ASSOCIATE_OF", carter, ruiz),
                edge("ASSOCIATE_OF", carter, zelinsky),
                edge("MEMBER_OF", nair_id, hale_logistics),
                edge("PRESENT_AT", carter, home_id),
                # The SAR's own finding, kept honest: control inferred, not asserted.
                edge("CONTROLS", hale, brightpath, {"capacity": "de facto"}, inferred),
            ],
            tx,
        )
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    await graph.commit_transaction(tx)
