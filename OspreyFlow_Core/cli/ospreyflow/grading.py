"""`ospreyflow grading change` (`06_DECISIONS.md` ADR-143 decision 11 and Amendment 6; the owner's
ruling C13): the deployment's grading scheme changed, the drawn items and the setting together.

    ospreyflow grading change --to <scheme or scheme file> --mapping <file> --dry-run
    ospreyflow grading change --to <scheme or scheme file> --mapping <file> --confirm <token> \
        [--stop-api]

A thin verb over `scripts/grading_change.py`, which it runs inside the deployment, in a one-shot
from the Conduit's image on the deployment's own network, as a load's revert runs (the mapping and
any scheme file mounted read-only, never copied into the image). The dry run may run beside a
running Conduit: it writes nothing, and gives the token the change needs. The change is refused
while the Conduit runs unless `--stop-api` says to stop it, since a drawing made during the change,
or before the deployment starts again in the new scheme, would be in the old one.

After the change, and only then, the verb sets `grading.scheme` in `osprey.yaml` (a scheme file is
copied beside it first), renders the deployment again (`harness.apply --reapply`) and starts the
Conduit, so the boards offer the new scheme's grades. A refusal changes nothing, and the Conduit is
started again as it was. A run stopped part way leaves the Conduit stopped and says so: the dry run
and the same change again finish it, and only then is the setting changed.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

#: The command inside the Conduit's image.
GRADING_PATH = ("-m", "scripts.grading_change")
#: Where the mapping and a scheme file are mounted in the one-shot.
IN_CONTAINER = "/grading"
#: The command's exits that mean nothing was changed: refused before any write (1), a usage
#: error or no store settings (64). Any other is a change that may have written (2: stopped part
#: way or failed unforeseen; a killed one-shot's 137), so the Conduit is never restarted in the
#: old scheme over it.
NOTHING_CHANGED = (1, 64)


def is_scheme_file(to: str) -> bool:
    """A scheme file by its name; which names are built-in schemes is the deployment schema's to
    say (`schemas.domain.GRADING_PARTS`), inside the Conduit's image, not this verb's."""
    return to.endswith((".yaml", ".yml"))


def scheme_file_beside(config_path: Path, scheme_file: Path) -> str:
    """The scheme file copied beside `osprey.yaml` (`grading-scheme.yaml`), so the setting names a
    file the deployment keeps, never one in a folder the operator may tidy away. The setting's
    value, relative to `osprey.yaml`."""
    kept = config_path.parent / "grading-scheme.yaml"
    if scheme_file.resolve() != kept.resolve():
        shutil.copyfile(scheme_file, kept)
    return kept.name


_SECTION = re.compile(r"^grading:[ \t]*(#.*)?$", re.MULTILINE)
#: The next top-level key: a comment at column 0 does not end the section.
_TOP_LEVEL = re.compile(r"^[^\s#]", re.MULTILINE)
_SCHEME = re.compile(r"^([ \t]+scheme:[ \t]*)([^#\n]*?)([ \t]*(#.*)?)$", re.MULTILINE)


def with_grading_scheme(text: str, scheme: str) -> str:
    """`osprey.yaml`'s text with `grading.scheme` set to `scheme` and nothing else changed: the
    file's comments and order are the owner's, so it is edited in place, never dumped again."""
    section = _SECTION.search(text)
    if section is None:
        joined = text if text.endswith("\n") or not text else text + "\n"
        return f"{joined}grading:\n  scheme: {scheme}\n"
    start = section.end()
    following = _TOP_LEVEL.search(text, start + 1)
    end = following.start() if following else len(text)
    body = text[start:end]
    line = _SCHEME.search(body)
    if line is None:
        body = f"\n  scheme: {scheme}" + body
    else:
        body = body[: line.start(2)] + scheme + body[line.end(2) :]
    return text[:start] + body + text[end:]


def scheme_set(text: str) -> str | None:
    """`grading.scheme` as `osprey.yaml`'s text says it, read as YAML reads it (the last of a
    repeated key wins): the check that the edit took."""
    try:
        loaded = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return None
    section = loaded.get("grading") if isinstance(loaded, dict) else None
    scheme = section.get("scheme") if isinstance(section, dict) else None
    return str(scheme) if scheme is not None else None
