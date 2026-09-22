"""Probability-yardstick loader — `docs/01_DOMAIN_MODEL.md` §5, `06_DECISIONS.md` ADR-046's own
Stage 4b scope. "Probability bands come from a configured yardstick file, not from the codebase"
(§5) — the exact `load_handling_scheme` shape (`packages/ontology/handling.py`), applied to a
different YAML directory. Swapping `phia.yaml` for a different organisation's own scale, or
revising the bands in place, is a config change with nothing above this module to touch.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from .errors import YardstickError

_YARDSTICK_DIR = Path(__file__).resolve().parent / "yardstick"


class YardstickBand(BaseModel):
    label: str
    lower: float
    upper: float


class Yardstick(BaseModel):
    name: str
    bands: list[YardstickBand]

    def labels(self) -> list[str]:
        return [band.label for band in self.bands]


def load_yardstick(path: str | Path) -> Yardstick:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise YardstickError(f"{path}: yardstick must be a YAML mapping")
    try:
        return Yardstick.model_validate(raw)
    except ValidationError as exc:
        raise YardstickError(f"{path}: {exc}") from exc


def load_phia_yardstick() -> Yardstick:
    return load_yardstick(_YARDSTICK_DIR / "phia.yaml")


__all__ = ["Yardstick", "YardstickBand", "load_phia_yardstick", "load_yardstick"]
