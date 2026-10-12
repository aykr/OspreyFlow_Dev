"""`make licence-check` — enforces the allowlist in `spec/00_ARCHITECTURE.md` §7.

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
from pathlib import Path

from tools.layout import CORE
from tools.layout import REPO as REPO_ROOT

# `make licence-check` runs this file as a plain script (`$(PY) tools/licence_check.py`, no
# `-m`, no `PYTHONPATH`), which puts only `scripts/`'s own directory on `sys.path`, not the
# repository root — the same problem `tools/product_tree_link_check.py` already solved for
# importing a sibling `scripts.*` module, and the identical fix, not a second one.

sys.path.insert(0, str(CORE))

from scripts.demo_registry import REGISTRY, DemoManifest  # noqa: E402

from tools.packaging_gate import check_license_and_notice  # noqa: E402

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


#: ADR-114 Amendment 1 decision 5: a share-alike data licence is acceptable only for a pack
#: whose data is downloaded, never bundled, so the obligation never attaches to an artefact.
DOWNLOAD_ONLY_DATA_LICENCES = ("CC-BY-SA-4.0",)


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


def find_own_licence_violations(repo_root: Path = REPO_ROOT) -> list[str]:
    """The third `licence-check` leg — round 14a's own close-step addition, `process/
    07_BUILD_PLAN.md`'s Trigger A entry: the two legs above check third-party *dependency*
    licence metadata; nothing checked this project's own `LICENSE`/`NOTICE`. Reuses
    `packaging_gate.check_license_and_notice` (already built and unit-tested against fabricated
    text for a bundle's own copy) against the repository's real root files, rather than a second
    implementation of the same comparison. `repo_root` is a parameter, not always `REPO_ROOT`, so
    this test's own red-first case can point it at a planted, temporary copy instead of editing
    this repository's real `LICENSE`."""
    license_path = repo_root / "LICENSE"
    notice_path = repo_root / "NOTICE"
    return check_license_and_notice(
        license_path.read_text(encoding="utf-8") if license_path.is_file() else None,
        notice_path.read_text(encoding="utf-8") if notice_path.is_file() else None,
    )


def find_data_licence_offenders(
    registry: tuple[DemoManifest, ...] = REGISTRY,
) -> list[tuple[str, str]]:
    """`06_DECISIONS.md` ADR-035 §C7: "Neither leg inspects a data file's own embedded or
    accompanying licence... This is the fourth recorded instance of a gate verifying less than its
    name implies." Extends `make licence-check` to the one class of licence neither `pip-licenses`
    nor `license-checker` can see — a data file's own declared licence, checked against the
    identical allowlist `is_allowed` already applies to package metadata, on the reasoning that a
    licence family this codebase already accepts for code (Apache/MIT/BSD/etc.) is the same family
    it should accept for data with no further review, and anything else — a share-alike obligation
    like CDLA-Sharing-1.0 (§C6's own named case) above all — needs a human decision, not a silent
    pass.

    `None` (the generated demos — ADR-035 §C3/§C5) means no third-party data licence is declared
    and there is nothing to check. ADR-114 Amendment 1 decision 5 adds one exception: a licence in
    `DOWNLOAD_ONLY_DATA_LICENCES` is fine when the manifest's `delivery` is exactly `"download"`.
    This function returns `(demo_id, licence)` for an entry that declares a licence which is
    neither allowed nor a download-only licence on a download pack.
    """
    return [
        (manifest.id, manifest.data_licence)
        for manifest in registry
        if manifest.data_licence
        and not is_allowed(manifest.data_licence)
        and not (
            manifest.data_licence in DOWNLOAD_ONLY_DATA_LICENCES
            and manifest.delivery == "download"
        )
    ]


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
            f"{offender['License']!r} is not on the spec/00_ARCHITECTURE.md §7 allowlist",
            file=sys.stderr,
        )

    data_offenders = find_data_licence_offenders()
    for demo_id, licence in data_offenders:
        print(
            f"licence-check: demo {demo_id!r}'s own data licence {licence!r} is not on the "
            "spec/00_ARCHITECTURE.md §7 allowlist (06_DECISIONS.md ADR-035 §C7)",
            file=sys.stderr,
        )

    own_violations = find_own_licence_violations()
    for violation in own_violations:
        print(
            f"licence-check: this project's own {violation} (06_DECISIONS.md ADR-034 §B2/§B6)",
            file=sys.stderr,
        )

    if offenders or data_offenders or own_violations:
        return 1
    print(
        f"licence-check: {len(packages)} packages, all allowed "
        f"({len(REGISTRY)} demo data licence(s) checked, all allowed or undeclared); "
        "this project's own LICENSE/NOTICE present and correct."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
