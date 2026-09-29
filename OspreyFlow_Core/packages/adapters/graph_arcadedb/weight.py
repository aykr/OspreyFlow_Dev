"""Edge weight — `01_DOMAIN_MODEL.md` §6.1.

`weight` is derived at load time from corpus-wide counts gathered from the
store itself, but it is a load-time *snapshot*, never frozen ground truth:
the pointwise-mutual-information term depends on how the whole corpus
looks, which changes as more data loads and again when a caller scopes the
same formula to a working set rather than the full corpus. `WeightComponents`
persists the raw counts the formula needs alongside the derived float, so a
later, more scoped recompute is arithmetic over stored numbers, never a
full corpus rescan — Phase 3's working-set service is the caller that does
that recompute; this module only has to make it possible.

`recency` and `normalise` are both defined by §6.1 itself now (they were
not when this module was first written — see the git history of the doc
if it matters). `midpoint`/`scale` are stated as "calibrated per corpus";
no calibration procedure exists yet, so `WeightConfig`'s defaults
(`midpoint=0.0`, `scale=1.0` — an uncalibrated standard logistic) are a
placeholder, not a corpus calibration, and should be treated as one:
revisit when something actually calibrates them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from schemas.domain import WeightComponents


@dataclass(frozen=True)
class WeightConfig:
    #: `01_DOMAIN_MODEL.md` §6.1's stated defaults.
    alpha: float = 0.5
    beta: float = 0.2
    gamma: float = 0.3
    half_life_days: float = 90.0
    #: "Calibrated per corpus" — nothing calibrates them yet. See the
    #: module docstring: these are an uncalibrated placeholder, not a
    #: deployment default in the sense alpha/beta/gamma are.
    midpoint: float = 0.0
    scale: float = 1.0


def recency(valid_to: datetime | None, *, now: datetime, config: WeightConfig) -> float:
    """`recency(t) = 0.5 ^ ((now - t) / half_life)` — exponential decay,
    halving every `half_life_days`. `valid_to=None` (no upper bound on the
    edge's interval yet) is treated as "as recent as it gets"."""
    if valid_to is None:
        return 1.0
    age_days = max((now - valid_to).total_seconds() / 86400.0, 0.0)
    return math.pow(0.5, age_days / config.half_life_days)


def mutual_information(components: WeightComponents) -> float:
    """Pointwise mutual information of the pair against the corpus — what
    suppresses a high-volume, low-information relationship: the broadcast
    sender, the service number everyone calls."""
    total = components.corpus_total_occurrences
    if total == 0 or components.corpus_pair_count == 0:
        return 0.0
    p_pair = components.corpus_pair_count / total
    p_source = components.corpus_source_degree / total
    p_target = components.corpus_target_degree / total
    if p_source == 0.0 or p_target == 0.0:
        return 0.0
    return math.log(p_pair / (p_source * p_target))


def normalise(raw: float, *, config: WeightConfig) -> float:
    """`normalise(x) = 1 / (1 + e^(-(x - midpoint) / scale))` — logistic,
    centred and scaled per `config` rather than the standard logistic."""
    return 1.0 / (1.0 + math.exp(-(raw - config.midpoint) / config.scale))


def compute_weight(
    components: WeightComponents,
    *,
    valid_to: datetime | None,
    now: datetime,
    config: WeightConfig = WeightConfig(),
) -> float:
    raw = (
        config.alpha * math.log1p(components.occurrences)
        + config.beta * recency(valid_to, now=now, config=config)
        + config.gamma * mutual_information(components)
    )
    return normalise(raw, config=config)
