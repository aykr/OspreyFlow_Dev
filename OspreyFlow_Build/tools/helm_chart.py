"""The chart templated by Helm's own pinned image, so nothing needs Helm on the host: the one runner
`make cp-policy-check` (`tools/cp_policy_check.py`) and the chart's tests (`tests/harness/
test_helm_chart.py`) share. Needs Docker. (The Makefile's `chart-check` names the same image.)"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

BUILD = Path(__file__).resolve().parents[1]
CHART = BUILD.parent / "OspreyFlow_Core" / "deploy" / "helm" / "ospreyflow"
HELM = "alpine/helm:3.16.3"


class HelmFailed(RuntimeError):
    """`helm template` refused the values; the message is Helm's own."""


def template_text(values: str | None, namespace: str) -> str:
    """Helm's own output for `values` (None: the chart's defaults alone) into `namespace`."""
    command = ["docker", "run", "--rm", "-i", "-v", f"{CHART}:/chart:ro", HELM, "template",
               "ospreyflow", "/chart", "--namespace", namespace]  # fmt: skip
    if values is not None:
        command += ["-f", "-"]
    done = subprocess.run(
        command, input=values, capture_output=True, text=True, timeout=300, check=False
    )
    if done.returncode != 0:
        raise HelmFailed(f"helm template failed: {done.stderr or done.stdout}")
    return done.stdout


def template(values: str | None, namespace: str) -> list[dict[str, Any]]:
    """`template_text`, each manifest parsed."""
    return [doc for doc in yaml.safe_load_all(template_text(values, namespace)) if doc]
