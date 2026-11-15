"""v0.6.0 stage 3 preparation: the product's release, run short of everything that leaves the machine.

The workflow that releases is the product's, `OspreyFlow_Core/.github/workflows/release.yml` (published to the
product repository by `publish_user_repo_update.sh`), not the development repository's root
`.github/workflows/release.yml`, which `tools/release_local.py` mirrors (another image list, another registry).
This reads the product workflow's own image matrix and trivy settings, so it cannot drift from them, and runs:

1. the notes: `scripts.changelog_check --tag <tag>`;
2. each image built as the workflow's scan build is (`docker buildx build --pull --platform linux/amd64 --load`),
   with the day's upgrade stamp (`harness.upgrade_stamp`), then scanned with the workflow's trivy flags;
3. the lock: `harness.release_lock`, which must refuse naming exactly our owned images (never pushed, so not
   pinnable) and pin every third-party one;
4. the install page built and packed; the chart packaged at the tag's version.

It never pushes, signs, logs in or publishes: what the workflow would do there is printed as `[would] …`.

    PYTHONPATH=.:packages .venv/bin/python ../OspreyFlow_Build/process/lanes/platform-b/v060/release_dry_run.py \\
        --tag v0.6.0 --out <folder> [--plan]            (from OspreyFlow_Core; --plan prints and runs nothing)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
WORKFLOW = CORE / ".github" / "workflows" / "release.yml"
REGISTRY = "ghcr.io/aykr"  # the product repository's owner, lower case, as the workflow names it

Run = Callable[[Sequence[str]], None]


def workflow(path: Path = WORKFLOW) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def matrix(flow: dict[str, Any]) -> list[dict[str, str]]:
    """The images job's matrix entries: service, dockerfile and (when not the root) context."""
    return list(flow["jobs"]["images"]["strategy"]["matrix"]["include"])


def trivy_settings(flow: dict[str, Any]) -> dict[str, Any]:
    step = next(s for s in flow["jobs"]["images"]["steps"] if str(s.get("uses", "")).startswith("aquasecurity/trivy-action"))
    return dict(step["with"])


def trivy_command(settings: dict[str, Any], image: str) -> list[str]:
    cmd = ["trivy", "image", "--scanners", str(settings["scanners"]), "--severity", str(settings["severity"])]
    if str(settings.get("ignore-unfixed")).lower() == "true":
        cmd.append("--ignore-unfixed")
    return [*cmd, "--exit-code", str(settings["exit-code"]), image]


def plan(tag: str, sha: str, out: Path, stamp_args: list[str], flow: dict[str, Any]) -> list[list[str]]:
    """Every command, in order. A line starting `[would]` is printed, never run."""
    steps: list[list[str]] = [["python3", "-m", "scripts.changelog_check", "--tag", tag, "--notes-out", str(out / "notes.md")]]
    settings = trivy_settings(flow)
    for entry in matrix(flow):
        image = f"{REGISTRY}/{entry['service']}"
        scan = f"{image}:scan"
        steps.append(["docker", "buildx", "build", "--pull", "--platform", "linux/amd64", "--load", *stamp_args,
                      "-f", entry["dockerfile"], "-t", scan, entry.get("context", ".")])  # fmt: skip
        steps.append(trivy_command(settings, scan))
        steps.append(["[would]", "docker", "buildx", "build", "--platform", "linux/amd64,linux/arm64", "--push",
                      "-f", entry["dockerfile"], "-t", f"{image}:{sha}", entry.get("context", ".")])  # fmt: skip
        steps.append(["[would]", "cosign", "sign", "--yes", f"{image}@<the pushed index's digest>"])
    steps.append(["env", f"OSPREY_IMAGE_REGISTRY={REGISTRY}", "PYTHONPATH=.:packages", sys.executable, "-m",
                  "harness.release_lock", "--config", "osprey.yaml", "--out", str(out / "versions.lock")])  # fmt: skip
    steps.append(["npm", "run", "build", "-w", "apps/harness"])
    steps.append(["tar", "-C", "apps/harness/dist", "-czf", str(out / "install-page.tar.gz"), "."])
    version = tag.removeprefix("v")
    steps.append(["helm", "package", "deploy/helm/ospreyflow", "--version", version, "--app-version", tag,
                  "--destination", str(out)])  # fmt: skip
    steps.append(["[would]", "cosign", "sign-blob", "versions.lock, install-page.tar.gz and the chart; helm push; "
                  "harness.signatures verifies; gh release create"])  # fmt: skip
    return steps


def owned_images(flow: dict[str, Any]) -> set[str]:
    return {entry["service"] for entry in matrix(flow)}


def lock_refusal_names(text: str) -> set[str]:
    """The services a refused lock names (`ghcr.io/aykr/<service>:<sha>` in its words)."""
    return {part.split("/")[-1].split(":")[0] for part in text.replace(",", " ").split() if part.startswith(REGISTRY + "/")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release_dry_run")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plan", action="store_true", help="print the commands and run nothing")
    args = parser.parse_args(argv)
    sys.path[:0] = [str(CORE), str(CORE / "packages")]
    from harness import upgrade_stamp

    sha = subprocess.run(["git", "-C", str(CORE), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    args.out.mkdir(parents=True, exist_ok=True)
    flow = workflow()
    for step in plan(args.tag, sha, args.out, upgrade_stamp.build_args(), flow):
        line = " ".join(step)
        if step[0] == "[would]" or args.plan:
            print(line if step[0] == "[would]" else f"[plan] {line}", flush=True)
            continue
        print(f"+ {line}", flush=True)
        if "harness.release_lock" in step:
            done = subprocess.run(step, cwd=CORE, capture_output=True, text=True)
            named = lock_refusal_names(done.stdout + done.stderr)
            expected = owned_images(flow) & {"workspace", "api", "ingest", "ner", "superset"}
            if done.returncode == 0 or named != expected:
                print(done.stdout + done.stderr, file=sys.stderr)
                raise SystemExit(f"FAIL the lock: expected a refusal naming exactly {sorted(expected)}, got "
                                 f"{sorted(named) if done.returncode else 'a written lock'}")  # fmt: skip
            print(f"PASS the lock refuses only our unpushed images {sorted(named)}; every third-party image pinned")
            continue
        subprocess.run(step, cwd=CORE, check=True)
    print("release_dry_run: done; nothing pushed, signed or published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
