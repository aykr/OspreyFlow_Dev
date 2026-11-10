"""Write `pytest.mark.store` into every live test file (admin's T1 part 2, 10 November 2026).

    ../OspreyFlow_Core/.venv/bin/python -m tools.write_store_marks [--check] [file …]   (from OspreyFlow_Build)

marks each named file, or by default every live file (`tools.live_select`'s live set: the Makefile's `--ignore` list),
so the mark commit can be regenerated on the day's main in minutes rather than rebased. Each file gets the mark at
module level, once:
- with no `pytestmark`, `pytestmark = pytest.mark.store` goes after the module's imports (and `import pytest` is
  added if the file has none);
- a `pytestmark = [ … ]` list gains `pytest.mark.store` as its last item;
- a single `pytestmark = <mark>` becomes `[<mark>, pytest.mark.store]`.

A file already marked is left as it is, so running it twice changes nothing. `--check` writes nothing and exits 1
naming every file not marked. Its proof is `tests/test_write_store_marks.py`.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

MARK = "pytest.mark.store"
BUILD = Path(__file__).resolve().parents[1]


def _is_store(node: ast.expr) -> bool:
    return ast.unparse(node) in (MARK, f"{MARK}()")


def _pytestmark(tree: ast.Module) -> ast.Assign | ast.AnnAssign | None:
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets) and node.value is not None:
            return node
    return None


def is_marked(source: str) -> bool:
    node = _pytestmark(ast.parse(source))
    if node is None or node.value is None:
        return False
    value = node.value
    items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
    return any(_is_store(i) for i in items)


def _offset(lines: list[str], lineno: int, col: int) -> int:
    """A character offset into the source, from ast's line and UTF-8 byte column."""
    return sum(len(l) for l in lines[: lineno - 1]) + len(lines[lineno - 1].encode()[:col].decode())


def marked(source: str) -> str:
    """The source with the mark added, or the source as it was when it already has it."""
    if is_marked(source):
        return source
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    node = _pytestmark(tree)
    if node is not None and node.value is not None:
        value = node.value
        start = _offset(lines, value.lineno, value.col_offset)
        end = _offset(lines, value.end_lineno or value.lineno, value.end_col_offset or 0)
        old = source[start:end]
        if isinstance(value, ast.List):
            body = old[:-1].rstrip()
            if body == "[":
                new = f"[{MARK}]"
            elif "\n" in old:
                new = f"{body}{'' if body.endswith(',') else ','}\n    {MARK},\n]"
            else:
                new = f"{body}{' ' if body.endswith(',') else ', '}{MARK}]"
        else:
            new = f"[{old}, {MARK}]"
        return source[:start] + new + source[end:]
    has_pytest = any(
        isinstance(n, ast.Import) and any(a.name == "pytest" and a.asname is None for a in n.names) for n in tree.body
    )
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if imports:
        after = max(n.end_lineno or n.lineno for n in imports)
    else:
        doc = tree.body[0] if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(
            getattr(tree.body[0], "value", None), ast.Constant) else None  # fmt: skip
        after = (doc.end_lineno or doc.lineno) if doc else 0
    head = "".join(lines[:after])
    tail = "".join(lines[after:])
    if head and not head.endswith("\n"):
        head += "\n"
    block = ("import pytest\n" if not has_pytest else "") + f"\npytestmark = {MARK}\n"
    if not tail.startswith("\n"):
        block += "\n"
    return head + block + tail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write pytest.mark.store into the live test files.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 naming each file not marked")
    parser.add_argument("files", nargs="*", help="files relative to OspreyFlow_Build (default: the live set)")
    args = parser.parse_args(argv)
    if args.files:
        files = args.files
    else:
        from tools.live_select import Repo

        files = Repo().live_set()
    missing, written = [], []
    for rel in files:
        path = BUILD / rel
        source = path.read_text(encoding="utf-8")
        if is_marked(source):
            continue
        if args.check:
            missing.append(rel)
            continue
        new = marked(source)
        ast.parse(new)  # never write a file Python cannot read
        path.write_text(new, encoding="utf-8")
        written.append(rel)
    if args.check:
        for rel in missing:
            print(f"not marked store: {rel}")
        print(f"{len(files) - len(missing)} of {len(files)} live files marked store.", file=sys.stderr)
        return 1 if missing else 0
    print(f"marked {len(written)} file(s); {len(files) - len(written)} already were.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
