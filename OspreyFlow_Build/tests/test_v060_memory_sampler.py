"""v0.6.0 #11's memory sampler (`process/lanes/platform-b/v060/memory_sampler.py`): each container's working set
over the package test's run, with peaks, steady state, restarts and OOMKills, the figures the owner reads.

The inputs are shaped as the kubelet's stats summary and `kubectl get pods -o json` give them, including what
they really give that a happy-path fixture would not: a container the summary has not measured yet (no
`workingSetBytes`), a pod replaced by a new one (its restart counter starting again at zero), an OOMKill shown
only as the last termination's reason, and the API refusing a request (kubectl exiting 1)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parents[1] / "process" / "lanes" / "platform-b" / "v060" / "memory_sampler.py"
spec = importlib.util.spec_from_file_location("memory_sampler", HERE)
assert spec and spec.loader
ms = importlib.util.module_from_spec(spec)
sys.modules["memory_sampler"] = ms  # a dataclass reads its module from here
spec.loader.exec_module(ms)

MIB = 2**20


def _summary(pods: dict[str, dict[str, int | None]], node: int = 8 * 2**30) -> dict[str, Any]:
    """A kubelet stats summary: {pod name: {container: working set or None (not measured yet)}}."""
    return {
        "node": {"nodeName": ms.NODE, "memory": {"workingSetBytes": node}},
        "pods": [
            {"podRef": {"name": name, "namespace": "ospreyflow-poc", "uid": name},
             "containers": [{"name": c, "memory": ({} if v is None else {"workingSetBytes": v})}
                            for c, v in containers.items()]}
            for name, containers in pods.items()
        ],
    }  # fmt: skip


def _pods(statuses: dict[str, dict[str, tuple[int, str | None]]]) -> dict[str, Any]:
    """`kubectl get pods -A -o json`: {pod: {container: (restartCount, last termination reason)}}."""
    return {"items": [
        {"metadata": {"name": pod, "namespace": "ospreyflow-poc"},
         "status": {"containerStatuses": [
             {"name": c, "restartCount": n,
              "lastState": ({"terminated": {"reason": why, "exitCode": 137}} if why else {})}
             for c, (n, why) in containers.items()]}}
        for pod, containers in statuses.items()
    ]}  # fmt: skip


@pytest.mark.parametrize(("pod", "expected"), [
    ("conduit-866798dd8-qwdfc", "conduit"),            # a Deployment's pod
    ("arcadedb-0", "arcadedb-0"),                      # a StatefulSet's keeps its ordinal
    ("search-rebuild-r1-x7k2p", "search-rebuild-r1"),  # a Job's
    ("search-drift-29386020-b4m9q", "search-drift"),   # a CronJob's job
])  # fmt: skip
def test_a_pod_is_named_by_its_workload(pod: str, expected: str) -> None:
    assert ms.workload(pod) == expected


def test_a_container_not_measured_yet_is_left_out_not_counted_as_zero() -> None:
    node, got = ms.from_summary(_summary({"conduit-866798dd8-qwdfc": {"api": 300 * MIB, "sidecar": None}}))
    assert got == {"ospreyflow-poc/conduit/api": 300 * MIB}
    assert node == 8 * 2**30


def test_a_refused_request_is_a_gap_and_the_run_goes_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """kubectl exits 1 while the API restarts: that sample is a gap, the loop takes the next one."""
    monkeypatch.setattr(ms, "STATE", tmp_path)
    answers = iter([
        subprocess.CalledProcessError(1, ["kubectl"], stderr="The connection to the server was refused"),
        json.dumps(_summary({"conduit-866798dd8-qwdfc": {"api": 300 * MIB}})),
        json.dumps(_pods({"conduit-866798dd8-qwdfc": {"api": (0, None)}})),
    ])  # fmt: skip

    def kubectl(*args: str) -> str:
        got = next(answers)
        if isinstance(got, Exception):
            raise got
        return got

    ms.loop(15, kubectl=kubectl, now=lambda: "2026-11-15T12:00:00Z", sleep=lambda _: None, rounds=2)
    lines = [json.loads(x) for x in (tmp_path / "memory-samples.jsonl").read_text().splitlines()]
    assert "gap" in lines[0] and "containers" in lines[1]
    assert "samples 1, gaps 1" in ms.report(lines)


def _run() -> list[dict[str, Any]]:
    """Ten samples of one workload: rising to a peak of 900 MiB, then an OOMKill, the pod replaced, a steady
    200 MiB idle tail after the mark."""
    lines: list[dict[str, Any]] = []
    first, second = "conduit-866798dd8-aaaaa", "conduit-866798dd8-bbbbb"
    for i, mib in enumerate([100, 300, 600, 900]):
        lines.append({"at": f"t{i}", "node": (6 + i) * 2**30,
                      "containers": {"ospreyflow-poc/conduit/api": mib * MIB},
                      "pods": ms.from_pods(_pods({first: {"api": (0, None)}}))})  # fmt: skip
    lines.append({"at": "t4", "node": 9 * 2**30, "containers": {"ospreyflow-poc/conduit/api": 50 * MIB},
                  "pods": ms.from_pods(_pods({first: {"api": (1, "OOMKilled")}}))})  # fmt: skip
    lines.append({"at": "t5", "mark": "soak"})
    for i in range(5):
        lines.append({"at": f"t{6 + i}", "node": 7 * 2**30,
                      "containers": {"ospreyflow-poc/conduit/api": 200 * MIB},
                      "pods": ms.from_pods(_pods({second: {"api": (0, None)}}))})  # fmt: skip
    return lines


def _row(text: str, key: str) -> list[str]:
    return next(line for line in text.splitlines() if line.startswith(key + " ")).split()


def test_the_report_gives_peak_steady_restarts_and_oomkills() -> None:
    row = _row(ms.report(_run(), steady_from="soak"), "ospreyflow-poc/conduit/api")
    _, peak, p95, median, steady, restarts, ooms = row
    assert (peak, steady, restarts, ooms) == ("900", "200", "1", "1")
    assert int(p95) <= 900 and int(median) == 200


def test_the_peak_is_the_largest_sample_not_the_last() -> None:
    """A snapshot at the end (R1's `py memory`) would say 200: the run's peak is 900."""
    assert _row(ms.report(_run(), steady_from="soak"), "ospreyflow-poc/conduit/api")[1] == "900"


def test_the_node_peak_is_reported() -> None:
    assert "node working set peak 9.00 GiB" in ms.report(_run())


def test_a_restart_on_a_replaced_pod_is_not_lost() -> None:
    """The replacement pod's counter starts at zero: the first pod's restart still counts."""
    assert _row(ms.report(_run()), "ospreyflow-poc/conduit/api")[5] == "1"


def test_a_steady_mark_that_was_never_made_is_refused() -> None:
    with pytest.raises(SystemExit, match="no mark 'idle'"):
        ms.report(_run(), steady_from="idle")


def test_without_a_mark_steady_is_the_last_fifth() -> None:
    assert _row(ms.report(_run()), "ospreyflow-poc/conduit/api")[4] == "200"
