"""The real-data exceptions mechanism `CLAUDE.md` rule 9 and `07_BUILD_PLAN.md` standing rule 3
both now reference — `06_DECISIONS.md` ADR-035 §C3 has the decision record, 23 September 2026,
the owner's own.

**The rule stays "no real intelligence data, ever" for everything this repository can see.** The
exception is narrower than the rule text alone could show: a named dataset, admitted for local
development, scale/realism testing, or an owner-run demonstration, on the owner's own secured
device only — never committed, never in CI, never distributed to an attendee. Enforcing that
narrowness needs two things working together, not one:

1. **The exceptions list never enters git.** `config/real_data_exceptions.yaml` is gitignored;
   only `config/real_data_exceptions.example.yaml` (this file's own schema, no real dataset named)
   is committed. A repository clone — this one or, eventually, the published one — never contains
   a record of which real datasets anyone has ever admitted, on any device. The owner adds their
   own entries locally, with this module's own CLI (`python -m scripts.real_data_exceptions add`),
   the shape an eventual admin-console screen (`process/07_BUILD_PLAN.md`'s own harness/packaging
   stage) would wrap, not a shortcut around one.
2. **Code that would load a named real dataset checks `is_permitted()` first and refuses if the
   entry is missing** — fail closed, the same discipline `06_DECISIONS.md` ADR-035's own
   `shipped`/`internal` packaging gate already applies to what ships. No such loader exists yet for
   any real dataset (Enron's own admission, ADR-035 §C3, is not code yet); this module is the
   mechanism whatever loader is built next must call, not a gate with nothing behind it.

**Not a CI gate, deliberately** — CI never sees real data by construction (rule 9's own "ever"
holds there absolutely), so there is nothing for a CI job to check. The gate this module provides
is a runtime one, called by whatever code path would touch a named real dataset, on the owner's
own device, at the moment it would do so.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "real_data_exceptions.yaml"
EXAMPLE_PATH = REPO_ROOT / "config" / "real_data_exceptions.example.yaml"

APPROVED_USES = ("local_development", "scale_testing", "owner_run_demonstration")

#: `06_DECISIONS.md` ADR-049 Stage 2 §6, ruling 3's own "format only" reading: "a non-empty string
#: matching an ADR reference, `ADR-` followed by three digits, optionally with a section suffix
#: (`ADR-035 §C3`)." Presence and shape are checked here; existence and resolvability are
#: deliberately not — this module never reads `06_DECISIONS.md` (see the module docstring's own
#: `is_permitted` reasoning: nothing here depends on a file this device's clone may not even have
#: at the same content, and a citation this module cannot verify is not one it should pretend to).
_DECISION_RECORD_PATTERN = re.compile(r"^ADR-\d{3}( §.+)?$")


@dataclass(frozen=True)
class RealDataException:
    """One admitted real dataset. Every field is required — a partially-filled entry is not a
    valid exception, the same "no silent gap" discipline the rest of this codebase holds itself
    to for anything access- or safety-relevant."""

    dataset: str
    approved_uses: tuple[str, ...]
    added_by: str
    added_date: date
    device: str
    justification: str
    #: `06_DECISIONS.md` ADR-049 Stage 2 §6, ruling 3 — the seventh required field, added 26
    #: September 2026. **Any entry in an existing local `config/real_data_exceptions.yaml` that
    #: predates this field is invalid until the owner adds it** — this module cannot see that
    #: gitignored file and must not try to migrate it; `load_exceptions` will raise the same
    #: `ValueError` this field's own absence raises for any other required field.
    decision_record: str
    revisit: str | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.dataset.strip():
            raise ValueError("dataset name must not be empty")
        if not self.approved_uses:
            raise ValueError(f"{self.dataset!r}: approved_uses must not be empty")
        unknown = set(self.approved_uses) - set(APPROVED_USES)
        if unknown:
            raise ValueError(
                f"{self.dataset!r}: unknown approved_uses {sorted(unknown)}; must be a subset of "
                f"{APPROVED_USES}"
            )
        if not self.added_by.strip():
            raise ValueError(f"{self.dataset!r}: added_by must not be empty")
        if not self.device.strip():
            raise ValueError(f"{self.dataset!r}: device must not be empty")
        if not self.justification.strip():
            raise ValueError(f"{self.dataset!r}: justification must not be empty")
        if not self.decision_record.strip():
            raise ValueError(f"{self.dataset!r}: decision_record must not be empty")
        if not _DECISION_RECORD_PATTERN.match(self.decision_record.strip()):
            raise ValueError(
                f"{self.dataset!r}: decision_record {self.decision_record!r} does not match "
                "'ADR-' plus three digits, optionally followed by ' §<section>' (e.g. "
                "'ADR-035' or 'ADR-035 §C3') — format checked, not resolved against "
                "06_DECISIONS.md"
            )

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RealDataException:
        added_date = raw["added_date"]
        if isinstance(added_date, str):
            added_date = date.fromisoformat(added_date)
        return cls(
            dataset=str(raw["dataset"]),
            approved_uses=tuple(raw["approved_uses"]),  # type: ignore[arg-type]
            added_by=str(raw["added_by"]),
            added_date=added_date,  # type: ignore[arg-type]
            device=str(raw["device"]),
            justification=str(raw["justification"]),
            decision_record=str(raw["decision_record"]),
            revisit=str(raw["revisit"]) if raw.get("revisit") else None,
        )

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "dataset": self.dataset,
            "approved_uses": list(self.approved_uses),
            "added_by": self.added_by,
            "added_date": self.added_date.isoformat(),
            "device": self.device,
            "justification": self.justification,
            "decision_record": self.decision_record,
        }
        if self.revisit:
            d["revisit"] = self.revisit
        return d


def load_exceptions(config_path: Path = CONFIG_PATH) -> list[RealDataException]:
    """Empty list if the file does not exist — no local exceptions configured is the default,
    fail-closed state, not an error."""
    if not config_path.exists():
        return []
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    entries = raw.get("exceptions", [])
    return [RealDataException.from_dict(e) for e in entries]


def is_permitted(dataset: str, use: str, *, config_path: Path = CONFIG_PATH) -> bool:
    """The check any code loading a named real dataset must call first, and refuse if this
    returns `False` — fail closed. Matches on `dataset` case-insensitively (a typo in casing must
    not silently deny what was actually approved, the same "not a shortcut around" reasoning
    already governs the exact-match discipline elsewhere) and requires `use` to be one of the
    entry's own `approved_uses` — an entry approved for `local_development` does not, by itself,
    permit `owner_run_demonstration`."""
    for exc in load_exceptions(config_path):
        if exc.dataset.strip().lower() == dataset.strip().lower() and use in exc.approved_uses:
            return True
    return False


def _save(entries: list[RealDataException], config_path: Path = CONFIG_PATH) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {"exceptions": [e.to_dict() for e in entries]},
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def add_exception(entry: RealDataException, *, config_path: Path = CONFIG_PATH) -> None:
    entries = load_exceptions(config_path)
    if any(e.dataset.strip().lower() == entry.dataset.strip().lower() for e in entries):
        raise ValueError(f"{entry.dataset!r} is already in the exceptions list — remove it first")
    entries.append(entry)
    _save(entries, config_path)


def remove_exception(dataset: str, *, config_path: Path = CONFIG_PATH) -> bool:
    entries = load_exceptions(config_path)
    remaining = [e for e in entries if e.dataset.strip().lower() != dataset.strip().lower()]
    if len(remaining) == len(entries):
        return False
    _save(remaining, config_path)
    return True


def _cmd_add(args: argparse.Namespace) -> int:
    entry = RealDataException(
        dataset=args.dataset,
        approved_uses=tuple(args.use),
        added_by=args.added_by,
        added_date=date.today(),
        device=args.device,
        justification=args.justification,
        decision_record=args.decision_record,
        revisit=args.revisit,
    )
    add_exception(entry)
    rel = CONFIG_PATH.relative_to(REPO_ROOT)
    print(f"Added {entry.dataset!r} to {rel} (not committed — gitignored).")
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    if remove_exception(args.dataset):
        print(f"Removed {args.dataset!r}.")
        return 0
    print(f"{args.dataset!r} was not in the exceptions list.")
    return 1


def _cmd_list(_args: argparse.Namespace) -> int:
    entries = load_exceptions()
    if not entries:
        print("No real-data exceptions configured.")
        return 0
    for e in entries:
        print(f"- {e.dataset}: {', '.join(e.approved_uses)} — added {e.added_date} by {e.added_by} "
              f"for {e.device!r}")
        print(f"  justification: {e.justification}")
        print(f"  decision_record: {e.decision_record}")
        if e.revisit:
            print(f"  revisit: {e.revisit}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.real_data_exceptions")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Admit a real dataset for local use only")
    p_add.add_argument("dataset")
    p_add.add_argument("--use", action="append", required=True, choices=APPROVED_USES)
    p_add.add_argument("--added-by", required=True)
    p_add.add_argument("--device", required=True, help="Which device this applies to (hostname)")
    p_add.add_argument("--justification", required=True)
    p_add.add_argument(
        "--decision-record",
        required=True,
        help="'ADR-' plus three digits, optionally ' §<section>' (e.g. 'ADR-035 §C3')",
    )
    p_add.add_argument("--revisit", default=None)
    p_add.set_defaults(func=_cmd_add)

    p_remove = sub.add_parser("remove", help="Withdraw a dataset's exception")
    p_remove.add_argument("dataset")
    p_remove.set_defaults(func=_cmd_remove)

    p_list = sub.add_parser("list", help="Show the current local exceptions")
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
