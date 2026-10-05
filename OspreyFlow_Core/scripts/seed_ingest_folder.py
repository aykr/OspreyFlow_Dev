"""Write the synthetic demo source files into a deployment's ingest folder — round 13c.

**The gap this closes.** `05_DEPLOYMENT.md` §3 and `DEMO_GUIDE.md` §3.7a both told an operator to
copy source files into `components.storage.ingest` before opening the Ingest Studio, and
`DEMO_GUIDE.md` named the command outright:

    sudo cp tests/scenarios/fixtures/files/*.csv /var/lib/osprey/ingest/

**`tests/scenarios/fixtures/files/` has never existed.** The CDR fixture is *generated*
(`packages/demo_fixtures/cdr.py`), never stored as a CSV, so the documented procedure copies
nothing and fails. Found on the closing pass, installing from a fresh clone and following the
documentation as written rather than from memory — the same way round 13 found §3's missing
`PYTHONPATH` line, and the same way round 13bd found §3.7a's `mint_dev_token` step 403ing.

`tests/scenarios/test_phase8_exit_over_the_wire.py`'s own B1-B3 fixture had the matching false
claim in its failure message ("the harness places it"). Nothing placed it; I had put the file
there by hand the round before and not noticed that made the test unrunnable anywhere else.

**Why the rows are imported rather than written out here.** `CLAUDE.md` rule 9 requires fixtures
to be synthetic and in-repo, and `packages/demo_fixtures/cdr.py` already is exactly that,
deterministically (`seed=42`). Copying its rows into this module would be a second definition of
one fixture — which is the defect round 13bf spent itself removing from connector availability,
and it would drift the first time either side changed. The generator stays the single source; this
module only decides *where the bytes land*.

Run as the project's other operational modules are (`CLAUDE.md`'s conventions — no `osprey` CLI
yet):

    PYTHONPATH=.:packages .venv/bin/python -m scripts.seed_ingest_folder \\
      --ingest-root /var/lib/osprey/ingest

With `--osprey-config` it reads the root from a rendered deployment's own config instead of being
told. **It never writes to the config**, which `DEMO_GUIDE.md` §3.6 warns about after
`build_local_basemap` rewrote a committed `osprey.yaml`.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

from demo_fixtures.cdr import generate_cdr_rows
from demo_fixtures.phone_extraction import write_phone_extraction
from demo_fixtures.seizure_record import SEIZURE_CSV_COLUMNS, generate_seizure_rows
from demo_fixtures.sms import FIELDS as SMS_FIELDS
from demo_fixtures.sms import generate_sms_rows

#: The name `08_ACCEPTANCE_SCENARIOS.md`'s B1-B3 and the over-the-wire test both expect. Changing
#: it breaks `test_b1_…`/`test_b2_…`/`test_b3_…`, which look the file up by name — that coupling
#: is deliberate and is what makes this module's output load-bearing rather than decorative.
CDR_FIXTURE_NAME = "carrier-a-cdr.csv"
#: ADR-094 step 1: the same carrier's messages, with their text.
SMS_FIXTURE_NAME = "carrier-a-sms.csv"

#: The exhibit schedule B13 ingests to fire a hotlist alert — round 13cdb. Named here for the same
#: reason the CDR file is: the over-the-wire cases select it from the Studio's own listing by name.
SEIZURE_FIXTURE_NAME = "seizure-record.csv"

#: The default in `packages/schemas/deployment.py` and `05_DEPLOYMENT.md` §3.
DEFAULT_INGEST_ROOT = "/var/lib/osprey/ingest"


def write_sms_fixture(ingest_root: Path) -> Path:
    """Write the synthetic SMS export (ADR-094 step 1), returning the path written."""
    ingest_root.mkdir(parents=True, exist_ok=True)
    destination = ingest_root / SMS_FIXTURE_NAME
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SMS_FIELDS))
        writer.writeheader()
        writer.writerows(generate_sms_rows())
    return destination


def write_cdr_fixture(ingest_root: Path) -> Path:
    """Write the synthetic CDR export, returning the path written.

    The column order is the generator's own, taken from the first row rather than restated here —
    a hardcoded field list would silently drop a column the generator later adds, and the recipe
    that maps this file would then fail on a missing field with no indication of why.
    """
    rows = generate_cdr_rows()
    if not rows:
        raise ValueError("the CDR generator produced no rows")

    ingest_root.mkdir(parents=True, exist_ok=True)
    destination = ingest_root / CDR_FIXTURE_NAME
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return destination


def write_seizure_fixture(ingest_root: Path) -> Path:
    """Write the seizure record `08_ACCEPTANCE_SCENARIOS.md` B13 ingests — round 13cdb.

    B13 is worded "**ingest** the later seizure record", so it is performed through the Studio
    rather than seeded into the graph (`09_INGEST_STUDIO.md`'s own rule), and that needs the
    record to exist as a file a connector reads. `connectors/seizure-record-csv.yaml` is the
    layout; these are its rows.

    The identifiers come from `seizure_record.py`, the same module `scenario_cohorts.py` takes
    the seeded handset's IMEI from, so the ingest and the device already in the graph are the
    same handset. Minting them separately would give B13 an alert on a device B15 never pivots
    on — two fixtures that both look right.
    """
    rows = generate_seizure_rows()
    if not rows:
        raise ValueError("the seizure-record generator produced no rows")

    ingest_root.mkdir(parents=True, exist_ok=True)
    destination = ingest_root / SEIZURE_FIXTURE_NAME
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SEIZURE_CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return destination


def ingest_root_from_config(config_path: Path) -> Path:
    """The `components.storage.ingest` a rendered deployment is using.

    Read-only, deliberately — see this module's docstring on §3.6.
    """
    document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    storage = (document.get("components") or {}).get("storage") or {}
    return Path(storage.get("ingest") or DEFAULT_INGEST_ROOT)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--ingest-root",
        type=Path,
        help=f"where to write the files (default: {DEFAULT_INGEST_ROOT})",
    )
    source.add_argument(
        "--osprey-config",
        type=Path,
        help="read components.storage.ingest from this deployment config instead",
    )
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    if args.osprey_config is not None:
        ingest_root = ingest_root_from_config(args.osprey_config)
        print(f"ingest root from {args.osprey_config}: {ingest_root}")
    else:
        ingest_root = args.ingest_root or Path(DEFAULT_INGEST_ROOT)

    try:
        written = [
            write_cdr_fixture(ingest_root),
            write_sms_fixture(ingest_root),
            write_seizure_fixture(ingest_root),
        ]
        # ADR-094 step 3: a phone extraction whose photos, video and notes the phones hold.
        extraction, left_out = write_phone_extraction(ingest_root)
        written.append(extraction)
    except PermissionError:
        # The documented default lives under /var, which an ordinary user cannot create. Say so
        # by name rather than letting a traceback stand in for an instruction.
        print(
            f"cannot write to {ingest_root} — run with sudo, or pass --ingest-root pointing "
            "somewhere writable and set components.storage.ingest to match",
            file=sys.stderr,
        )
        return 1

    for path in written:
        print(f"wrote {path} ({path.stat().st_size} bytes)")
    for note in left_out:
        print(f"not made: {note}")
    print(
        "The Ingest Studio's Connect stage will now list them. Map the CDR with the "
        "`cdr-generic-csv` connector — it declares `date_order: dmy`, which that file's own dates "
        "need — the SMS export with the `csv` connector, marking its `text` column as the "
        "message's text, the phone extraction (in its own folder) marking photo, video and note "
        "as content the phone holds, and the seizure record with `seizure-record-csv`."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return _run(_parse_args(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
