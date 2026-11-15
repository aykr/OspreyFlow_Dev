"""v0.6.0 #11, the package test: each container's working set over the whole run on R1's kind cluster.

The owner's ruling (15 November 2026): item 23 (sizes from measured use) is out of v0.6.0, but the package test
records each container's working set over its run, with its peak, its steady state, its OOMKills and its restarts.
Those figures are the owner's to read; nothing here changes a size.

R1's own `py memory` (`process/lanes/platform/gates/r1_kind.py`) reads the kubelet's stats summary once: one
moment, never a peak. This samples the same summary every `--every` seconds from `start` to `stop`, with the
pods' restart counts and last terminations beside it, into R1's state folder, and `report` writes the table.

    bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh memory start [--every 15]
    bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh memory mark "<label>"
    bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh memory stop
    bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh memory report [--steady-from <label>]

A sample the cluster cannot answer (kubectl failing, the API restarting) is recorded as a gap, counted in the
report, and never stops the run. A container the summary has not measured yet (just started) is left out of that
sample, not counted as zero.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NODE = "osprey-r1-control-plane"
STATE = Path(os.environ.get("OSPREY_R1_STATE", str(Path.home() / "osprey-runs" / "platform.r1")))
MIB = 2**20

#: A Deployment's pod is `<name>-<template hash>-<5 characters>`, a Job's or a CronJob's `<name>-<5 characters>`
#: (a CronJob's job also `-<schedule number>`); a StatefulSet's `<name>-<ordinal>` keeps its ordinal.
_DEPLOYMENT = re.compile(r"^(?P<w>.+)-[0-9a-f]{6,10}-[0-9a-z]{5}$")
_JOB = re.compile(r"^(?P<w>.+?)(?:-\d{8,})?-[0-9a-z]{5}$")

Kubectl = Callable[..., str]


def workload(pod: str) -> str:
    """The workload a pod belongs to, so a container restarted into a new pod is one row, not two."""
    for pattern in (_DEPLOYMENT, _JOB):
        match = pattern.match(pod)
        if match and not pod.rsplit("-", 1)[-1].isdigit():
            return match.group("w")
    return pod


def from_summary(summary: dict[str, Any]) -> tuple[int | None, dict[str, int]]:
    """The node's working set and each measured container's, keyed `namespace/workload/container`."""
    node = (summary.get("node") or {}).get("memory", {}).get("workingSetBytes")
    out: dict[str, int] = {}
    for pod in summary.get("pods") or []:
        ref = pod.get("podRef") or {}
        for container in pod.get("containers") or []:
            got = (container.get("memory") or {}).get("workingSetBytes")
            if got is None:  # not measured yet: left out, never a zero
                continue
            key = f"{ref.get('namespace')}/{workload(str(ref.get('name')))}/{container.get('name')}"
            out[key] = max(out.get(key, 0), int(got))  # two replicas of one workload: the larger
    return node, out


def from_pods(pods: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each container's restarts and whether its last termination was an OOMKill, by pod (a restart counter
    belongs to one pod: a replaced pod starts again at zero)."""
    out: dict[str, dict[str, Any]] = {}
    for item in pods.get("items") or []:
        meta = item.get("metadata") or {}
        for status in (item.get("status") or {}).get("containerStatuses") or []:
            last = ((status.get("lastState") or {}).get("terminated") or {}).get("reason")
            key = f"{meta.get('namespace')}/{meta.get('name')}/{status.get('name')}"
            out[key] = {"restarts": int(status.get("restartCount") or 0), "last": last}
    return out


def sample(kubectl: Kubectl, now: Callable[[], str]) -> dict[str, Any]:
    """One line of the record: the summary and the pods, or a gap saying why."""
    at = now()
    try:
        summary = json.loads(kubectl("get", "--raw", f"/api/v1/nodes/{NODE}/proxy/stats/summary"))
        pods = json.loads(kubectl("get", "pods", "-A", "-o", "json"))
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        return {"at": at, "gap": str(e).strip()[:300]}
    node, containers = from_summary(summary)
    return {"at": at, "node": node, "containers": containers, "pods": from_pods(pods)}


@dataclass
class Row:
    samples: list[int] = field(default_factory=list)
    steady: list[int] = field(default_factory=list)


def report(lines: Iterable[dict[str, Any]], steady_from: str | None = None) -> str:
    """The table: per container, its peak, p95, median over the run, steady state (the median from the mark
    `steady_from`, else the last fifth of the samples), and the run's restarts and OOMKills."""
    rows: dict[str, Row] = {}
    node_peak = 0
    gaps = taken = 0
    restarts: dict[str, int] = {}
    ooms: dict[str, set[int]] = {}
    in_steady = False
    seen: list[dict[str, Any]] = []
    for line in lines:
        if "mark" in line:
            if steady_from is not None and line["mark"] == steady_from:
                in_steady = True
            continue
        if "gap" in line:
            gaps += 1
            continue
        taken += 1
        seen.append(line)
        node_peak = max(node_peak, int(line.get("node") or 0))
        for key, value in line["containers"].items():
            row = rows.setdefault(key, Row())
            row.samples.append(value)
            if in_steady:
                row.steady.append(value)
        for pod_key, status in line.get("pods", {}).items():
            ns, pod, container = pod_key.split("/", 2)
            key = f"{ns}/{workload(pod)}/{container}"
            restarts[pod_key] = max(restarts.get(pod_key, 0), status["restarts"])
            if status["last"] == "OOMKilled":
                ooms.setdefault(key, set()).add(hash((pod, status["restarts"])))
    if steady_from is not None and not in_steady:
        raise SystemExit(f"report: no mark {steady_from!r} in the record")
    if steady_from is None and seen:  # the last fifth of the samples
        tail = seen[-max(1, len(seen) // 5):]
        for key, row in rows.items():
            row.steady = [line["containers"][key] for line in tail if key in line["containers"]]
    by_workload: dict[str, int] = {}
    for pod_key, count in restarts.items():
        ns, pod, container = pod_key.split("/", 2)
        key = f"{ns}/{workload(pod)}/{container}"
        by_workload[key] = by_workload.get(key, 0) + count

    def mib(value: float) -> str:
        return f"{value / MIB:.0f}"

    out = [f"samples {taken}, gaps {gaps}; node working set peak {node_peak / 2**30:.2f} GiB",
           "", "container (namespace/workload/container)  peak_MiB  p95_MiB  median_MiB  steady_MiB  restarts  oomkills"]
    for key in sorted(rows, key=lambda k: -max(rows[k].samples)):
        row = rows[key]
        ordered = sorted(row.samples)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1) + 0.5))]
        steady = mib(statistics.median(row.steady)) if row.steady else "-"
        out.append(f"{key}  {mib(ordered[-1])}  {mib(p95)}  {mib(statistics.median(ordered))}  {steady}  "
                   f"{by_workload.get(key, 0)}  {len(ooms.get(key, set()))}")
    return "\n".join(out) + "\n"


def _kubectl(*args: str) -> str:
    return subprocess.run(["kubectl", *args], capture_output=True, text=True, check=True, timeout=30).stdout


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _paths() -> tuple[Path, Path]:
    return STATE / "memory-samples.jsonl", STATE / "memory-sampler.pid"


def loop(every: float, kubectl: Kubectl = _kubectl, now: Callable[[], str] = _now,
         sleep: Callable[[float], None] = time.sleep, rounds: int | None = None) -> None:  # fmt: skip
    record, _ = _paths()
    done = 0
    while rounds is None or done < rounds:
        with record.open("a", encoding="utf-8") as out:
            out.write(json.dumps(sample(kubectl, now), sort_keys=True) + "\n")
        done += 1
        sleep(every)


def _running(pid_file: Path) -> int | None:
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memory_sampler")
    sub = parser.add_subparsers(dest="verb", required=True)
    start = sub.add_parser("start")
    start.add_argument("--every", type=float, default=15.0)
    sub.add_parser("stop")
    mark = sub.add_parser("mark")
    mark.add_argument("label")
    rep = sub.add_parser("report")
    rep.add_argument("--steady-from")
    run = sub.add_parser("loop")
    run.add_argument("--every", type=float, default=15.0)
    args = parser.parse_args(argv)
    record, pid_file = _paths()
    STATE.mkdir(parents=True, exist_ok=True)
    if args.verb == "start":
        if (pid := _running(pid_file)) is not None:
            raise SystemExit(f"memory sampler already running (pid {pid}): stop it first")
        record.write_text("")  # one record per run
        log = (STATE / "memory-sampler.log").open("a")
        child = subprocess.Popen([sys.executable, __file__, "loop", "--every", str(args.every)],
                                 stdout=log, stderr=log, start_new_session=True)  # fmt: skip
        pid_file.write_text(f"{child.pid}\n")
        print(f"memory sampler started (pid {child.pid}), every {args.every:g} s, into {record}")
    elif args.verb == "loop":
        loop(args.every)
    elif args.verb == "mark":
        with record.open("a", encoding="utf-8") as out:
            out.write(json.dumps({"at": _now(), "mark": args.label}) + "\n")
        print(f"memory sampler: marked {args.label!r}")
    elif args.verb == "stop":
        pid = _running(pid_file)
        if pid is None:
            raise SystemExit("memory sampler: none running")
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink()
        print(f"memory sampler stopped (pid {pid})")
    else:
        lines = [json.loads(x) for x in record.read_text(encoding="utf-8").splitlines() if x.strip()]
        text = report(lines, args.steady_from)
        out_file = STATE / "records" / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-memory-sampled.txt"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(text, encoding="utf-8")
        print(text, end="")
        print(f"(written to {out_file})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
