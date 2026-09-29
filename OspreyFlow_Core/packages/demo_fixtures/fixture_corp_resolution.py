"""The one resolution pass Fixture Corp has — used by the seed and by the §C5 test alike.

**Why this module exists** (round 12e, 27 September 2026). `scripts/seed_fixture_corp.py` and
`tests/scenarios/test_fixture_corp_shape.py` each assembled their own call: take
`generate_resolution_persons()`, flatten it to ten nodes, look up the `Person` entity type, hand
both to `resolve_entity_type`. Same function, same population, same answer — but assembled twice,
with nothing keeping them that way. A change to either call site (a different population, a
different entity type, a filter) would have made the test measure one thing and the demo another,
silently, and the test would have gone on passing.

That is not hypothetical here. Round 12d spent an afternoon on the belief that exactly this had
happened, and the belief was only wrong by luck: the two call sites did still agree. `CLAUDE.md`
rule 15 and STANDING.md's own rule of 27 September — "a test that measures something the real
system does not do is not evidence" — are what this module answers, by removing the second call
site rather than documenting that it matches.

`ADR_035_C5_SCORES` makes the same move for the numbers: ADR-035 §C5 records them in prose, and
prose cannot be checked. `test_fixture_corp_shape.py` asserts the live pass reproduces this dict,
so the ADR's own figures now have a test behind them.
"""

from __future__ import annotations

from functools import lru_cache

from services.resolve.resolver import SameAsCandidate, resolve_entity_type

from ontology.loader import load_default_ontology
from schemas.domain import EntityTypeDef

from .fixture_corp import ResolutionPair, generate_resolution_persons

#: ADR-035 §C5's recorded match scores, by the pair label `generate_resolution_persons` gives.
#:
#: Measured against the real, untrained Splink configuration this ontology declares for `Person`
#: — `jaro_winkler(family_name)`/`levenshtein(given_names)`/`exact(date_of_birth)`, blocked on
#: `soundex(family_name)`/`year(date_of_birth)` — and re-measured bit-for-bit in rounds 12b and
#: 12e. These are **match scores** (`properties["score"]` on the written `SAME_AS` edge, what
#: `services/resolve/projection.py` collapses components on), not edge `weight`, which is
#: `01_DOMAIN_MODEL.md` §6.1's load-time strength formula and has nothing to do with resolution.
#: Round 12d conflated the two; the distinction is spelled out here so it cannot be read wrongly
#: from this file.
ADR_035_C5_SCORES: dict[str, float] = {
    "identical": 0.999991,
    "close_given_name": 0.981285,
    "close_surname_and_given": 0.867624,
    "shared_surname_different_person": 0.0001,
    "identical_non_latin_script": 0.999991,
}


@lru_cache(maxsize=1)
def person_entity_type() -> EntityTypeDef:
    return next(e for e in load_default_ontology().entity_types if e.name == "Person")


def resolve_fixture_corp_pairs() -> list[SameAsCandidate]:
    """Runs the real resolver over exactly the ten pair nodes, and nothing else.

    The population is load-bearing: Splink's scores depend on the set being resolved, so
    "the five pairs, alone" is part of what §C5's numbers mean. Any caller wanting a different
    population is doing something else and should say so at its own call site."""
    pairs = generate_resolution_persons()
    nodes = [p.node_a for p in pairs] + [p.node_b for p in pairs]
    return resolve_entity_type(nodes, person_entity_type())


def scores_by_pair_label() -> dict[str, float | None]:
    """The same pass, keyed by pair label — `None` for a pair the resolver never scored at all
    (the negative control's own expected shape, since Splink need not emit a candidate for it)."""
    pairs: list[ResolutionPair] = generate_resolution_persons()
    candidates = resolve_fixture_corp_pairs()
    out: dict[str, float | None] = {}
    for pair in pairs:
        ids = {pair.node_a.id, pair.node_b.id}
        out[pair.label] = next(
            (c.score for c in candidates if {c.node_a, c.node_b} == ids), None
        )
    return out
