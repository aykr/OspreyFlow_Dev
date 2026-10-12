"""Demo packs through the command (ADR-114 decision 5; Amendment 3 decision 4).

A pack is seeded by the product's own `scripts.seed_internal`; PaySim, which is a download rather
than generated, is checked by `scripts.demo_packs verify` before anything else starts.
"""

from __future__ import annotations

import filecmp
import shutil
from collections.abc import Mapping
from pathlib import Path

from .home import CommandRefused, python_for
from .run import Capture, Runner, StepFailed

#: The pack id each pack is seeded under in `scripts.seed_internal.DATASETS`.
PACK_KEYS = {
    "hmp": "hmp",
    "fixture-corp": "fixture-corp",
    "operation-ledger": "ledger",
    "paysim": "paysim",
}
#: PaySim's source page. A test holds this to the pack's own `source_page`.
PAYSIM_SOURCE_PAGE = "https://www.kaggle.com/datasets/ealaxi/paysim1"
PAYSIM_FOLDER = "PaySIM_Dataset"


def demo_data_root(product: Path, env: Mapping[str, str], *, home: Path | None = None) -> Path:
    """Where demo data lives: `OSPREYFLOW_DEMO_DATA`, else an `OspreyFlow_Data` beside the product
    (the developer layout, as `scripts.seed_internal` has it), else `~/OspreyFlow/demo-data`."""
    chosen = env.get("OSPREYFLOW_DEMO_DATA")
    if chosen:
        return Path(chosen).expanduser()
    sibling = product.parent / "OspreyFlow_Data"
    if sibling.is_dir():
        return sibling
    return (home or Path.home()) / "OspreyFlow" / "demo-data"


def pack_ids(product: Path, capture: Capture) -> tuple[str, ...]:
    """The packs this checkout offers, asked of the checkout itself."""
    code, output = capture([*python_for(product), "-m", "scripts.demo_packs", "--ids"], cwd=product)
    if code != 0:
        raise CommandRefused(
            "This checkout could not list its demo packs (scripts.demo_packs --ids failed). "
            "Is the checkout complete, and has `uv sync` been run in it?"
        )
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def list_packs(product: Path, run: Runner) -> int:
    return run([*python_for(product), "-m", "scripts.demo_packs"], cwd=product)


def _place(file: Path, root: Path) -> Path:
    destination = root / PAYSIM_FOLDER / file.name
    if destination.exists() and destination.resolve() == file.resolve():
        return destination
    if destination.is_file() and filecmp.cmp(file, destination, shallow=False):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file, destination)
    return destination


def add_pack(
    product: Path, run: Runner, env: Mapping[str, str], pack: str, file: Path | None = None
) -> None:
    """Seed `pack` into its own case. Raises `CommandRefused` before anything starts when the
    request cannot be honoured, and `StepFailed` when a step it ran exits non-zero."""
    if pack not in PACK_KEYS:
        raise CommandRefused(
            f"There is no demo pack called '{pack}'. The packs are: {', '.join(PACK_KEYS)}."
        )
    python = python_for(product)
    root = demo_data_root(product, env)
    if pack == "paysim":
        if file is None:
            raise CommandRefused(
                "PaySim is a download, not generated: give its file with --file PATH. The release "
                "asset that ospreyflow fetches for you arrives with stage B5; until then download "
                f"the file from {PAYSIM_SOURCE_PAGE} and pass it here."
            )
        file = file.expanduser()
        verify = [*python, "-m", "scripts.demo_packs", "verify", "paysim", str(file)]
        code = run(verify, cwd=product)
        if code != 0:
            raise StepFailed("check the PaySim file", code)
        _place(file, root)
    code = run(
        [*python, "-m", "scripts.seed_internal", PACK_KEYS[pack], "--stop-api"],
        env={"OSPREYFLOW_DEMO_DATA": str(root)},
        cwd=product,
    )
    if code != 0:
        raise StepFailed(f"load the {pack} demo pack", code)
