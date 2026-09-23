"""Synthetic population and relationship rows for the HMP fixture's graph
side — `08_ACCEPTANCE_SCENARIOS.md` Scenario A's "a population of ~400
person entities with wing and cell locations; a subset with recorded
group affiliations and family relationships."

Deterministic (`CLAUDE.md` rule 9): every row list below is built from
fixed seeded choices — two calls to any function here produce
byte-identical output, the same discipline `hmp.py`'s own
`generate_hmp_events` already follows.

Three named individuals carry the Scenario A narrative deliberately, not
by chance — a fixture cannot demonstrate "the principal subject ranks
first" (A8) or a discoverable relay group (A12) if nothing in the data
actually has that shape:

- **`PRINCIPAL_SUBJECT_PRISON_NUMBER`** — `hmp_graph.py` gives this person
  a deliberately elevated share of incidents and structured-report
  mentions, concentrated in the hotspot yards and peak hours.
- **`SECOND_SUBJECT_PRISON_NUMBER`** — family-linked to the principal
  (A10), on a different wing, with prior-period incidents outside the
  fixture's normal window (`hmp_graph.py`'s own `PRIOR_PERIOD_EVENTS`,
  A10/A11).
- **`RELAY_GROUP_PRISON_NUMBERS`** — eight persons connected to each other
  far more densely than to anyone else, and sharing one `Organisation`
  membership. This is a real graph topology (a near-complete subgraph
  among the eight, one sparse external bridge each), not a label — the
  substrate the Clique Metric needs, computed only once Phase 7 builds
  `ComputePort`. A12/the metric itself is not verified here; only that
  the fixture actually has the shape to verify later, rather than
  discovering only in Phase 7 that it never did.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

TOTAL_PERSONS = 400
WINGS = 8
PERSONS_PER_WING = TOTAL_PERSONS // WINGS

PRINCIPAL_SUBJECT_INDEX = 0
SECOND_SUBJECT_INDEX = 1
RELAY_GROUP_INDICES: tuple[int, ...] = tuple(range(2, 10))  # eight persons

_FAMILY_NAMES = (
    "OKAFOR", "SZYMANSKI", "MARSH", "DELACROIX", "NKOSI", "FERREIRA", "MULCAHY", "IVANOV",
    "BOATENG", "PETROVA", "WHITFIELD", "RASHID", "COSTELLO", "ADEYEMI", "HALVORSEN", "BENNETT",
    "ZIMMERMAN", "OYELARAN", "MCALLISTER", "SANTOS", "KOWALSKI", "OSEI", "DUBOIS", "HARRINGTON",
    "NAKAMURA", "FITZGERALD", "ABARA", "WOZNIAK", "KEEGAN", "MBEKI",
)
_GIVEN_NAMES = (
    "Callum", "Aisha", "Marek", "Nadia", "Femi", "Gabriela", "Declan", "Yusuf",
    "Rosa", "Kwame", "Ingrid", "Tariq", "Siobhan", "Anton", "Naledi", "Lukas",
    "Priya", "Oisin", "Chidi", "Ewa", "Rafael", "Amara", "Bartosz", "Nia",
)


def prison_number_for_index(index: int) -> str:
    return f"HMP-{index + 1:04d}"


@dataclass(frozen=True)
class PersonRow:
    prison_number: str
    family_name: str
    given_names: str
    date_of_birth: str  # ISO date, string — every recipe row field is a string
    wing: int
    cell_site_ref: str
    cell_name: str


def generate_persons(seed: int = 42) -> list[PersonRow]:
    rng = random.Random(seed)
    persons: list[PersonRow] = []
    for index in range(TOTAL_PERSONS):
        wing = (index % WINGS) + 1
        cell_number = (index // WINGS) + 1
        family_name = _FAMILY_NAMES[index % len(_FAMILY_NAMES)]
        # A different stride than family_name's, so the same (family, given)
        # pairing does not repeat every len(_FAMILY_NAMES) persons.
        given_names = _GIVEN_NAMES[(index * 7) % len(_GIVEN_NAMES)]
        birth_year = rng.randint(1975, 2006)
        birth_month = rng.randint(1, 12)
        birth_day = rng.randint(1, 28)
        persons.append(
            PersonRow(
                prison_number=prison_number_for_index(index),
                family_name=family_name,
                given_names=given_names,
                date_of_birth=date(birth_year, birth_month, birth_day).isoformat(),
                wing=wing,
                cell_site_ref=f"wing-{wing}-cell-{cell_number:03d}",
                cell_name=f"Wing {wing}, Cell {cell_number}",
            )
        )
    return persons


PRINCIPAL_SUBJECT_PRISON_NUMBER = prison_number_for_index(PRINCIPAL_SUBJECT_INDEX)
SECOND_SUBJECT_PRISON_NUMBER = prison_number_for_index(SECOND_SUBJECT_INDEX)
RELAY_GROUP_PRISON_NUMBERS: tuple[str, ...] = tuple(
    prison_number_for_index(i) for i in RELAY_GROUP_INDICES
)


def person_rows_as_dicts(persons: list[PersonRow]) -> list[dict[str, str]]:
    return [
        {
            "prison_number": p.prison_number,
            "family_name": p.family_name,
            "given_names": p.given_names,
            "date_of_birth": p.date_of_birth,
            "cell_site_ref": p.cell_site_ref,
            "cell_name": p.cell_name,
        }
        for p in persons
    ]


#: The ten yards `hmp.py`'s own `_YARD_COUNTS` already names — a `Location`
#: per yard letter, same identifiers everywhere else in this fixture uses.
YARD_LETTERS: tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")


def yard_rows_as_dicts() -> list[dict[str, str]]:
    return [
        {"site_ref": f"yard-{letter.lower()}", "name": f"Yard {letter}"} for letter in YARD_LETTERS
    ]


def generate_family_rows(persons: list[PersonRow], seed: int = 42) -> list[dict[str, str]]:
    """Principal <-> second subject (A10) plus a modest number of other
    family pairs among the general population, for a graph that has more
    than one deliberately-placed edge in it."""
    rng = random.Random(seed)
    by_index = {i: p for i, p in enumerate(persons)}
    rows = [
        {
            "person_a_prison_number": by_index[PRINCIPAL_SUBJECT_INDEX].prison_number,
            "person_a_family_name": by_index[PRINCIPAL_SUBJECT_INDEX].family_name,
            "person_a_given_names": by_index[PRINCIPAL_SUBJECT_INDEX].given_names,
            "person_b_prison_number": by_index[SECOND_SUBJECT_INDEX].prison_number,
            "person_b_family_name": by_index[SECOND_SUBJECT_INDEX].family_name,
            "person_b_given_names": by_index[SECOND_SUBJECT_INDEX].given_names,
            "relation": "brother",
        }
    ]
    excluded = (PRINCIPAL_SUBJECT_INDEX, SECOND_SUBJECT_INDEX)
    general_pool = [i for i in range(len(persons)) if i not in excluded]
    rng.shuffle(general_pool)
    used: set[int] = set()
    relations = ("sister", "father", "cousin", "brother", "uncle")
    pair_count = 15
    pool_iter = iter(general_pool)
    for i in range(pair_count):
        a = next(pool_iter)
        while a in used:
            a = next(pool_iter)
        b = next(pool_iter)
        while b in used or b == a:
            b = next(pool_iter)
        used.add(a)
        used.add(b)
        rows.append(
            {
                "person_a_prison_number": by_index[a].prison_number,
                "person_a_family_name": by_index[a].family_name,
                "person_a_given_names": by_index[a].given_names,
                "person_b_prison_number": by_index[b].prison_number,
                "person_b_family_name": by_index[b].family_name,
                "person_b_given_names": by_index[b].given_names,
                "relation": relations[i % len(relations)],
            }
        )
    return rows


#: Two organisations: the relay group's own (its membership *is* the
#: group A8/A12 need discoverable), and an unrelated second one purely for
#: realism, so "group affiliations" is not a synonym for "the one
#: narrative group" throughout the fixture.
RELAY_ORG_REF = "org-relay-crew"
RELAY_ORG_NAME = "The Wing Crew"
OUTER_ORG_REF = "org-outer-circle"
OUTER_ORG_NAME = "Outer Circle"


def generate_group_rows(persons: list[PersonRow], seed: int = 42) -> list[dict[str, str]]:
    rng = random.Random(seed)
    by_index = {i: p for i, p in enumerate(persons)}
    rows: list[dict[str, str]] = []
    for i in RELAY_GROUP_INDICES:
        rows.append(
            {
                "prison_number": by_index[i].prison_number,
                "family_name": by_index[i].family_name,
                "given_names": by_index[i].given_names,
                "org_ref": RELAY_ORG_REF,
                "org_name": RELAY_ORG_NAME,
            }
        )
    excluded = set(RELAY_GROUP_INDICES) | {PRINCIPAL_SUBJECT_INDEX, SECOND_SUBJECT_INDEX}
    general_pool = [i for i in range(len(persons)) if i not in excluded]
    rng.shuffle(general_pool)
    for i in general_pool[:10]:
        rows.append(
            {
                "prison_number": by_index[i].prison_number,
                "family_name": by_index[i].family_name,
                "given_names": by_index[i].given_names,
                "org_ref": OUTER_ORG_REF,
                "org_name": OUTER_ORG_NAME,
            }
        )
    return rows


def generate_associate_rows(persons: list[PersonRow], seed: int = 42) -> list[dict[str, str]]:
    """A near-complete subgraph among the relay group (every pair
    connected — `density(v) = 1.0` for each member) plus exactly one
    sparse external bridge per member, so the group is embedded in the
    wider population rather than a suspiciously isolated island."""
    rng = random.Random(seed)
    by_index = {i: p for i, p in enumerate(persons)}
    rows: list[dict[str, str]] = []
    for a_pos, a in enumerate(RELAY_GROUP_INDICES):
        for b in RELAY_GROUP_INDICES[a_pos + 1 :]:
            rows.append(
                {
                    "person_a_prison_number": by_index[a].prison_number,
                    "person_a_family_name": by_index[a].family_name,
                    "person_a_given_names": by_index[a].given_names,
                    "person_b_prison_number": by_index[b].prison_number,
                    "person_b_family_name": by_index[b].family_name,
                    "person_b_given_names": by_index[b].given_names,
                }
            )
    excluded = set(RELAY_GROUP_INDICES) | {PRINCIPAL_SUBJECT_INDEX, SECOND_SUBJECT_INDEX}
    outsiders = [i for i in range(len(persons)) if i not in excluded]
    rng.shuffle(outsiders)
    for member, outsider in zip(RELAY_GROUP_INDICES, outsiders, strict=False):
        rows.append(
            {
                "person_a_prison_number": by_index[member].prison_number,
                "person_a_family_name": by_index[member].family_name,
                "person_a_given_names": by_index[member].given_names,
                "person_b_prison_number": by_index[outsider].prison_number,
                "person_b_family_name": by_index[outsider].family_name,
                "person_b_given_names": by_index[outsider].given_names,
            }
        )
    return rows


TOTAL_REPORTS = 229
STRUCTURED_REPORTS = 68


def generate_report_rows(persons: list[PersonRow], seed: int = 42) -> list[dict[str, str]]:
    """229 rows, 68 of which name a mentioned person (`when: not_null` in
    `hmp_reports_recipe.yaml` gates the `MENTIONED_IN` edge on this field
    being present) — mentions deliberately concentrated on the principal
    subject, the second subject and the relay group, the same bias
    `hmp_graph.py`'s incident assignment applies, so the two analytical
    paths (reports and incidents) agree on who matters."""
    rng = random.Random(seed)
    by_index = {i: p for i, p in enumerate(persons)}

    mentioned_indices: list[int] = [PRINCIPAL_SUBJECT_INDEX] * 12 + [SECOND_SUBJECT_INDEX] * 4
    for i in RELAY_GROUP_INDICES:
        mentioned_indices.extend([i] * 2)
    excluded = set(RELAY_GROUP_INDICES) | {PRINCIPAL_SUBJECT_INDEX, SECOND_SUBJECT_INDEX}
    general_pool = [i for i in range(len(persons)) if i not in excluded]
    rng.shuffle(general_pool)
    remaining = STRUCTURED_REPORTS - len(mentioned_indices)
    assert remaining > 0
    mentioned_indices.extend(general_pool[:remaining])
    assert len(mentioned_indices) == STRUCTURED_REPORTS

    rows: list[dict[str, str]] = []
    for report_index in range(TOTAL_REPORTS):
        report_ref = f"hmp-report-{report_index:04d}"
        if report_index < STRUCTURED_REPORTS:
            mentioned = by_index[mentioned_indices[report_index]]
            rows.append(
                {
                    "report_ref": report_ref,
                    "title": f"Security report {report_index + 1:04d}",
                    "mentioned_prison_number": mentioned.prison_number,
                    "mentioned_family_name": mentioned.family_name,
                    "mentioned_given_names": mentioned.given_names,
                }
            )
        else:
            rows.append(
                {
                    "report_ref": report_ref,
                    "title": f"Incident log {report_index + 1:04d}",
                    "mentioned_prison_number": "",
                    "mentioned_family_name": "",
                    "mentioned_given_names": "",
                }
            )
    return rows
