"""A public dataset of the administrator's choosing (`06_DECISIONS.md` ADR-138 decision 3).

    python -m scripts.public_dataset --list
    python -m scripts.public_dataset verify --manifest <dataset.yaml | id> --file <path> [--json]
    python -m scripts.public_dataset stage --manifest ... --file <path> --into <folder> [--accepted]
    python -m scripts.public_dataset pin --manifest <catalogue id> --file <path> --out <yaml>

`ospreyflow demo add public` runs `verify` (the manifest checked against `schemas.public_dataset`,
the recipe against `schemas.ingest.Recipe`, the file against the manifest's SHA-256), then asks for
any acceptance real data needs, then `stage`, then the seed (`scripts.seed_internal public`).
Nothing is placed, and nothing loads, until `verify` has passed: a checksum that differs is refused
first.

**The catalogue** is `packages/demo_fixtures/public_datasets/`: a manifest and a recipe per dataset,
never the data. A catalogue entry whose checksum nobody has recorded (OspreyFlow never downloads
VAST data) is refused by `verify` until the administrator `pin`s the file they downloaded, which
writes a manifest of their own with its checksum (ADR-138 Amendment 1).

**Real personal data** (`real_personal_data: true`) is `stage`d only with `--accepted`, which the
command passes once the person has typed `yes` (or given `--accept-real-data`), and an acceptance
record is written beside it, as for Enron (rule 9; ADR-035 §C3). It never enters a repository or CI:
the data folder is outside the checkout, and the tests use synthetic files only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from schemas.ingest import Recipe
from schemas.public_dataset import PublicDatasetManifest

CATALOGUE = Path(__file__).resolve().parents[1] / "packages" / "demo_fixtures" / "public_datasets"
#: Under the demo data folder, one folder per dataset: the file, `dataset.yaml` and `recipe.yaml`.
PUBLIC_FOLDER = "public"
STAGED_MANIFEST = "dataset.yaml"
STAGED_RECIPE = "recipe.yaml"
ACCEPTANCE_RECORD = "ACCEPTED_REAL_DATA.json"
_CHUNK = 1024 * 1024


class DatasetRefused(Exception):
    """The dataset cannot be added; the message says why and what to do."""


def catalogue() -> list[Path]:
    return sorted(CATALOGUE.glob("*.dataset.yaml"))


def find_manifest(given: str) -> Path:
    """A manifest by path, else by catalogue id."""
    path = Path(given).expanduser()
    if path.is_file():
        return path
    entry = CATALOGUE / f"{given}.dataset.yaml"
    if entry.is_file():
        return entry
    ids = ", ".join(p.name.removesuffix(".dataset.yaml") for p in catalogue())
    raise DatasetRefused(
        f"There is no manifest at {given}, and no catalogue entry of that id. The catalogue: {ids}."
    )


def load_manifest(path: Path) -> PublicDatasetManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return PublicDatasetManifest.model_validate(raw)
    except (OSError, yaml.YAMLError) as error:
        raise DatasetRefused(f"Could not read the manifest {path}: {error}") from error
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'manifest'}: {e['msg']}"
            for e in error.errors()
        )
        raise DatasetRefused(f"The manifest {path} is not valid: {problems}") from error


def recipe_path(manifest: PublicDatasetManifest, manifest_file: Path) -> Path:
    """The recipe beside the manifest, else the catalogue's of that file name."""
    for folder in (manifest_file.parent, CATALOGUE):
        candidate = folder / manifest.recipe
        if candidate.is_file():
            return candidate
    raise DatasetRefused(
        f"The manifest names the recipe {manifest.recipe}, which is neither beside it nor in the "
        "catalogue."
    )


def load_recipe(path: Path) -> Recipe:
    try:
        return Recipe.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise DatasetRefused(f"The recipe {path} is not a valid recipe: {error}") from error


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify(manifest_given: str, file: Path) -> tuple[PublicDatasetManifest, Path, Path]:
    """The manifest, its recipe and the file, each checked; returns the manifest and both paths.
    Raises `DatasetRefused`, in words, for anything that is not exactly as the manifest says."""
    manifest_file = find_manifest(manifest_given)
    manifest = load_manifest(manifest_file)
    recipe_file = recipe_path(manifest, manifest_file)
    load_recipe(recipe_file)
    if not file.is_file():
        raise DatasetRefused(
            f"There is no file at {file}. Download {manifest.file.name} from "
            f"{manifest.source_page} and try again."
        )
    if manifest.file.sha256 is None:
        raise DatasetRefused(
            f"The manifest of {manifest.name} records no checksum yet: OspreyFlow never downloads "
            "this data, so nobody has recorded one. Check your download came from "
            f"{manifest.source_page}, then record its checksum in a manifest of your own with "
            f"python -m scripts.public_dataset pin --manifest {manifest_given} --file {file} "
            "--out <your dataset.yaml>, and add that. Nothing was loaded."
        )
    if manifest.file.size_bytes is not None and file.stat().st_size != manifest.file.size_bytes:
        raise DatasetRefused(
            f"{file.name} is {file.stat().st_size:,} bytes, but the manifest expects "
            f"{manifest.file.size_bytes:,}. It may be incomplete: download it again from "
            f"{manifest.source_page}. Nothing was loaded."
        )
    actual = sha256_of(file)
    if actual != manifest.file.sha256:
        raise DatasetRefused(
            f"The SHA-256 checksum of {file.name} is {actual}, but the manifest of "
            f"{manifest.name} records {manifest.file.sha256}, so the file is not the one it "
            f"describes. Download it again from {manifest.source_page}. Nothing was loaded."
        )
    return manifest, manifest_file, recipe_file


def summary(manifest: PublicDatasetManifest) -> dict[str, object]:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "source_page": manifest.source_page,
        "licence": manifest.licence,
        "redistribution": manifest.redistribution,
        "commercial_use": manifest.commercial_use,
        "real_personal_data": manifest.real_personal_data,
        "domains": list(manifest.domains),
    }


def stage(manifest_given: str, file: Path, into: Path, *, accepted: bool) -> Path:
    """Checked again, then placed under `<into>/public/<id>/`: the file under its manifest's name,
    the manifest as `dataset.yaml` and the recipe as `recipe.yaml`. Real personal data is refused
    without `accepted`, and its acceptance recorded beside it."""
    manifest, manifest_file, recipe_file = verify(manifest_given, file)
    if manifest.real_personal_data and not accepted:
        raise DatasetRefused(
            f"{manifest.name} holds real personal data and has not been accepted: add it with "
            "ospreyflow demo add public, which says what it is and asks first. Nothing was placed."
        )
    folder = into / PUBLIC_FOLDER / manifest.id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / manifest.file.name
    if not (target.exists() and target.resolve() == file.resolve()):
        shutil.copyfile(file, target)
    shutil.copyfile(manifest_file, folder / STAGED_MANIFEST)
    shutil.copyfile(recipe_file, folder / STAGED_RECIPE)
    if manifest.real_personal_data:
        (folder / ACCEPTANCE_RECORD).write_text(
            json.dumps(
                {
                    "dataset": manifest.id,
                    "accepted": True,
                    "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "source_file": manifest.file.name,
                    "sha256": manifest.file.sha256,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return folder


def pin(manifest_given: str, file: Path, out: Path) -> Path:
    """A copy of a manifest with the checksum and size of the file the administrator downloaded
    recorded in it, written to `out` (never over the catalogue's own)."""
    manifest_file = find_manifest(manifest_given)
    manifest = load_manifest(manifest_file)
    if not file.is_file():
        raise DatasetRefused(f"There is no file at {file}.")
    if out.resolve().parent == CATALOGUE.resolve():
        raise DatasetRefused("Write your pinned manifest outside the catalogue folder.")
    raw = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
    raw["file"] = {**raw["file"], "name": file.name, "sha256": sha256_of(file),
                   "size_bytes": file.stat().st_size}  # fmt: skip
    # The recipe travels with the pinned manifest, so it loads from wherever the copy is kept.
    recipe_file = recipe_path(manifest, manifest_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    if recipe_file.parent != out.parent:
        shutil.copyfile(recipe_file, out.parent / manifest.recipe)
    out.write_text(
        f"# Pinned from {manifest_file.name} on {datetime.now(UTC).date().isoformat()}: the "
        "checksum of the file you downloaded.\n" + yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )
    load_manifest(out)
    return out


def _list() -> int:
    for path in catalogue():
        manifest = load_manifest(path)
        print(f"{manifest.id}: {manifest.name}")
        print(f"  source: {manifest.source_page}")
        print(
            f"  redistribution: {manifest.redistribution}; commercial use: "
            f"{manifest.commercial_use}; fictional: {'yes' if manifest.fictional else 'no'}; "
            f"real personal data: {'YES' if manifest.real_personal_data else 'no'}"
        )
        pinned = "recorded" if manifest.file.sha256 else "not recorded: pin your download first"
        print(f"  file: {manifest.file.name} (checksum {pinned})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.public_dataset")
    parser.add_argument("--list", action="store_true", help="the catalogue")
    actions = parser.add_subparsers(dest="action")
    for name in ("verify", "stage", "pin"):
        action = actions.add_parser(name)
        action.add_argument("--manifest", required=True)
        action.add_argument("--file", type=Path, required=True)
        if name == "verify":
            action.add_argument("--json", action="store_true")
        if name == "stage":
            action.add_argument("--into", type=Path, required=True)
            action.add_argument("--accepted", action="store_true")
        if name == "pin":
            action.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.list or args.action is None:
        return _list()
    try:
        file = args.file.expanduser()
        if args.action == "verify":
            manifest, _m, _r = verify(args.manifest, file)
            if args.json:
                print(json.dumps(summary(manifest)))
            else:
                print(f"{file} is the file the manifest of {manifest.name} names.")
        elif args.action == "stage":
            folder = stage(args.manifest, file, args.into.expanduser(), accepted=args.accepted)
            print(f"Placed in {folder}.")
        else:
            out = pin(args.manifest, file, args.out.expanduser())
            print(f"Wrote {out}, with the checksum of {file.name}. Add it with ospreyflow demo "
                  f"add public --file {file} --manifest {out}")  # fmt: skip
    except DatasetRefused as refusal:
        # `--json` is read by the command, which keeps standard output only: the refusal goes there.
        json_mode = args.action == "verify" and args.json
        print(refusal, file=sys.stdout if json_mode else sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
