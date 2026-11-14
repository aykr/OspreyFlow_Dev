# ruff: noqa: E501
"""Step 4's record, RESULTS.md, made from the live gate's results (each case writes one JSON into the
folder `OSPREY_MEASURE_RESULTS` names: `tests/perf/test_search_budget_live.py`) and the run's facts.

Every one of ADR-149 Amendment 2's measures has a row, its figures read from the amendment's own
table (never typed here). A measure with no result says so ("not measured"), never "met" (rule 2);
one measured elsewhere names where. Run on the stack's host after the live gate:

    OspreyFlow_Core/.venv/bin/python OspreyFlow_Build/process/lanes/platform/v052-measure/results_table.py \\
      --results <folder> --run <run id> --stack d --lease "<holder, since>" --commit <sha> > RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
#: Each measure: what it is, and where its result comes from when not from the live gate.
MEASURES: tuple[tuple[str, str, str], ...] = (
    ("M1", "Suggestions, 2–6 characters, the largest loaded type", ""),
    ("M2", "Suggestions in the Glass, last key to the list", "a perf/ case in a browser slot"),
    ("M3", "Name search (typos, variants, sounds-like)", ""),
    ("M4", "Full text with the passage highlighted", ""),
    ("M5", "An exact identifier ranked first", ""),
    ("M6", "The feed's lag: a drawn node to searchable", ""),
    ("M7", "Rebuild from the graph, B's whole load", "the restore's rebuild, timed"),
    ("M8", "Drift check, B's whole load", "its Job's peak and time"),
    ("M9", "The fallback: OpenSearch stopped mid-session", ""),
    ("M10", "The leak test at scale (m10-part)", ""),
    ("M11", "Each container's peak working set during M1–M8", "the cluster's metrics"),
)


def amendment_figures() -> dict[str, tuple[str, str]]:
    """Each measure's budget and failure figure as ADR-149 Amendment 2's table gives them (its timed
    rows held to `measure_search.BUDGETS` both ways by `tests/test_measure_search.py`)."""
    text = (ROOT / "OspreyFlow_Build/spec/06_DECISIONS.md").read_text(encoding="utf-8")
    start = text.index("### ADR-149, Amendment 2 ")
    end = text.find("\n### ", start + 1)
    found: dict[str, tuple[str, str]] = {}
    for line in text[start : end if end > 0 else len(text)].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[0].startswith("M") and cells[0][1:].isdigit():
            found[cells[0]] = (cells[3], cells[4])
    return found


def figures(measure: str) -> tuple[str, str]:
    return amendment_figures().get(measure, ("(not in the amendment)", "(not in the amendment)"))


def row(measure: str, what: str, elsewhere: str, result: dict[str, Any] | None) -> str:
    budget, fail = figures(measure)
    if result is None:
        found = f"not measured here: {elsewhere}" if elsewhere else "**not measured**"
        return f"| {measure} | {what} | {budget} | {fail} | — | — | — | {found} |"
    if "p95_ms" in result:
        timing = f"{result['p50_ms']:g} / {result['p95_ms']:g} / {result['max_ms']:g} ms"
        n = str(result.get("n", ""))
    elif "timings" in result:
        times = [t["ms"] for t in result["timings"]]
        timing = f"max {max(times):g} ms" if times else "—"
        n = str(len(times))
    else:
        timing, n = "—", str(result.get("cases", ""))
    verdict = result.get("verdict", "not measured")
    why = result.get("why") or "; ".join(result.get("failures", [])[:3])
    said = f"**{verdict}**" + (f": {why}" if why else "")
    return f"| {measure} | {what} | {budget} | {fail} | {timing} | {n} | {result.get('class', '')} | {said} |"


def render(results: dict[str, dict[str, Any]], facts: dict[str, str]) -> str:
    lines = [
        "# v0.5.2 step 4: search measured on B's load (ADR-149 Amendment 2)",
        "",
        f"- **Run:** {facts.get('run') or '(to be filled in)'}",
        f"- **Stack and lease:** {facts.get('stack') or '(to be filled in)'}, "
        f"{facts.get('lease') or '(to be filled in)'} (rule 14: a figure taken without the lease is "
        "not a measurement)",
        f"- **The scripts' commit:** {facts.get('commit') or '(to be filled in)'}",
        "- **The load:** B, about 281,000 Persons. The owner's tens-of-millions figure is not measured "
        '(the owner\'s ruling of 13 November, "measure what is loaded").',
        "- **Known difference:** the stores on the host's loopback, unsigned and without TLS; SigV4 "
        "measured at about 35 µs per request; TLS and the network to the endpoint not measured "
        "(ADR-149 Amendment 2).",
        "",
        "| Measure | What | Budget | Failure figure | p50 / p95 / max | n | Class | Result |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [row(m, what, where, results.get(m)) for m, what, where in MEASURES]
    lines += ["", "A result between the budget and the failure figure is over budget, not failed; past the "
              "failure figure, step 4 fails (ADR-149 Amendment 2)."]  # fmt: skip
    return "\n".join(lines) + "\n"


def load(folder: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("M*.json")) if folder.is_dir() else []:
        found[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="results_table.py", description=__doc__)
    parser.add_argument("--results", type=Path)
    for fact in ("run", "stack", "lease", "commit"):
        parser.add_argument(f"--{fact}", default="")
    args = parser.parse_args(argv)
    results = load(args.results) if args.results else {}
    sys.stdout.write(
        render(results, {f: getattr(args, f) for f in ("run", "stack", "lease", "commit")})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
