"""`make licence-check` — enforces the allowlist in `docs/00_ARCHITECTURE.md` §7.

Runs `pip-licenses` against a Python environment and fails, naming every
offending package, if any reported licence is not on the allowlist. Exit 1 on
any offender, 0 otherwise.

Known gap, accepted and flagged rather than fixed here (Phase 0 plan §2.D):
`pip-licenses` reports declared licence metadata only, so the "(dynamic
linking only)" condition on LGPL-3.0 in the allowlist is not checked — an
LGPL-3.0 package passes here regardless of linkage mode. That is a
specification defect to correct in the docs, not something this script can
enforce.

Also allows PSF-2.0 (Python Software Foundation Licence 2.0), which is not
itemised in `00_ARCHITECTURE.md` §7 but is OSI-approved and permissive, and is
an unavoidable transitive licence of `typing_extensions`. Noted rather than
silently absorbed: flag to the spec owner as a missing allowlist entry.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ALLOWED_MARKERS = (
    "mit",
    "apache",
    "bsd",
    "isc",
    "mozilla public license",
    "mpl-2.0",
    "sil open font",
    "open font license",
    "psf-2.0",
    "python software foundation",
)


def is_allowed(license_text: str) -> bool:
    text = license_text.lower()
    if "lesser general public license" in text or "lgpl" in text:
        return True  # LGPL-3.0, dynamic linking only — linkage not checked, see module docstring.
    if "general public license" in text or "gpl" in text:
        return False
    return any(marker in text for marker in ALLOWED_MARKERS)


def run_pip_licenses(extra_pythonpath: str | None) -> list[dict[str, str]]:
    env = os.environ.copy()
    if extra_pythonpath:
        env["PYTHONPATH"] = extra_pythonpath + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(result.stdout)


def find_offenders(packages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [p for p in packages if not is_allowed(p["License"])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--extra-pythonpath",
        default=None,
        help="Prepended to PYTHONPATH before running pip-licenses — used to point at a fixture.",
    )
    args = parser.parse_args()

    packages = run_pip_licenses(args.extra_pythonpath)
    offenders = find_offenders(packages)
    for offender in offenders:
        print(
            f"licence-check: {offender['Name']} {offender['Version']} — "
            f"{offender['License']!r} is not on the docs/00_ARCHITECTURE.md §7 allowlist",
            file=sys.stderr,
        )
    if offenders:
        return 1
    print(f"licence-check: {len(packages)} packages, all allowed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
