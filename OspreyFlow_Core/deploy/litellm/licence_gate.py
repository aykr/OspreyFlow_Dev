"""The gateway image's licence gate: fails the build if the publisher's commercially licensed
package or folder, or any distribution declaring a proprietary licence, is in the image.

The gateway is built from the publisher's MIT files alone (the owner's ruling of 21 November 2026).
The publisher's `proxy` extra names one proprietary package (`litellm-enterprise`, declared
`LicenseRef-Proprietary`), and its own image also carries a folder of commercially licensed source
under `/app/enterprise`. Neither may be in ours. `overrides.txt` keeps the package out of the
install; this gate is the check that it stayed out, and that nothing else proprietary came in
behind it, read from what is installed rather than from what was asked for. It runs in the builder
over the venv just installed and again in the final image over what was copied in (the stages are
separate: a later `COPY` could add what the builder never had), and is removed from the image.

What it reads: every `*.dist-info/METADATA` in the site-packages folder given (the name, and the
licence as `License-Expression`, `License` and the `License ::` classifiers declare it), the folders
of that folder, and, with `--app`, the application root. What it refuses, each naming the thing:

- a distribution called `litellm-enterprise` (however the name is written), whatever it declares;
- a distribution declaring a proprietary licence (`LicenseRef-Proprietary`, `Proprietary`, the
  classifier `License :: Other/Proprietary License`), under any name;
- a folder `litellm_enterprise` in the site-packages folder, with or without metadata (a copied
  tree carries none);
- an `enterprise` folder in the application root.

It is a deny list, not an allowlist: a distribution that declares nothing passes (the register's
definition for the code, `tools/licence_check.py`, is the allowlist for what the product installs
itself; this image's own packages are the publisher's, held to the versions its image was measured
with). The test that runs it over planted metadata is `tests/harness/test_own_gateway_image.py`.
Standard library only: it runs before anything is installed that could be trusted.
"""

from __future__ import annotations

import re
import sys
from email.parser import Parser
from pathlib import Path

#: The one package the publisher's `proxy` extra names that is proprietary, by its normalised name.
FORBIDDEN_NAMES = frozenset({"litellm-enterprise"})
#: Folders that are that package or the publisher's commercial folder, by name.
FORBIDDEN_PACKAGE_FOLDERS = frozenset({"litellm_enterprise"})
FORBIDDEN_APP_FOLDERS = frozenset({"enterprise"})
#: A licence field longer than this is a pasted licence text, not an identifier: read for its
#: first line only (a GPL text quoted in a `License:` field mentions "proprietary" and is not).
LONGEST_IDENTIFIER = 200

_PROPRIETARY = re.compile(r"proprietary", re.I)


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_licences(metadata: str) -> list[str]:
    """Each licence statement a `METADATA` file makes, as written."""
    message = Parser().parsestr(metadata, headersonly=True)
    found = [str(v) for v in message.get_all("License-Expression") or []]
    for value in message.get_all("License") or []:
        text = " ".join(str(value).split())
        found.append(text if len(text) <= LONGEST_IDENTIFIER else " ".join(
            str(value).splitlines()[0].split()
        ))  # fmt: skip
    found += [
        str(c) for c in message.get_all("Classifier") or [] if str(c).startswith("License ::")
    ]
    return found


def check(site_packages: Path, app_root: Path | None = None) -> list[str]:
    """Every reason the folder (and the application root, when given) holds what it must not;
    empty when it holds none."""
    problems: list[str] = []
    for info in sorted(site_packages.glob("*.dist-info")):
        metadata = info / "METADATA"
        if not metadata.is_file():
            problems.append(f"{info.name}: no METADATA, so what it declares cannot be read")
            continue
        text = metadata.read_text(encoding="utf-8", errors="replace")
        name = str(Parser().parsestr(text, headersonly=True).get("Name") or info.name)
        if _normal(name) in FORBIDDEN_NAMES:
            problems.append(f"{name}: the publisher's commercially licensed package is installed")
        for licence in _declared_licences(text):
            if _PROPRIETARY.search(licence):
                problems.append(f"{name}: declares the proprietary licence {licence!r}")
                break
    for folder in sorted(site_packages.iterdir()):
        if folder.is_dir() and folder.name in FORBIDDEN_PACKAGE_FOLDERS:
            problems.append(f"{folder.name}: the commercially licensed package's folder is present")
    if app_root is not None and app_root.is_dir():
        for name in sorted(FORBIDDEN_APP_FOLDERS):
            if (app_root / name).exists():
                problems.append(f"{app_root / name}: the commercially licensed folder is present")
    return problems


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    app: Path | None = None
    if "--app" in arguments:
        at = arguments.index("--app")
        if at + 1 >= len(arguments):
            print("licence-gate: --app needs the application root", file=sys.stderr)
            return 2
        app = Path(arguments[at + 1])
        del arguments[at : at + 2]
    if len(arguments) != 1:
        print("usage: licence_gate.py <site-packages folder> [--app <application root>]",
              file=sys.stderr)  # fmt: skip
        return 2
    site = Path(arguments[0])
    if not site.is_dir():
        print(f"licence-gate: {site} is not a folder, so nothing was checked", file=sys.stderr)
        return 2
    problems = check(site, app)
    for problem in problems:
        print(f"licence-gate: {problem}", file=sys.stderr)
    if problems:
        return 1
    read = len(list(site.glob("*.dist-info")))
    print(f"licence-gate: {read} distributions read, none proprietary, no commercial folder")
    return 0


if __name__ == "__main__":
    sys.exit(main())
