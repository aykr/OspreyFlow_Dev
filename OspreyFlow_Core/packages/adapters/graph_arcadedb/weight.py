"""Edge weight — `01_DOMAIN_MODEL.md` §6.1, ADR-120 D3 and Amendment 4.

```
weight(e) = normalise( alpha * log1p(occurrences) / log1p(heavy(type))
                       + beta * recency(interval.to) + gamma * npmi(u, v) )
```

From weights version 2 (ADR-123) gamma is 0, so a link's weight comes from the link alone: its own
occurrences and recency, or a structural type's fixed strength. No other link's count enters it,
which is what keeps a link a viewer cannot see from moving the weight of one they can (rule 3).
Version 1 (gamma 0.3) is kept, and the weights of links stored under it still carry the
mutual-information term until they are reseeded or recomputed.

`WeightComponents` still persists the raw counts the formula takes, and the adapter and the bulk
loader still gather them; at gamma 0 they move no weight. The mutual-information term below is
defined, and used only under version 1.

The parameters (alpha, beta, gamma, the half-life, `midpoint` and `scale`) and each link type's
rule (its `heavy` count, or a structural type's fixed strength) are the weights file's
(`ontology/weights.py`); nothing here holds a number the file does. A structural type weighs its
declared strength whatever its occurrences, recency or mutual information. A self-loop's
mutual-information term is 0 (Amendment 4): its weight follows its count and recency only, and the
stored inputs do not say whether a link is one, so every caller passes `self_loop`.
"""

from __future__ import annotations

import math
from datetime import datetime

from ontology.weights import WeightRules
from schemas.domain import WeightComponents


def recency(valid_to: datetime | None, *, now: datetime, rules: WeightRules) -> float:
    """`recency(t) = 0.5 ^ ((now - t) / half_life)` — exponential decay,
    halving every `half_life_days`. `valid_to=None` (no upper bound on the
    edge's interval yet) is treated as "as recent as it gets"."""
    if valid_to is None:
        return 1.0
    age_days = max((now - valid_to).total_seconds() / 86400.0, 0.0)
    return math.pow(0.5, age_days / rules.half_life_days)


def npmi(components: WeightComponents) -> float:
    """Normalised pointwise mutual information of the pair against the corpus,
    `pmi(u,v) / -ln p(u,v)` clamped to [-1, 1]. It is 1 when `p(u,v) = 1` (the pair is the whole
    corpus) and 0 wherever the corpus total, the pair count or either degree is 0.

    Defined here and used only by weights version 1 (gamma 0.3), where it suppressed a
    high-volume, low-information relationship. From version 2 gamma is 0 and the term moves no
    weight (ADR-123): it counted links a viewer cannot see, which rule 3 forbids."""
    total = components.corpus_total_occurrences
    if total == 0 or components.corpus_pair_count == 0:
        return 0.0
    p_pair = components.corpus_pair_count / total
    p_source = components.corpus_source_degree / total
    p_target = components.corpus_target_degree / total
    if p_source == 0.0 or p_target == 0.0:
        return 0.0
    if p_pair >= 1.0:
        return 1.0
    pmi = math.log(p_pair / (p_source * p_target))
    return max(-1.0, min(1.0, pmi / -math.log(p_pair)))


def normalise(raw: float, *, rules: WeightRules) -> float:
    """`normalise(x) = 1 / (1 + e^(-(x - midpoint) / scale))` — logistic, centred and scaled by the
    weights file's one deployment-wide `midpoint` and `scale`."""
    return 1.0 / (1.0 + math.exp(-(raw - rules.midpoint) / rules.scale))


def compute_weight(
    components: WeightComponents,
    *,
    edge_type: str,
    valid_to: datetime | None,
    now: datetime,
    rules: WeightRules,
    self_loop: bool,
) -> float:
    _, rule = rules.rule_for(edge_type)
    if rule.fixed is not None:
        return rule.fixed
    assert rule.heavy is not None  # the loader refuses a rule with neither
    mutual = 0.0 if self_loop else npmi(components)
    raw = (
        rules.alpha * math.log1p(components.occurrences) / math.log1p(rule.heavy)
        + rules.beta * recency(valid_to, now=now, rules=rules)
        + rules.gamma * mutual
    )
    return normalise(raw, rules=rules)
