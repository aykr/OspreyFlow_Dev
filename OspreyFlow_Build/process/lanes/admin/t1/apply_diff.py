"""Apply (or, with --reverse, take back) one of this lane's diffs to shared files, for a gate run
where there is no git checkout to `git apply` in (the server's copy of the worktree). Paths in the
diff are relative to the repository root. Run from anywhere:

    python3 OspreyFlow_Build/process/lanes/admin/t1/apply_diff.py [--reverse] <diff>…

**All or nothing** (T1 part 5's review): each hunk's old lines must occur exactly once in their
file, whole lines at line boundaries (a hunk never matches inside a longer line), or nothing is
written. Every changed file is written to a temporary beside it first, and only once all are written
are they renamed into place. A hunk is read by the line counts its `@@` header gives, so a removed
line that itself begins `-- ` is never taken for the next file's header.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def hunks(diff: str) -> list[tuple[str, str, str]]:
    """(path, old lines, new lines) for every hunk, each a block of whole lines."""
    out: list[tuple[str, str, str]] = []
    path = ""
    lines = diff.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if line.startswith("--- /dev/null") or line.startswith("+++ /dev/null"):
            raise SystemExit("refused: a diff making or removing a file is not applied here")
        if line.startswith("+++ "):
            path = line[4:].split("\t")[0].removeprefix("b/")
            continue
        found = HUNK.match(line)
        if not found:
            continue
        left = int(found.group(1) or 1)
        right = int(found.group(2) or 1)
        old: list[str] = []
        new: list[str] = []
        while (left or right) and i < len(lines):
            body = lines[i]
            i += 1
            if body.startswith("\\"):  # "\ No newline at end of file"
                continue
            tag, text = body[:1], body[1:]
            if tag in (" ", ""):
                old.append(text)
                new.append(text)
                left, right = left - 1, right - 1
            elif tag == "-":
                old.append(text)
                left -= 1
            elif tag == "+":
                new.append(text)
                right -= 1
        out.append((path, "".join(f"{x}\n" for x in old), "".join(f"{x}\n" for x in new)))
    return out


def at_line_starts(text: str, block: str) -> list[int]:
    """Where `block` (whole lines) occurs in `text`, starting at the beginning of a line."""
    found, start = [], 0
    while (i := text.find(block, start)) != -1:
        if i == 0 or text[i - 1] == "\n":
            found.append(i)
        start = i + 1
    return found


def main() -> int:
    reverse = "--reverse" in sys.argv
    diffs = [a for a in sys.argv[1:] if a != "--reverse"]
    planned: dict[Path, str] = {}
    for d in diffs:
        for path, old, new in hunks(Path(d).read_text()):
            if reverse:
                old, new = new, old
            target = ROOT / path
            text = planned.get(target, target.read_text())
            where = at_line_starts(text, old)
            if len(where) != 1:
                n = len(where)
                print(f"refused: a hunk of {d} matches {n} times in {path}; nothing written")
                return 1
            planned[target] = text[: where[0]] + new + text[where[0] + len(old) :]
    temporaries: list[tuple[Path, Path]] = []
    try:
        for target, text in planned.items():
            temporary = target.with_name(f".{target.name}.apply_diff")
            temporary.write_text(text)
            os.chmod(temporary, target.stat().st_mode)
            temporaries.append((temporary, target))
    except OSError as error:
        for temporary, _ in temporaries:
            temporary.unlink(missing_ok=True)
        print(f"refused: {error}; nothing written")
        return 1
    for temporary, target in temporaries:
        os.replace(temporary, target)
        print(f"{'took back' if reverse else 'applied'}: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
