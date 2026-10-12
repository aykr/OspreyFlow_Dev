"""Seeds an internal demo through the product's own seed runner (`scripts/seed_internal.py`), with
this folder's code mounted read-only beside the product's (`spec/06_DECISIONS.md` ADR-114
Amendment 2). Every check the runner makes applies unchanged: a real dataset is refused without
its entry in the owner's local exceptions list, and only ever seeded from a checkout.

    cd OspreyFlow_Core && PYTHONPATH=.:packages:../OspreyFlow_Build \\
        .venv/bin/python -m internal_demos.seed enron --stop-api      # or: make seed-enron
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.seed_internal import DATASETS, Dataset, main

HERE = Path(__file__).resolve().parent
#: Where this folder is mounted in the seed's container, so `internal_demos.*` imports from `/app`.
CONTAINER_CODE = "/app/internal_demos"

ENRON = Dataset(
    script="internal_demos.seed_enron",
    case_name="Enron corpus (real data, this machine only)",
    data_folder="Enron_Mails",
    real_dataset="enron",
    bulk=True,
    rewrites_links=True,
)

#: The product's datasets with the internal ones added.
DATASETS_WITH_INTERNAL: dict[str, Dataset] = {**DATASETS, "enron": ENRON}
CODE_MOUNTS: tuple[tuple[Path, str], ...] = ((HERE, CONTAINER_CODE),)


def run(argv: list[str] | None = None) -> int:
    return main(argv, datasets=DATASETS_WITH_INTERNAL, code_mounts=CODE_MOUNTS)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
