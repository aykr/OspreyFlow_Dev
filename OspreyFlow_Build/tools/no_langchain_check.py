"""An image or deployment without Laurium carries no LangChain, spaCy or Laurium
(`06_DECISIONS.md` ADR-135 Amendment 6 decision 1; the owner's ruling 1 of 11 November 2026).

Laurium runs in its own image (`services/laurium/`), built only when it is chosen; nothing of it, or
of the LangChain it brings, is in the Conduit's or any other image. Two legs, each a refusal in words
and never a pass on anything it cannot read:

- **the source leg** (no flag; offline, in `make ci`): the Conduit's build context leaves every file
  of Laurium's folder out (read with the repository's own `.dockerignore` matcher,
  `tests/test_dockerignore.py`'s, so any pattern that does so passes and one that leaves a file in is
  named, a file a `!` negation puts back among them); the Conduit's `pyproject.toml` and
  `uv.lock` name no LangChain, LangSmith, Laurium or spaCy model package (spaCy itself is in the
  lock only as ADR-108's optional `extraction` extra, which no image installs, so the image leg
  refuses it where the lock may not); and no Dockerfile but Laurium's installs any of them;
- **the image leg** (`--image <ref>`, after CI builds each image): the distributions installed in
  the built image, read by `IMAGE_SCRIPT` with the image's own Python (`docker run`), must include
  no LangChain, LangSmith, Laurium, spaCy or spaCy model. With `--image` the image leg runs alone:
  CI's image steps run this with the runner's own Python, and the source leg is its own job.

Each refusal shown red in `tests/test_no_langchain_check.py` (rule 15), on the shape each leg reads.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from tools.layout import CORE

#: Files of Laurium's folder that name LangChain or Laurium, checked whether or not a copied tree
#: carries them; every file the folder really holds is checked besides.
_LAURIUM_FILES = ("Dockerfile", "requirements.txt", "requirements.in", "app.py")

#: Distributions that come with Laurium and nothing else, by normalised name.
_FORBIDDEN = re.compile(r"^(langchain(-[a-z0-9-]+)?|langsmith|laurium|spacy(-[a-z0-9-]+)?|en-core-web-[a-z]+)$")
#: In the Conduit's lock and project, spaCy is allowed as ADR-108's optional extra; the rest never.
_FORBIDDEN_IN_SOURCE = re.compile(r"^(langchain(-[a-z0-9-]+)?|langsmith|laurium|en-core-web-[a-z]+)$")

#: Run inside an image by its own Python: every installed distribution's name and version, as JSON.
IMAGE_SCRIPT = (
    "import json, importlib.metadata as m; "
    "print(json.dumps(sorted(({'name': d.metadata['Name'], 'version': d.version} "
    "for d in m.distributions() if d.metadata['Name']), key=lambda r: r['name'].lower())))"
)


class Unreadable(Exception):
    """The image's distributions could not be read: a refusal, never a pass."""


def _normalised(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def forbidden_in_image(printed: str) -> list[str]:
    """`name version` for each forbidden distribution in `IMAGE_SCRIPT`'s output."""
    try:
        rows = json.loads(printed)
        if not isinstance(rows, list):
            raise ValueError("not a list")
        found = [
            f"{row['name']} {row['version']}"
            for row in rows
            if _FORBIDDEN.match(_normalised(str(row["name"])))
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise Unreadable(f"the image's installed distributions could not be read: {exc}") from None
    return found


def _named_packages(text: str) -> set[str]:
    """Package names a pyproject or lock declares: `name = "x"` entries and quoted requirements."""
    names = set(re.findall(r'^name\s*=\s*"([^"]+)"', text, re.M))
    names |= set(re.findall(r'\{\s*name\s*=\s*"([^"]+)"', text))
    names |= set(re.findall(r'^\s*"([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*[<>=!~;"]', text, re.M))
    return {_normalised(n) for n in names}


def _outside_laurium(core: Path, path: Path) -> bool:
    parts = path.relative_to(core).parts
    return parts[:2] != ("services", "laurium") and not {"node_modules", ".venv"} & set(parts)


def _laurium_files(core: Path) -> list[str]:
    folder = core / "services" / "laurium"
    found = {f"services/laurium/{name}" for name in _LAURIUM_FILES}
    if folder.is_dir():
        found |= {
            p.relative_to(core).as_posix()
            for p in folder.rglob("*")
            if p.is_file() and not {".venv", "__pycache__"} & set(p.relative_to(folder).parts)
        }
    return sorted(found)


def _context_problems(core: Path) -> list[str]:
    """Laurium's folder out of the Conduit's build context, read as Docker reads `.dockerignore`
    with the repository's own matcher (the same `pathspec` gitignore reading as
    `tests/test_dockerignore.py`, imported from it so the two cannot part)."""
    from tests.test_dockerignore import _spec

    ignore = core / ".dockerignore"
    text = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    problems: list[str] = []
    spec = _spec(text)
    kept = [path for path in _laurium_files(core) if not spec.match_file(path)]
    if kept:
        problems.append(
            ".dockerignore leaves part of services/laurium in the Conduit's build context: "
            + ", ".join(kept[:5])
        )
    return problems


def source_problems(core: Path = CORE) -> list[str]:
    from tools.licence_check import _instructions

    problems = _context_problems(core)
    for name in ("pyproject.toml", "uv.lock"):
        path = core / name
        if not path.is_file():
            problems.append(f"{name} could not be read")
            continue
        bad = sorted(n for n in _named_packages(path.read_text(encoding="utf-8")) if _FORBIDDEN_IN_SOURCE.match(n))
        if bad:
            problems.append(f"{name} names {', '.join(bad)}, which only Laurium's image may carry")
    # Every other Dockerfile, read as instructions (continued lines joined, comments left out), and
    # every other requirements file: a forbidden name anywhere in them is refused, whatever installs
    # it (a continued line, a build argument, uv or pip).
    files = [p for p in sorted(core.rglob("Dockerfile*")) if _outside_laurium(core, p)]
    files += [
        p
        for pattern in ("*requirements*.txt", "*requirements*.in")
        for p in sorted(core.rglob(pattern))
        if _outside_laurium(core, p)
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        lines = _instructions(text) if path.name.startswith("Dockerfile") else [
            line.split("#", 1)[0] for line in text.splitlines()
        ]  # fmt: skip
        words = {w for line in lines for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", line)}
        bad = sorted({w for w in words if _FORBIDDEN.match(_normalised(re.split(r"[=<>]", w)[0]))})
        if bad:
            relative = path.relative_to(core).as_posix()
            problems.append(f"{relative} names {', '.join(bad)}, which only Laurium's image may carry")
    return problems


def _image_distributions(image: str) -> str:
    try:
        out = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "python", image, "-c", IMAGE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Unreadable(f"{image} could not be run: {exc}") from None
    if out.returncode != 0:
        raise Unreadable(f"{image} could not be read (exit {out.returncode})")
    return out.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", action="append", default=[], help="a built image to read")
    args = parser.parse_args(argv)
    problems = [] if args.image else source_problems()
    for image in args.image:
        try:
            found = forbidden_in_image(_image_distributions(image))
        except Unreadable as exc:
            problems.append(str(exc))
            continue
        problems += [f"{image} carries {name}, which only Laurium's image may" for name in found]
    for problem in problems:
        print(f"no-langchain-check: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(
        "no-langchain-check: no LangChain, spaCy or Laurium outside Laurium's own image "
        f"({', '.join(args.image) if args.image else 'source'})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
