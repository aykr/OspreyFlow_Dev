"""The names no page on either site may carry, kept as hashes so that this repository never names them.

The owner runs this on the Mac and types or pipes the names, one per line: each client's name, its abbreviations,
and its departments and agencies. Each name's SHA-256, taken after `normalise`, is appended to `client_names.sha256`
beside this file. The script prints a count only, never a name, and asks without echoing when typed at a terminal:

    python3 OspreyFlow_Build/marketing_site/client_hashes.py              # type each name, an empty line to finish
    python3 OspreyFlow_Build/marketing_site/client_hashes.py < names.txt  # or from a file, deleted afterwards

`tests/test_sites.py` checks every run of one to six words on every page of both sites against the file.
"""

from __future__ import annotations

import getpass
import hashlib
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

HASHES = Path(__file__).with_name("client_names.sha256")
#: The longest name, in words, the check looks for.
LONGEST = 6


def normalise(text: str) -> str:
    """Lower case, `&` read as "and", every other mark a space, runs of space one: "H.M. Example & Co" and
    "hm example and co" are the same name."""
    text = text.lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def digest(name: str) -> str:
    return hashlib.sha256(normalise(name).encode("utf-8")).hexdigest()


def known() -> set[str]:
    """The hashes in the file, without its comments."""
    if not HASHES.exists():
        return set()
    lines = (line.split("#", 1)[0].strip() for line in HASHES.read_text().splitlines())
    return {line for line in lines if line}


def runs(text: str, longest: int = LONGEST) -> Iterator[str]:
    """Every run of one to `longest` words in `text`, normalised as a name is."""
    words = normalise(text).split()
    for start in range(len(words)):
        for end in range(start + 1, min(start + longest, len(words)) + 1):
            yield " ".join(words[start:end])


def named(text: str, hashes: Iterable[str]) -> set[str]:
    """The hashes of the names `text` carries (the hashes alone, so a failure never prints a name)."""
    wanted = set(hashes)
    return {h for run in runs(text) if (h := hashlib.sha256(run.encode("utf-8")).hexdigest()) in wanted}


def _typed() -> Iterator[str]:
    while name := getpass.getpass("Name (an empty line to finish): "):
        yield name


def main() -> int:
    names = _typed() if sys.stdin.isatty() else (line.rstrip("\n") for line in sys.stdin)
    have = known()
    new: list[str] = []
    for name in names:
        if not normalise(name):
            continue
        if len(normalise(name).split()) > LONGEST:
            print(f"A name longer than {LONGEST} words is not checked; it was skipped.", file=sys.stderr)
            continue
        if (h := digest(name)) not in have and h not in new:
            new.append(h)
    if new:
        with HASHES.open("a") as out:
            out.writelines(f"{h}\n" for h in new)
    print(f"{len(new)} added, {len(have) + len(new)} held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
