"""T1 part 5, item 2b: live tests that may read beyond their own rows (CARRIES: rules' kyc diagnosis, 10 November
2026: lane stacks keep every earlier run's rows, so a test asserting on a whole table or graph fails by
accumulation). A static scan, not a gate: it lists candidates for a person to judge, by four shapes.

  R1  an SQL count or select over a table with no WHERE (in a string literal of a live test file)
  R2  a graph-wide count: Gremlin `g.V().count()` / `g.E().count()` or Cypher/SQL over a type with no filter
  R3  an equality on the length of a store listing called with no arguments (`assert len(store.list_x()) == n`)
  R4  `TRUNCATE` or `DELETE FROM <t>` with no WHERE in a live test: it clears every run's rows, other lanes' too

Run from `OspreyFlow_Core`: .venv/bin/python ../OspreyFlow_Build/process/lanes/admin/t1/t1p5_reads_audit.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[4]
CORE = BUILD.parent / "OspreyFlow_Core"

SQL_COUNT = re.compile(r"\bselect\b[^;]*\bfrom\b\s+[\w.\"]+", re.I | re.S)
WHERE = re.compile(r"\bwhere\b|\bjoin\b.*\bon\b.*=\s*\$|\$\d|%s|:\w+|\{", re.I | re.S)
GRAPH_WIDE = re.compile(r"g\.[VE]\(\)\s*\.count\(\)|MATCH\s*\(\w*(:\w+)?\)\s*RETURN\s+count", re.I)
CLEAR_ALL = re.compile(r"\b(truncate\b|delete\s+from\s+[\w.\"]+\s*(;|$))", re.I)


def live_files() -> list[Path]:
    picked = subprocess.run(
        [str(CORE / ".venv/bin/python"), "-m", "tools.live_select", "--all"],
        cwd=BUILD, capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    return [BUILD / p for p in picked]


def scan(path: Path) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as exc:
        return [("parse", exc.lineno or 0, str(exc))]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if SQL_COUNT.search(text) and re.search(r"\bcount\s*\(", text, re.I) and not WHERE.search(text):
                found.append(("R1", node.lineno, " ".join(text.split())[:110]))
            if GRAPH_WIDE.search(text):
                found.append(("R2", node.lineno, " ".join(text.split())[:110]))
            if CLEAR_ALL.search(text.strip()) and "where" not in text.lower():
                found.append(("R4", node.lineno, " ".join(text.split())[:110]))
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            left = node.test.left
            if (
                isinstance(left, ast.Call) and getattr(left.func, "id", "") == "len" and left.args
                and isinstance(left.args[0], (ast.Call, ast.Await))
            ):  # fmt: skip
                inner = left.args[0].value if isinstance(left.args[0], ast.Await) else left.args[0]
                if (
                    isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and re.match(r"(list|all|fetch_all|search)", inner.func.attr)
                    and not inner.args and not inner.keywords
                    and any(isinstance(op, ast.Eq) for op in node.test.ops)
                ):  # fmt: skip
                    found.append(("R3", node.lineno, ast.unparse(node.test)[:110]))
    return found


def main() -> int:
    context = "--context" in sys.argv
    files = live_files()
    total = 0
    for path in files:
        for shape, line, text in scan(path):
            total += 1
            print(f"{shape}\t{path.relative_to(BUILD)}:{line}\t{text}")
            if context:
                lines = path.read_text().splitlines()
                for i in range(max(0, line - 6), min(len(lines), line + 3)):
                    print(f"    {i + 1}: {lines[i][:140]}")
    print(f"# {total} candidates in {len(files)} live files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
