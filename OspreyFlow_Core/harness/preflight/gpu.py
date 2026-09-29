"""GPU presence and driver version — `05_DEPLOYMENT.md` §2.1's third check.

**Skip, not pass, in two distinct cases, and the difference matters.** A profile that declares no
GPU component has nothing to check, and a platform where the driver version cannot be read has
something to check and no way to read it. Both return `skip`; each says which it is. Reporting
either as `pass` would tell an operator their GPU driver is fine when in the first case there is no
GPU in play and in the second nobody looked — the exact failure `06_DECISIONS.md` ADR-035 §C7 calls
"a gate verifying less than its name implies".

**On macOS specifically, this is a skip and will stay one.** `nvidia-smi` does not exist there and
Metal exposes no equivalent driver-version query that means the same thing; the honest answer is
that this check does not run on this platform, recorded in the result rather than in a comment.
"""

from __future__ import annotations

import platform
import shutil
import subprocess

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped

NAME = "gpu"


def _declares_gpu_components(context: PreflightContext) -> bool:
    """Ollama and vLLM are the GPU-capable components. `local-lite` runs Ollama on "CPU or one
    consumer GPU" (§1), so a GPU is optional there — which is why its absence is not a failure."""
    return not context.config.models.local_only or context.config.profile.value != "local-lite"


def check(context: PreflightContext) -> CheckResult:
    if platform.system() == "Darwin":
        return skipped(
            NAME,
            reason=(
                "GPU driver version cannot be read headlessly on macOS — nvidia-smi does not "
                "exist and Metal exposes no equivalent. This check did not run; it is not a "
                "statement that the GPU or its driver is correct."
            ),
            detail=(f"platform: {platform.system()} {platform.release()}",),
        )

    smi = shutil.which("nvidia-smi")
    if smi is None:
        if context.config.profile.value == "local-lite":
            return skipped(
                NAME,
                reason=(
                    "no nvidia-smi on PATH and the local-lite profile runs models on CPU or one "
                    "consumer GPU (05_DEPLOYMENT.md §1), so a GPU is optional here. Not checked."
                ),
            )
        return failed(
            NAME,
            what_is_wrong=(
                f"no nvidia-smi on PATH, and the {context.config.profile.value} profile expects "
                "GPU-backed model serving."
            ),
            what_to_do=(
                "Install the NVIDIA driver and container toolkit on this host, or change the "
                "models section of osprey.yaml so this deployment does not expect a GPU."
            ),
        )

    result = subprocess.run(
        [smi, "--query-gpu=driver_version,name", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return failed(
            NAME,
            what_is_wrong=(
                f"nvidia-smi is installed but returned {result.returncode}: "
                f"{result.stderr.strip() or 'no error output'}"
            ),
            what_to_do=(
                "The driver is usually loaded but mismatched with the installed userspace "
                "library. Reinstall the driver package, or reboot if it was updated in place."
            ),
        )
    return passed(NAME, detail=tuple(line.strip() for line in result.stdout.splitlines() if line))
