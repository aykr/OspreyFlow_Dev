"""Writes the client-size synthetic dataset to a folder (ROUTE_052 step B, `v052-load`).

    python -m scripts.generate_client_size --out DIR [--scale 1.0] [--graph-scale 0.25]
                                           [--seed 20261116] [--jobs N]

Plain generation: no store, no network. `--out` must be outside the git working tree (the files
are tens of GB and never committed), so a path inside the repository is refused before anything is
written, as `scripts.write_pid_files` refuses one.

**What it writes** (`client_size_plan` has the sources; `process/lanes/rules/v052-load/DESIGN.md`
the sizes): for each of the twelve sources a folder of part files, one per stream and part:
`<stream>-<part>.nodes.jsonl`, `.edges.jsonl`, `.texts.jsonl` (a document's full text) and
`.events.csv` (rows for the analytics store); `same_as/<plant>.jsonl`, the planted merge
candidates, each with its truth (`same` or `different`); and `manifest.json`, which lists every
file with its rows, bytes and SHA-256, the seed, both scales and each source's dataset and marking.
Nothing in it depends on the time or the machine, so the same arguments write the same bytes,
however many jobs run.

`--scale` sizes the analytics rows (60 million calls, 15 million payments and 25 million
sightings at 1.0); `--graph-scale` (default: `--scale`) sizes everything bound for the graph, which
the graph's write path bounds (DESIGN.md, "Wall time").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from scripts import client_size_plan as plan
from scripts.write_pid_files import inside_repository

_KINDS = ("nodes", "edges", "texts", "events")
_SUFFIX = {
    "nodes": ".nodes.jsonl",
    "edges": ".edges.jsonl",
    "texts": ".texts.jsonl",
    "events": ".events.csv",
}
EVENTS_HEADER = ",".join(plan.EVENT_COLUMNS) + "\n"


@dataclass
class _Sink:
    """One output file, opened on its first row, hashed as it is written."""

    path: Path
    header: str = ""
    handle: IO[bytes] | None = None
    rows: int = 0
    size: int = 0

    def __post_init__(self) -> None:
        self.digest = hashlib.sha256()

    def write(self, line: str) -> None:
        if self.handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = self.path.open("wb")
            if self.header:
                self._raw(self.header)
        self._raw(line)
        self.rows += 1

    def _raw(self, text: str) -> None:
        data = text.encode()
        assert self.handle is not None
        self.handle.write(data)
        self.digest.update(data)
        self.size += len(data)

    def close(self) -> dict[str, Any] | None:
        if self.handle is None:
            return None
        self.handle.close()
        return {"rows": self.rows, "bytes": self.size, "sha256": self.digest.hexdigest()}


def _json(row: dict[str, Any]) -> str:
    return json.dumps(row, separators=(",", ":"), ensure_ascii=False, sort_keys=True) + "\n"


def write_stream_part(
    out: str,
    seed: int,
    scale: float,
    graph_scale: float,
    source_key: str,
    stream_name: str,
    part: int,
    start: int,
    stop: int,
) -> list[dict[str, Any]]:
    """Writes one part of one stream; returns its manifest entries."""
    ctx = plan.Context(seed, scale, graph_scale)
    source = plan.SOURCES_BY_KEY[source_key]
    stream = next(s for s in source.streams if s.name == stream_name)
    stem = Path(out) / source_key / f"{stream_name}-{part:05d}"
    sinks = {
        kind: _Sink(
            stem.with_name(stem.name + _SUFFIX[kind]), EVENTS_HEADER if kind == "events" else ""
        )
        for kind in _KINDS
    }
    for rows in plan.build_part(ctx, source, stream, start, stop):
        for record in rows.nodes:
            sinks["nodes"].write(_json(record))
        for record in rows.edges:
            sinks["edges"].write(_json(record))
        for record in rows.texts:
            sinks["texts"].write(_json(record))
        for line in rows.events:
            sinks["events"].write(line)
    entries = []
    for kind, sink in sinks.items():
        closed = sink.close()
        if closed is not None:
            entries.append(
                {
                    "path": str(sink.path.relative_to(out)),
                    "source": source_key,
                    "stream": stream_name,
                    "part": part,
                    "kind": kind,
                    **closed,
                }
            )
    return entries


def write_same_as(
    out: str, seed: int, scale: float, graph_scale: float, name: str
) -> list[dict[str, Any]]:
    ctx = plan.Context(seed, scale, graph_scale)
    build = dict(plan.same_as_plants(ctx))[name]
    sink = _Sink(Path(out) / "same_as" / f"{name}.jsonl")
    for row in build():
        sink.write(_json(row))
    closed = sink.close()
    if closed is None:
        return []
    return [
        {
            "path": str(sink.path.relative_to(out)),
            "source": "same_as",
            "stream": name,
            "part": 0,
            "kind": "same_as",
            **closed,
        }
    ]


def tasks(seed: int, scale: float, graph_scale: float) -> list[tuple[Any, ...]]:
    ctx = plan.Context(seed, scale, graph_scale)
    found: list[tuple[Any, ...]] = []
    for source in plan.SOURCES:
        for stream in source.streams:
            for part, start, stop in plan.stream_parts(ctx, stream):
                found.append(("stream", source.key, stream.name, part, start, stop))
    for name, _build in plan.same_as_plants(ctx):
        found.append(("same_as", name))
    return found


def _run_task(
    out: str, seed: int, scale: float, graph_scale: float, task: tuple[Any, ...]
) -> list[dict[str, Any]]:
    if task[0] == "stream":
        return write_stream_part(out, seed, scale, graph_scale, *task[1:])
    return write_same_as(out, seed, scale, graph_scale, task[1])


def manifest(
    seed: int, scale: float, graph_scale: float, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    files = sorted(entries, key=lambda e: e["path"])
    totals: dict[str, int] = {}
    for entry in files:
        totals[entry["kind"]] = totals.get(entry["kind"], 0) + entry["rows"]
    by_source: dict[str, dict[str, int]] = {}
    for entry in files:
        counts = by_source.setdefault(entry["source"], {})
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + entry["rows"]
        counts["bytes"] = counts.get("bytes", 0) + entry["bytes"]
    return {
        "generator_version": plan.GENERATOR_VERSION,
        "seed": seed,
        "scale": scale,
        "graph_scale": graph_scale,
        "same_as_model": plan.SAME_AS_MODEL,
        "sources": [
            {
                "key": s.key,
                "dataset": s.dataset,
                "name": s.name,
                "description": s.description,
                "marking": s.marking.as_dict(),
                "counts": by_source.get(s.key, {}),
            }
            for s in plan.SOURCES
        ],
        "same_as": by_source.get("same_as", {}),
        "totals": {**totals, "bytes": sum(e["bytes"] for e in files)},
        "files": files,
    }


def generate(
    out: Path, *, seed: int, scale: float, graph_scale: float, jobs: int = 1, say: Any = print
) -> dict[str, Any]:
    """Writes everything under `out` and returns the manifest (also written as manifest.json)."""
    out.mkdir(parents=True, exist_ok=True)
    work = tasks(seed, scale, graph_scale)
    say(f"  generating {len(work):,} files' worth of parts into {out} with {jobs} job(s)")
    started = time.monotonic()
    entries: list[dict[str, Any]] = []
    if jobs <= 1:
        for task in work:
            entries += _run_task(str(out), seed, scale, graph_scale, task)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(_run_task, str(out), seed, scale, graph_scale, t) for t in work]
            for done, future in enumerate(futures, 1):
                entries += future.result()
                if done % 50 == 0 or done == len(futures):
                    say(
                        f"  {done:,} of {len(futures):,} parts written "
                        f"({int(time.monotonic() - started)}s)"
                    )
    result = manifest(seed, scale, graph_scale, entries)
    (out / "manifest.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return result


def summary(result: dict[str, Any]) -> str:
    lines = [
        f"{'source':<14}{'dataset':<18}{'marking':<26}{'nodes':>11}{'links':>11}"
        f"{'texts':>9}{'events':>13}{'MB':>9}"
    ]
    for s in result["sources"]:
        c = s["counts"]
        m = s["marking"]
        lines.append(
            f"{s['key']:<14}{s['dataset']:<18}"
            f"{m['classification'] + '/' + m['handling_code'] + ' ' + m['owning_unit']:<26}"
            f"{c.get('nodes', 0):>11,}{c.get('edges', 0):>11,}{c.get('texts', 0):>9,}"
            f"{c.get('events', 0):>13,}{c.get('bytes', 0) / 1e6:>9,.1f}"
        )
    t = result["totals"]
    lines.append(f"same_as: {result['same_as'].get('same_as', 0):,} planted candidates")
    lines.append(
        f"total: {t.get('nodes', 0):,} nodes, {t.get('edges', 0):,} links, "
        f"{t.get('texts', 0):,} texts, {t.get('events', 0):,} events, "
        f"{t['bytes'] / 1e9:,.2f} GB"
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.generate_client_size", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--graph-scale", type=float, default=None)
    parser.add_argument("--seed", type=int, default=plan.DEFAULT_SEED)
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = parser.parse_args(argv)
    if args.scale <= 0 or (args.graph_scale is not None and args.graph_scale <= 0):
        parser.error("the scales must be above 0")
    if args.graph_scale is None:
        args.graph_scale = args.scale
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    out = args.out.resolve()
    if inside_repository(out):
        print(
            f"--out {out} is inside the git working tree; these files are never committed. "
            "Choose a folder outside it.",
            file=sys.stderr,
        )
        return 2
    if (out / "manifest.json").exists():
        print(
            f"{out} already holds a generated set (manifest.json); choose an empty folder.",
            file=sys.stderr,
        )
        return 2
    result = generate(
        out, seed=args.seed, scale=args.scale, graph_scale=args.graph_scale, jobs=args.jobs
    )
    print(summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
