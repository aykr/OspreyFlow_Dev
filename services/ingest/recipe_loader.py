"""Loads a versioned recipe YAML file — `09_INGEST_STUDIO.md` §6. Publishing
writes the recipe to version control, not only to a database; loading it
back is this one function, used identically whether the file was
hand-written or produced by the studio (Phase 5a, ADR-018)."""

from __future__ import annotations

from pathlib import Path

import yaml

from schemas.ingest import Recipe


def load_recipe(path: str | Path) -> Recipe:
    raw = yaml.safe_load(Path(path).read_text())
    return Recipe.model_validate(raw)
