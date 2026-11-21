"""`python -m tools.release_local --dry-run --tag vX.Y.Z` — the product's release, run here short of everything
that leaves the machine.

**The release is the product repository's workflow**, `OspreyFlow_Core/.github/workflows/release.yml`, published
to the product repository by `publish_user_repo_update.sh` (the owner's ruling, 15 November 2026: this follows it;
until then this mirrored the development repository's root workflow, another image list for another registry,
which stopped at its first job on every tag and is retired). This reads the product workflow's own image matrix
and trivy settings, so it cannot drift from them, and runs, in the workflow's order:

1. the notes: `scripts.changelog_check --tag <tag>`;
2. each image as the workflow's scan build makes it (`docker buildx build --pull --platform linux/amd64 --load`),
   with the day's upgrade stamp (`harness.upgrade_stamp`: a local builder holds a cache, GitHub's runners do not),
   then trivy with the workflow's flags;
3. the lock (`harness.release_lock`), which must refuse naming exactly our locked images (never pushed here, so
   not pinnable) and pin every third-party one;
4. the install page built and packed; the chart packaged at the tag's version.

**It never pushes, signs, logs in or publishes**: the two-platform push, cosign's keyless signatures (the
workflow's own GitHub identity), `harness.signatures`' verify and `gh release create` are printed as
`[would] …`. A real push from here would publish unsigned single-platform images under the release's names, so it
is refused: `--dry-run` is required.

**No release while a live test is owed.** A slice the v0.6.2 slice line merged with its live step off leaves the live
test files its change reaches owed until a live run has run them green
(`OspreyFlow_Build/scripts/slice_line/owed.py`); this refuses before anything is built while any is owed, as
`OspreyFlow_Build/scripts/publish_user_repo_update.sh` does before the product is published.

**No release unless GitHub is green on the commit released** (the owner, 20 November 2026): the latest completed run
of `ci` on exactly that commit concluded success, a rerun that passed included
(`OspreyFlow_Build/scripts/slice_line/release_green.py`); refused before anything is built otherwise, as the publish
script does.

**No release while the licence register is unsettled** (the owner, 21 November 2026): any row of
`spec/LICENCE_REGISTER.yaml` that is `unconfirmed`, and any name in `HELD_FOR_OWNER`
(`tools/licence_register.py`), refuses the release before anything is built, in words that name each. The gate in
`make ci` allows both, so the build stays green while the owner decides. Checked after the two above, which the
existing cases in `tests/test_release_owed.py` assert and which are unchanged.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from harness import upgrade_stamp
from harness.render import REPO_ROOT, git_sha
from tools import licence_register

#: The slice line's owed live tests (owed.py check: exit 1 while any is owed or its records cannot be read).
OWED = REPO_ROOT.parent / "OspreyFlow_Build" / "scripts" / "slice_line" / "owed.py"


#: GitHub green on the commit released (release_green.py check: exit 1 unless the latest completed ci run on exactly
#: that commit concluded success; the owner, 20 November 2026).
GREEN = REPO_ROOT.parent / "OspreyFlow_Build" / "scripts" / "slice_line" / "release_green.py"


def green_refusal(sha: str) -> str | None:
    """Why a release of `sha` must wait for GitHub green on it, in release_green.py's words, or None when it is."""
    p = subprocess.run([sys.executable, str(GREEN), "check", sha], capture_output=True, text=True, check=False)
    return None if p.returncode == 0 else (p.stdout + p.stderr).strip()


def owed_refusal() -> str | None:
    """Why a release must wait for the live tests owed, in owed.py's words, or None when none is owed."""
    p = subprocess.run([sys.executable, str(OWED), "check"], capture_output=True, text=True, check=False)
    return None if p.returncode == 0 else (p.stdout + p.stderr).strip()


def register_refusal(
    rows: list[dict[str, Any]] | None = None, held: frozenset[str] | None = None
) -> str | None:
    """Why a release must wait for the licence register, in words that name each unconfirmed row and each
    name held for the owner, or None when none is left (`tools/licence_register.py`; the owner, 21 November
    2026). The gate in `make ci` allows both so the build stays green; a release does not."""
    return licence_register.release_refusal(
        rows=rows, held=licence_register.HELD_FOR_OWNER if held is None else held
    )


#: The product workflow (REPO_ROOT is the Core checkout, the product repository's root).
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
#: The product repository's owner, lower case, as the workflow names its images.
REGISTRY = os.environ.get("OSPREY_IMAGE_REGISTRY", "ghcr.io/aykr")
#: Our images the lock names (`harness.release_lock`: every image any option renders). The release builds two
#: more (worker, report-sync) for the Enterprise chart, which the lock does not name.
LOCKED_OURS = frozenset({"workspace", "api", "ingest", "ner", "superset"})


def workflow(path: Path = WORKFLOW) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def matrix(flow: dict[str, Any]) -> list[dict[str, str]]:
    """The images job's matrix entries: service, dockerfile and (when not the root) context."""
    return list(flow["jobs"]["images"]["strategy"]["matrix"]["include"])


def trivy_settings(flow: dict[str, Any]) -> dict[str, Any]:
    steps = flow["jobs"]["images"]["steps"]
    step = next(s for s in steps if str(s.get("uses", "")).startswith("aquasecurity/trivy-action"))
    return dict(step["with"])


def trivy_command(settings: dict[str, Any], image: str) -> list[str]:
    cmd = ["trivy", "image", "--scanners", str(settings["scanners"]),
           "--severity", str(settings["severity"])]  # fmt: skip
    if str(settings.get("ignore-unfixed")).lower() == "true":
        cmd.append("--ignore-unfixed")
    return [*cmd, "--exit-code", str(settings["exit-code"]), image]


#: Kept for the callers and tests that read the image list as tuples: (service, Dockerfile, context).
SERVICES: tuple[tuple[str, str, str], ...] = tuple(
    (e["service"], e["dockerfile"], e.get("context", ".")) for e in matrix(workflow())
)


def _run(cmd: list[str], **kwargs: object) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)  # type: ignore[call-overload]


def build_and_scan(sha: str, flow: dict[str, Any] | None = None) -> list[str]:
    """Builds and scans every image of the product matrix as the workflow's scan build does, and returns the
    references the workflow would push (`<image>:<sha>`), which this module only prints."""
    flow = flow if flow is not None else workflow()
    settings = trivy_settings(flow)
    refs: list[str] = []
    for entry in matrix(flow):
        image = f"{REGISTRY}/{entry['service']}"
        scan = f"{image}:scan"
        _run(["docker", "buildx", "build", "--pull", "--platform", "linux/amd64", "--load",
              *upgrade_stamp.build_args(), "-f", entry["dockerfile"], "-t", scan,
              str(REPO_ROOT / entry.get("context", "."))])  # fmt: skip
        _run(trivy_command(settings, scan))
        refs.append(f"{image}:{sha}")
    return refs


def lock_refusal_names(text: str) -> set[str]:
    """The services a refused lock names (`<registry>/<service>:<sha>` in its words)."""
    return {
        part.split("/")[-1].split(":")[0]
        for part in text.replace(",", " ").split()
        if part.startswith(REGISTRY + "/")
    }


def lock(out: Path) -> None:
    """The release's lock, which here must refuse naming exactly our locked images: never pushed, so not
    pinnable, while every third-party image pins from its registry."""
    cmd = [sys.executable, "-m", "harness.release_lock", "--config", "osprey.yaml",
           "--out", str(out / "versions.lock")]  # fmt: skip
    print("+ " + " ".join(cmd), flush=True)
    done = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True,
                          env={**os.environ, "OSPREY_IMAGE_REGISTRY": REGISTRY})  # fmt: skip
    named = lock_refusal_names(done.stdout + done.stderr)
    if done.returncode == 0 or named != set(LOCKED_OURS):
        print(done.stdout + done.stderr, file=sys.stderr)
        got = sorted(named) if done.returncode else "a lock written"
        raise SystemExit(f"FAIL the lock: expected a refusal naming exactly {sorted(LOCKED_OURS)}, got {got}")
    print(f"PASS the lock refuses only our unpushed images {sorted(named)}; every third-party image pinned")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.release_local", description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="required: nothing is pushed, signed or published")
    parser.add_argument("--tag", required=True, help="the release's tag, vX.Y.Z (its CHANGELOG section and chart)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT.parent / "OspreyFlow_Build" / "dist" / "release-dry-run")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if not args.dry_run:
        print("release_local: refusing — the release is the product workflow's, signed with its own GitHub identity; "
              "a push from here would publish unsigned images under its names. Run with --dry-run.", file=sys.stderr)
        return 1
    refusal = owed_refusal()
    if refusal:
        print(f"release_local: refusing — live tests are owed:\n{refusal}", file=sys.stderr)
        return 1
    sha = git_sha()
    if sha == "unknown":
        print("release_local: refusing — this checkout has no resolvable git sha", file=sys.stderr)
        return 1
    refusal = green_refusal(sha)
    if refusal:
        print(f"release_local: refusing — GitHub is not green on the commit released ({sha}):\n{refusal}",
              file=sys.stderr)
        return 1
    refusal = register_refusal()
    if refusal:
        print(f"release_local: refusing — {refusal}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"release_local: the product's release of {args.tag}, from commit {sha}, short of the push")
    _run([sys.executable, "-m", "scripts.changelog_check", "--tag", args.tag,
          "--notes-out", str(args.out / "notes.md")], cwd=str(REPO_ROOT))  # fmt: skip
    for ref in build_and_scan(sha):
        print(f"[would] push {ref} for linux/amd64 and linux/arm64, then cosign sign it by digest")
    lock(args.out)
    _run(["npm", "run", "build", "-w", "apps/harness"], cwd=str(REPO_ROOT))
    _run(["tar", "-C", "apps/harness/dist", "-czf", str(args.out / "install-page.tar.gz"), "."], cwd=str(REPO_ROOT))
    _run(["helm", "package", "deploy/helm/ospreyflow", "--version", args.tag.removeprefix("v"),
          "--app-version", args.tag, "--destination", str(args.out)], cwd=str(REPO_ROOT))  # fmt: skip
    print("[would] cosign sign-blob the lock, the install page and the chart; helm push the chart and sign it; "
          "harness.signatures verify all of it; gh release create")
    print("release_local: done — dry-run, nothing was pushed, signed or published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
