"""One digest from the image plan to the values (the D2c guide's finding (b), ADR-148 decision 8).

The cloud-platform install renders twice: first `--allow-unpinned`, since our images are not in
the namespace's registry until `ospreyflow images push` puts them there, then pinned. The push
copies each third-party image by the digest its plan (`images.yaml`) names, so the pinned render
must pin that digest, not whatever the image's tag points at by then. `carried_resolver` answers
each reference the previous plan copied by the digest it copied, and asks the registry for the rest.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from harness.images import DigestResolver, ImageRef


def carried_resolver(previous_plan: Path, fallback: DigestResolver) -> DigestResolver:
    copied: dict[str, str] = {}
    if previous_plan.is_file():
        plan = yaml.safe_load(previous_plan.read_text(encoding="utf-8")) or {}
        for image in plan.get("images") or []:
            reference, _, digest = str(image.get("source", "")).partition("@")
            if reference and digest:
                copied[reference] = digest

    def resolve(image: ImageRef) -> str | None:
        return copied.get(image) or fallback(image)

    return resolve
