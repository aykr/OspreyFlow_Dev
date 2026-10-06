"""The licence register (`00_ARCHITECTURE.md` §7) for the recogniser image's own packages, which
`make licence-check` cannot see (it reads the Conduit's environment). Run at image build: fails,
naming each package, on any licence that mentions the GPL or that matches nothing on the allowlist
(an unreadable licence fails too: default-deny). The same rule as `tools/licence_check.is_allowed`;
`tests/test_ner_licence_gate.py` fails if the two allowlists part.

Found building it (6 October 2026): Stanza 1.11 and later require udtools (GPL-2.0-or-later) and
udapi (GPL-3.0-or-later), and pip-licenses 5.0.0 reports both as UNKNOWN, which a fail-on list
of GPL names lets through; 5.5.5 reads their `License-Expression`.
"""

from __future__ import annotations

import json
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

#: The gate's own tool, and what it depends on: not shipped, removed after the check.
TOOLING = {"pip-licenses", "prettytable", "wcwidth"}


def is_allowed(license_text: str) -> bool:
    text = license_text.lower()
    if "lesser general public license" in text or "lgpl" in text:
        return True  # LGPL, dynamic linking only (the register's recorded exception)
    if "general public license" in text or "gpl" in text:
        return False
    return any(marker in text for marker in ALLOWED_MARKERS)


def offenders(packages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        p for p in packages if p["Name"].lower() not in TOOLING and not is_allowed(p["License"])
    ]


def main() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    bad = offenders(json.loads(out.stdout))
    for p in bad:
        print(f"licence-gate: {p['Name']} {p['Version']} is {p['License']!r}, not on the allowlist")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
