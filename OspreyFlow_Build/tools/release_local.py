"""`python -m tools.release_local` — every step `.github/workflows/release.yml` runs, except
the push, executable directly against this checkout.

**Why this exists, round 11.** The release workflow cannot be run end to end from this sandbox —
it needs a real tag push and `packages: write` credentials for `ghcr.io/ospreyflow` this sandbox
does not have. `actionlint` (`06_DECISIONS.md` ADR-049 Stage 2 §5b/§7's own brief, item 2) checks
the YAML is well-formed; it says nothing about whether the *commands* it runs actually work. This
script runs the same four builds, the same trivy gate (same flags, same severity, same
`--ignore-unfixed`), the same `--build-arg OSPREY_BUILT_FROM_SHA` for the harness image, and the
same `make bundle` — against this repository's own real Dockerfiles, real trivy binary, real
`make bundle` command — with `--dry-run` standing in for the four `docker push` calls, printing
the exact references it would have pushed instead of reaching the registry. **The only step this
script cannot exercise is the push itself** — said here, not left implicit.

**Round 13cg: nor does it run `ci-status-gate`**, the job that now runs before `build-scan-push`
and refuses the release unless `ci.yml` reported green for the commit being tagged
(`tools/ci_status_check.py`). That check is about GitHub's own recorded state for a commit, not
about whether this checkout's build commands work — the two questions this script answers — so
mirroring it here would need the same GitHub API call this script otherwise has no reason to make.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from harness.render import REPO_ROOT, git_sha

REGISTRY = "ghcr.io/ospreyflow"

#: (service, Dockerfile, build-arg name to bake the release sha under, or None). Mirrors
#: `.github/workflows/release.yml`'s own matrix exactly — a fifth entry there needs a fifth one
#: here, not a second copy of the list to drift from it.
SERVICES: tuple[tuple[str, str, str | None], ...] = (
    ("api", "services/api/Dockerfile", None),
    ("ingest", "services/ingest/Dockerfile", None),
    ("workspace", "apps/workspace/Dockerfile", None),
    ("harness", "harness/Dockerfile", "OSPREY_BUILT_FROM_SHA"),
)


def _run(cmd: list[str], **kwargs: object) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)  # type: ignore[call-overload]


def build_and_scan(sha: str) -> list[str]:
    """Builds and trivy-scans all four owned images, tagged the same way the release workflow
    tags them (`<service>:<sha>` plus `:latest`). Returns every reference a real run would push,
    in push order — the list `push()` below either pushes for real or only prints."""
    refs: list[str] = []
    for service, dockerfile, build_arg_name in SERVICES:
        sha_tag = f"{REGISTRY}/{service}:{sha}"
        latest_tag = f"{REGISTRY}/{service}:latest"
        cmd = ["docker", "build", "-f", dockerfile]
        if build_arg_name is not None:
            cmd += ["--build-arg", f"{build_arg_name}={sha}"]
        cmd += ["-t", sha_tag, str(REPO_ROOT)]
        _run(cmd)
        _run(
            [
                "trivy",
                "image",
                "--scanners",
                "vuln",
                "--severity",
                "HIGH,CRITICAL",
                "--ignore-unfixed",
                "--exit-code",
                "1",
                sha_tag,
            ]
        )
        _run(["docker", "tag", sha_tag, latest_tag])
        refs += [sha_tag, latest_tag]
    return refs


def push(refs: list[str], *, dry_run: bool) -> None:
    for ref in refs:
        if dry_run:
            print(f"[dry-run] would push {ref}")
        else:
            _run(["docker", "push", ref])


def bundle() -> None:
    """`make bundle` — pull mode is its own default (round 07's fix to `tools/osprey_bundle.py`),
    so no flag is needed here; its `versions.lock` resolves the three owned images this function's
    own caller just built and (for real, non-dry-run, callers) pushed above, against the registry,
    over the network, the same `registry_digest_resolver` call the release workflow's own bundle
    job makes."""
    _run(["make", "bundle"], cwd=str(REPO_ROOT))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tools.release_local",
        description=(
            "Runs .github/workflows/release.yml's build+scan+bundle steps locally. See this "
            "module's own docstring for what --dry-run does and does not exercise."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the references that would be pushed instead of running `docker push`.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    sha = git_sha()
    if sha == "unknown":
        print("release_local: refusing — this checkout has no resolvable git sha", file=sys.stderr)
        return 1
    print(f"release_local: building from commit {sha}")

    refs = build_and_scan(sha)
    push(refs, dry_run=args.dry_run)
    bundle()

    print(
        "release_local: done"
        + (" — dry-run, nothing was pushed to the registry" if args.dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
