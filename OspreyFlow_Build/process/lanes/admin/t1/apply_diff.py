"""Apply (or, with --reverse, take back) one of this lane's diffs to shared files, for a gate run
where there is no git checkout to `git apply` in (the server's copy of the worktree). Paths in the
diff are relative to the repository root. Run from anywhere:

    python3 OspreyFlow_Build/process/lanes/admin/t1/apply_diff.py [--reverse] <diff>…

**All or nothing** (T1 part 5's review): each hunk's old lines must occur exactly once in their
file, whole lines at line boundaries (a hunk never matches inside a longer line), or nothing is
written. Every changed file is written to a temporary beside it and copied to a backup first; the
temporaries are then renamed into place, and if any rename fails, every file already renamed is put
back from its backup. A hunk is read by the line counts its `@@` header gives (a removed line that
itself begins `-- ` is never taken for a header), the diff and the files are split on "\n" alone (a
"\r" stays part of its line, so a CRLF file keeps its endings), and "\\ No newline at end of file"
is honoured on either side.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as f:  # no newline translation: "\r\n" kept
        return f.read()


def write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


def block(lines: list[tuple[str, bool]]) -> str:
    """Lines as the file holds them: each ends in "\n" unless marked as the last, with none."""
    return "".join(text + ("\n" if newline else "") for text, newline in lines)


def hunks(diff: str) -> list[tuple[str, str, str]]:
    """(path, old text, new text) for every hunk, each a block of whole lines."""
    out: list[tuple[str, str, str]] = []
    path = ""
    lines = diff.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
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
        old: list[tuple[str, bool]] = []
        new: list[tuple[str, bool]] = []
        last = ""  # the side(s) of the line before a "\ No newline" marker
        while i < len(lines) and (left or right or lines[i].startswith("\\")):
            body = lines[i]
            i += 1
            if body.startswith("\\"):  # "\ No newline at end of file": the line before it has none
                if last in ("-", " "):
                    old[-1] = (old[-1][0], False)
                if last in ("+", " "):
                    new[-1] = (new[-1][0], False)
                continue
            tag, text = body[:1], body[1:]
            if tag in (" ", ""):
                old.append((text, True))
                new.append((text, True))
                left, right = left - 1, right - 1
                last = " "
            elif tag == "-":
                old.append((text, True))
                left -= 1
                last = "-"
            elif tag == "+":
                new.append((text, True))
                right -= 1
                last = "+"
        out.append((path, block(old), block(new)))
    return out


def at_line_starts(text: str, part: str) -> list[int]:
    """Where `part` (whole lines) occurs in `text`: at the start of a line, and ending at the end of
    one (or of the file)."""
    found, start = [], 0
    while (i := text.find(part, start)) != -1:
        end = i + len(part)
        starts_line = i == 0 or text[i - 1] == "\n"
        ends_line = part.endswith("\n") or end == len(text)
        if starts_line and ends_line:
            found.append(i)
        start = i + 1
    return found


def main() -> int:
    reverse = "--reverse" in sys.argv
    diffs = [a for a in sys.argv[1:] if a != "--reverse"]
    planned: dict[Path, str] = {}
    for d in diffs:
        for path, old, new in hunks(read(Path(d))):
            if reverse:
                old, new = new, old
            target = ROOT / path
            text = planned.get(target, read(target))
            where = at_line_starts(text, old)
            if len(where) != 1:
                n = len(where)
                print(f"refused: a hunk of {d} matches {n} times in {path}; nothing written")
                return 1
            planned[target] = text[: where[0]] + new + text[where[0] + len(old) :]
    staged: list[tuple[Path, Path, Path]] = []  # (temporary, backup, target)
    try:
        for target, text in planned.items():
            temporary = target.with_name(f".{target.name}.apply_diff")
            backup = target.with_name(f".{target.name}.apply_diff_backup")
            write(temporary, text)
            os.chmod(temporary, target.stat().st_mode)
            shutil.copy2(target, backup)
            staged.append((temporary, backup, target))
    except OSError as error:
        for temporary, backup, _ in staged:
            temporary.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)
        print(f"refused: {error}; nothing written")
        return 1
    done: list[tuple[Path, Path]] = []
    try:
        for temporary, backup, target in staged:
            os.replace(temporary, target)
            done.append((backup, target))
    except OSError as error:
        for backup, target in done:
            os.replace(backup, target)  # put back what was already renamed
        for temporary, backup, _ in staged:
            temporary.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)
        print(f"refused: {error}; every file put back as it was")
        return 1
    for _, backup, target in staged:
        backup.unlink(missing_ok=True)
        print(f"{'took back' if reverse else 'applied'}: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
