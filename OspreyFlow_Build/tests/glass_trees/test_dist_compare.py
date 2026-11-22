"""`OspreyFlow_Core/scripts/dist_compare.mjs`: compares two builds of `apps/workspace` and tolerates only what a file's
new path causes (ADR-152 invariant I11; the owner's condition (a) of 20 November 2026; slice PL4a).

The owner's condition: the script "tolerates differences that come only from a file's new path (chunk names, module
order, source maps) and fails on a real change, shown red on a planted change of behaviour and green on a planted move
before any later slice relies on it". This file is that demonstration, in two kinds of build:

* **Synthetic builds in the shape `vite build` writes** (`write_build`): a main chunk of top-level statements with
  declarators, an arrow-free function, a dynamic import and a static import cycle with a lazy chunk; a stylesheet that
  names a font; hashed assets; unhashed public files; an `index.html` naming the chunks. A *move* is the same build
  with other chunk names and hashes, the statements and declarators in another order, other identifier names,
  source maps, and a differently written stylesheet. Each *planted change* is that move **plus** one change of
  behaviour, so a red result is a red for that change and nothing else.
* **Real `vite build` output** (`test_a_real_vite_build_*`): a toy project built by the repository's own Vite, then the
  same code at other paths with other file names (and with its imports in another order), then one real change each.

Which test fails if the invariant is broken (rule 12):

* a **real change goes unseen** (a different string, a changed condition, a changed number, a removed statement, a
  removed export, a removed declarator, a different CSS rule or CSS order, a changed or removed asset, a changed public
  file, a rewired chunk, **a reference or an import pointed at another binding of the same shape**):
  `test_a_planted_change_of_behaviour_is_red` (one case each) and, over real output,
  `test_a_real_vite_build_with_one_real_change_is_red`;
* a **move is read as a change** (so every later slice would fail on a harmless move):
  `test_a_planted_move_is_green`, `test_a_move_with_the_statements_in_another_order_is_green` and
  `test_a_real_vite_build_moved_to_other_paths_is_green`;
* the **baseline record** is wrong or absent: `test_the_committed_baseline_record_is_complete`,
  `test_record_*` and `test_verify_*`.

A planted change that some other difference would have caught proves nothing (rule 15), so the changed build is the
move plus that one change alone (and the move alone is green, `test_every_part_of_the_move_is_tolerated_alone`);
`test_every_planted_change_alone_makes_the_builds_differ` checks that each change is red with nothing moved at all.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
SCRIPT = CORE / "scripts" / "dist_compare.mjs"
RECORD = CORE / "apps" / "workspace" / "PL4_BASELINE.json"
# The version the script's normaliser has (`NORMALISER_VERSION`): a record is comparable only with the same one.
NORMALISER_VERSION = 2


def node() -> str:
    found = shutil.which("node")
    assert found, "node is needed"
    return found


def run(*args: str | Path, cwd: Path = CORE) -> tuple[int, str]:
    done = subprocess.run([node(), str(SCRIPT), *map(str, args)], cwd=cwd, capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout + done.stderr


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def token(seed: str, what: str) -> str:
    """Eight characters of the alphabet Vite's content hashes use."""
    return base64.urlsafe_b64encode(hashlib.sha256(f"{seed}:{what}".encode()).digest())[:8].decode()


# ---------------------------------------------------------------------------------------------- synthetic builds


@dataclasses.dataclass(frozen=True)
class Build:
    """One build in the shape `vite build` writes. Every field is something a move may change, or a behaviour a test
    may plant a change in; the defaults are the build that is compared against."""

    # What a move changes ----------------------------------------------------------------------------------
    names: str = "etnriaosc"  # the identifier a minifier gave each of nine slots
    seed: str = "a"  # the content hashes in file names
    reverse: bool = False  # statements and declarators in the other order (module order)
    maps: bool = False  # source maps, and the comment that names one
    main_stem: str = "index"  # the chunk names
    lazy_stem: str = "GlassCanvas"
    css_pretty: bool = False  # the stylesheet written with newlines, indents and comments
    # What a planted change alters ---------------------------------------------------------------------------
    greeting: str = "ready"
    compare_op: str = ">"
    threshold: int = 10
    answer: int = 42
    prop: str = "count"
    drop: tuple[str, ...] = ()
    extra: str = ""
    lib_count: int = 2  # declarators in the first `var`
    export_names: tuple[str, ...] = ("t", "n")
    css: tuple[str, ...] = (".a{color:red}", ".b{margin:0 auto}", "@media (min-width:600px){.c{padding:4px}}")
    logo: bytes = b"<svg>logo</svg>"
    font: bytes = b"\x00font-bytes"
    keep_font: bool = True
    crown: str = "<svg>crown</svg>"
    crown_name: str = "crown.svg"
    lazy_uses_main: bool = True
    extra_asset: bytes | None = None
    # Which of the main chunk's constants (slot 4: the number, slot 5: the greeting) a statement of its own logs, and
    # which of the lazy chunk's two exports (`t` or `u`) the main chunk imports: a reference rewired to another binding.
    show: int = 5
    import_name: str = "t"

    def main_file(self) -> str:
        return f"{self.main_stem}-{token(self.seed, 'main')}.js"

    def css_file(self) -> str:
        return f"{self.main_stem}-{token(self.seed, 'css')}.css"

    def lazy_file(self) -> str:
        return f"{self.lazy_stem}-{token(self.seed, 'lazy')}.js"

    def font_file(self) -> str:
        return f"font-{token(self.seed, 'font')}.woff2"

    def logo_file(self) -> str:
        return f"logo-{token(self.seed, 'logo')}.svg"


def main_chunk(b: Build) -> str:
    s = list(b.names)
    declarators = [f"{s[0]}=Object.create", f"{s[1]}=Object.defineProperty"][: b.lib_count]
    if b.reverse:
        declarators.reverse()
    statements = {
        "lib": f"var {','.join(declarators)};" if declarators else "",
        "size": f"function {s[2]}({s[3]}){{return {s[3]}{b.compare_op}{b.threshold}?`big`:`small`}}",
        "consts": f"var {s[4]}={b.answer},{s[5]}=`{b.greeting}`;",
        "obj": f"var {s[6]}={{{b.prop}:1,items:[2,3]}};",
        "run": f"{s[2]}({s[4]}),console.log({s[5]});",
        "show": f"console.warn({s[b.show]});",
        "imported": f"console.debug({s[8]});",
        "lazy": f'function {s[7]}(){{return import("./{b.lazy_file()}")}}',
        "extra": b.extra,
    }
    order = [name for name in statements if name not in b.drop and statements[name]]
    if b.reverse:
        order.reverse()
    exports = ",".join(f"{s[2 if name == 't' else 4]} as {name}" for name in b.export_names)
    head = f'import{{{b.import_name} as {s[8]}}}from"./{b.lazy_file()}";'
    tail = f"export{{{exports}}};" if exports else ""
    comment = f"\n//# sourceMappingURL={b.main_file()}.map" if b.maps else ""
    return head + "".join(statements[name] for name in order) + tail + comment + "\n"


def lazy_chunk(b: Build) -> str:
    s = list(reversed(b.names))
    if b.lazy_uses_main:
        return f'import{{t as {s[0]}}}from"./{b.main_file()}";var {s[1]}={s[0]}(5),{s[2]}=`other`;export{{{s[1]} as t,{s[2]} as u}};\n'
    return f"var {s[1]}=5,{s[2]}=`other`;export{{{s[1]} as t,{s[2]} as u}};\n"


def css_text(b: Build) -> str:
    font_rule = f"@font-face{{font-family:F;src:url(/assets/{b.font_file()})}}" if b.keep_font else ""
    rules = [font_rule, *b.css] if font_rule else list(b.css)
    if not b.css_pretty:
        return "".join(rules) + "\n"
    pretty = []
    for rule in rules:
        rule = rule.replace("{", " {\n  ").replace(";", ";\n  ").replace("}", "\n}")
        pretty.append(f"/* generated */\n{rule}\n")
    return "\n".join(pretty)


def write_build(root: Path, b: Build) -> Path:
    write(root / "assets" / b.main_file(), main_chunk(b))
    write(root / "assets" / b.lazy_file(), lazy_chunk(b))
    write(root / "assets" / b.css_file(), css_text(b) + ("/*# sourceMappingURL=x.css.map */\n" if b.maps else ""))
    write(root / "assets" / b.logo_file(), b.logo)
    if b.keep_font:
        write(root / "assets" / b.font_file(), b.font)
    if b.extra_asset is not None:
        write(root / "assets" / f"extra-{token(b.seed, 'extra')}.png", b.extra_asset)
    if b.maps:
        write(root / "assets" / f"{b.main_file()}.map", '{"version":3,"sources":["../src/main.ts"]}')
    # Files a page asks for by name: no hash in the name.
    write(root / "assets" / "govuk" / b.crown_name, b.crown)
    write(
        root / "index.html",
        '<!doctype html>\n<html lang="en">\n  <head>\n'
        f'    <script type="module" crossorigin src="/assets/{b.main_file()}"></script>\n'
        f'    <link rel="stylesheet" crossorigin href="/assets/{b.css_file()}">\n'
        "  </head>\n  <body>\n    <div id=\"root\"></div>\n  </body>\n</html>\n",
    )
    write(root / "cookies.html", "<!doctype html><title>Cookies</title>\n")
    return root


# What a move changes, and nothing else. Every planted change below is this plus one field.
MOVE = dict(
    names="xyzwvutsr",
    seed="b",
    reverse=True,
    maps=True,
    main_stem="entry",
    lazy_stem="canvas",
    css_pretty=True,
)


def compare(tmp: Path, before: Build, after: Build) -> tuple[int, str]:
    write_build(tmp / "before", before)
    write_build(tmp / "after", after)
    return run("compare", tmp / "before", tmp / "after")


# ---------------------------------------------------------------------------------------------- the planted move: green


def test_the_same_build_is_the_same(tmp_path: Path) -> None:
    code, output = compare(tmp_path, Build(), Build())
    assert code == 0, output
    assert output.startswith("SAME")


def test_a_planted_move_is_green(tmp_path: Path) -> None:
    """The same code at another path: other chunk names and hashes, other module order, other identifier names,
    source maps, another way of writing the stylesheet."""
    code, output = compare(tmp_path, Build(), Build(**MOVE))
    assert code == 0, output
    assert output.startswith("SAME")


@pytest.mark.parametrize("change", sorted(MOVE))
def test_every_part_of_the_move_is_tolerated_alone(tmp_path: Path, change: str) -> None:
    code, output = compare(tmp_path, Build(), Build(**{change: MOVE[change]}))
    assert code == 0, f"{change}: {output}"


def test_a_move_with_the_statements_in_another_order_is_green(tmp_path: Path) -> None:
    """Module order: the same statements in the reverse order, the declarators of a `var` too."""
    code, output = compare(tmp_path, Build(), Build(reverse=True))
    assert code == 0, output


def test_two_chunks_that_name_each_other_are_matched_by_what_they_hold(tmp_path: Path) -> None:
    """The main chunk imports the lazy one and the lazy one imports the main: a cycle. Both are renamed, and the
    hashes in their names are different, so only reading each reference as the content it names can match them."""
    before, after = Build(), Build(seed="zz", main_stem="other", lazy_stem="elsewhere")
    assert before.main_file() != after.main_file() and before.lazy_file() != after.lazy_file()
    code, output = compare(tmp_path, before, after)
    assert code == 0, output


# ---------------------------------------------------------------------------------------------- planted changes: red

# (id, the one field changed, a string the report must show)
CHANGES: list[tuple[str, dict[str, object], str]] = [
    ("a different string", {"greeting": "steady"}, "steady"),
    ("a changed condition", {"compare_op": ">="}, ">="),
    ("a changed number in the condition", {"threshold": 11}, "11"),
    ("a changed constant", {"answer": 43}, "43"),
    ("a different property name", {"prop": "total"}, "total"),
    ("a removed function", {"drop": ("size",)}, "big"),
    ("a removed statement", {"drop": ("run",)}, "console.log"),
    ("an added statement", {"extra": "console.log(`added`);"}, "added"),
    ("a removed declarator", {"lib_count": 1}, "Object.defineProperty"),
    ("a removed export", {"export_names": ("t",)}, "export:"),
    ("a different CSS value", {"css": (".a{color:blue}", ".b{margin:0 auto}", "@media (min-width:600px){.c{padding:4px}}")}, "blue"),
    ("a different CSS rule", {"css": (".a{color:red}", ".b{margin:0 auto}", "@media (min-width:600px){.c{padding:4px}}", ".d{top:0}")}, ".d{top:0}"),
    ("a removed CSS rule", {"css": (".a{color:red}", ".b{margin:0 auto}")}, "min-width"),
    ("a different media query", {"css": (".a{color:red}", ".b{margin:0 auto}", "@media (min-width:601px){.c{padding:4px}}")}, "601"),
    ("two CSS rules in the other order", {"css": (".b{margin:0 auto}", ".a{color:red}", "@media (min-width:600px){.c{padding:4px}}")}, "first difference"),
    ("a changed image", {"logo": b"<svg>other logo</svg>"}, "logo.svg: the bytes differ"),
    ("a changed font", {"font": b"\x00other-font"}, "font.woff2: the bytes differ"),
    ("a removed font", {"keep_font": False}, "font.woff2"),
    ("an added asset", {"extra_asset": b"\x89PNG"}, "added: extra.png"),
    ("a changed public file", {"crown": "<svg>another crown</svg>"}, "changed: assets/govuk/crown.svg"),
    ("a public file under another name", {"crown_name": "crest.svg"}, "assets/govuk/crown.svg"),
    ("a rewired chunk", {"lazy_uses_main": False}, "import{*1}"),
    # A reference pointed at another binding of the same chunk: every unit keeps its shape, only the name differs.
    ("a reference rewired to another constant of the chunk", {"show": 4}, "console.warn"),
    ("an import rewired to another export of the chunk it comes from", {"import_name": "u"}, "console.debug"),
]


@pytest.mark.parametrize("name, change, needle", CHANGES, ids=[c[0] for c in CHANGES])
def test_a_planted_change_of_behaviour_is_red(tmp_path: Path, name: str, change: dict[str, object], needle: str) -> None:
    """The planted move **plus** one change. Red here, with the move alone green above, is red for that change."""
    code, output = compare(tmp_path, Build(), Build(**{**MOVE, **change}))
    assert code == 1, f"{name} was not found:\n{output}"
    assert output.startswith("DIFFERENT"), output
    assert needle in output, f"{name}: the report does not show {needle!r}:\n{output}"


@pytest.mark.parametrize("name, change, needle", CHANGES, ids=[c[0] for c in CHANGES])
def test_every_planted_change_alone_makes_the_builds_differ(tmp_path: Path, name: str, change: dict[str, object], needle: str) -> None:
    """The change on its own, with nothing moved, is red too: no change hides inside the move."""
    code, output = compare(tmp_path, Build(), Build(**change))
    # The report, not only the exit code: a script that is missing or crashes also exits 1.
    assert code == 1 and output.startswith("DIFFERENT"), f"{name} was not found:\n{output}"


def test_a_removed_asset_that_a_stylesheet_names_is_red(tmp_path: Path) -> None:
    code, output = compare(tmp_path, Build(), Build(**{**MOVE, "keep_font": False}))
    assert code == 1
    assert "removed: font.woff2" in output


def test_the_report_names_the_changed_file_not_the_files_that_only_name_it(tmp_path: Path) -> None:
    """A changed chunk changes the label of everything that names it; the report leads with the file that changed."""
    code, output = compare(tmp_path, Build(), Build(**{**MOVE, "greeting": "steady"}))
    assert code == 1
    lines = output.splitlines()
    changed = next(i for i, line in enumerate(lines) if line.startswith("changed:") and ".js" in line)
    also = [i for i, line in enumerate(lines) if line.startswith("also differs:")]
    assert all(i > changed for i in also)
    assert "ready" in output and "steady" in output


# ---------------------------------------------------------------------------------------------- real `vite build` output

TOY = {
    "index.html": '<!doctype html>\n<div id="app"></div>\n<script type="module" src="/src/main.js"></script>\n',
    "vite.config.js": "export default { build: { assetsInlineLimit: 0 } };\n",
    "src/style.css": "body{margin:0}\n.panel{color:#333}\n",
    "src/logo.svg": '<svg xmlns="http://www.w3.org/2000/svg"><circle r="4"/></svg>',
}


def relative_import(importer: str, target: str) -> str:
    """The path one source file writes to import another, both given as `src/`-relative names without `.js`."""
    path = os.path.relpath(f"{target}.js", start=os.path.dirname(f"{importer}.js") or ".")
    return path if path.startswith(".") else f"./{path}"


def toy_sources(*, math: str, greet: str, panel: str, order: str = "math-first", many: str = "many", cmp: str = ">", plus: int = 0, colour: str = "#333") -> dict[str, str]:
    """A toy app: two modules, a lazy panel that imports one of them, a stylesheet and an image. The three modules'
    paths are arguments, so the same code can sit at other paths (and, with `order`, be imported in another order)."""
    imports = [
        f'import {{ add }} from "{relative_import("main", math)}";',
        f'import {{ greet }} from "{relative_import("main", greet)}";',
    ]
    if order == "greet-first":
        imports.reverse()
    main = "\n".join(imports) + (
        '\nimport "./style.css";\nimport logo from "./logo.svg";\n'
        'document.body.append(greet("x", add(1, 2)), logo);\n'
        f'document.getElementById("app").onclick = () => import("{relative_import("main", panel)}").then((m) => m.open());\n'
    )
    return {
        "src/main.js": main,
        f"src/{math}.js": f"export const add = (a, b) => a + b + {plus};\n",
        f"src/{greet}.js": f'export function greet(name, count) {{\n  return `hello ${{name}} ${{count {cmp} 2 ? "{many}" : "few"}}`;\n}}\n',
        f"src/{panel}.js": f'import {{ greet }} from "{relative_import(panel, greet)}";\nexport function open() {{\n  console.log(greet("panel", 5));\n}}\n',
        "src/style.css": f"body{{margin:0}}\n.panel{{color:{colour}}}\n",
    }


def vite_build(root: Path, sources: dict[str, str]) -> Path:
    for relative, text in {**TOY, **sources}.items():
        write(root / relative, text)
    done = subprocess.run(
        [node(), str(CORE / "node_modules/vite/bin/vite.js"), "build", str(root), "--logLevel", "error"],
        cwd=CORE,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return root / "dist"


ORIGINAL = dict(math="lib/math", greet="lib/greet", panel="lazy/panel")


def test_the_toy_is_the_shape_vite_build_writes(tmp_path: Path) -> None:
    """Control: the toy really is the shape `vite build` writes (hashed chunks, a lazy chunk naming the main one)."""
    dist = vite_build(tmp_path / "a", toy_sources(**ORIGINAL))
    names = sorted(p.name for p in (dist / "assets").iterdir())
    assert any(n.startswith("index-") and n.endswith(".js") for n in names), names
    assert any(n.startswith("panel-") and n.endswith(".js") for n in names), names
    assert any(n.endswith(".css") for n in names) and any(n.startswith("logo-") for n in names), names


@pytest.mark.parametrize(
    "moved",
    [
        dict(math="shared/arith", greet="shared/hello", panel="deferred/drawer"),
        dict(math="packages/a/arith", greet="packages/b/hello", panel="x/y/z/drawer", order="greet-first"),
    ],
    ids=["moved to other paths and names", "moved and its imports in another order"],
)
def test_a_real_vite_build_moved_to_other_paths_is_green(tmp_path: Path, moved: dict[str, str]) -> None:
    before = vite_build(tmp_path / "a", toy_sources(**ORIGINAL))
    after = vite_build(tmp_path / "b", toy_sources(**moved))
    # Control: the move really did change the file names (a chunk is named after the file it came from) ...
    names_before = {p.name for p in (before / "assets").iterdir()}
    names_after = {p.name for p in (after / "assets").iterdir()}
    assert any(n.startswith("panel-") for n in names_before) and any(n.startswith("drawer-") for n in names_after)
    assert names_before != names_after
    # ... and the script still reads the two as one build.
    code, output = run("compare", before, after)
    assert code == 0, output


@pytest.mark.parametrize(
    "change, needle",
    [
        ({"many": "lots"}, "lots"),
        ({"cmp": ">="}, ">="),
        ({"plus": 1}, "+1"),
        ({"colour": "#334"}, "#334"),
    ],
    ids=["a string", "a condition", "a number", "a CSS value"],
)
def test_a_real_vite_build_with_one_real_change_is_red(tmp_path: Path, change: dict[str, object], needle: str) -> None:
    """Moved to other paths and one real change: red. (Moved alone is green, above.)"""
    before = vite_build(tmp_path / "a", toy_sources(**ORIGINAL))
    after = vite_build(tmp_path / "b", toy_sources(math="shared/arith", greet="shared/hello", panel="deferred/drawer", **change))
    code, output = run("compare", before, after)
    assert code == 1, output
    assert output.startswith("DIFFERENT") and needle in output, output


# ---------------------------------------------------------------------------------------------- the record

# What `npm test --workspace apps/workspace` prints at the end of each of its two vitest runs.
NPM_TEST_OUTPUT = """
 Test Files  405 passed (405)
      Tests  3734 passed (3734)
   Start at  08:53:07
   Duration  91.2s

 Test Files  3 passed (3)
      Tests  3 passed (3)
   Start at  08:54:40
"""


def test_normalise_prints_a_stable_hash_that_ignores_the_move(tmp_path: Path) -> None:
    write_build(tmp_path / "a", Build())
    write_build(tmp_path / "b", Build(**MOVE))
    write_build(tmp_path / "c", Build(**{**MOVE, "greeting": "steady"}))
    hashes = {}
    for name in "abc":
        code, output = run("normalise", tmp_path / name)
        assert code == 0, output
        info = json.loads(output)
        assert re.fullmatch(r"[0-9a-f]{64}", info["normalised_hash"])
        hashes[name] = info["normalised_hash"]
    assert hashes["a"] == hashes["b"] != hashes["c"]
    assert json.loads(run("normalise", tmp_path / "a")[1])["files"]["total"] == len(list((tmp_path / "a").rglob("*"))) - len(
        [p for p in (tmp_path / "a").rglob("*") if p.is_dir()]
    )


def test_record_writes_the_hash_the_file_counts_and_the_test_counts(tmp_path: Path) -> None:
    write_build(tmp_path / "dist", Build())
    write(tmp_path / "tests.txt", NPM_TEST_OUTPUT)
    code, output = run("record", "--dist", tmp_path / "dist", "--tests", tmp_path / "tests.txt", "--out", tmp_path / "record.json")
    assert code == 0, output
    record = json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{64}", record["normalised_hash"])
    assert record["files"]["total"] == 8 and record["files"]["by_kind"]["js"] == 2 and record["files"]["by_kind"]["css"] == 1
    assert record["unit_tests"] == [
        {"run": "main", "files": {"total": 405, "passed": 405, "failed": 0, "skipped": 0}, "tests": {"total": 3734, "passed": 3734, "failed": 0, "skipped": 0}},
        {"run": "budget", "files": {"total": 3, "passed": 3, "failed": 0, "skipped": 0}, "tests": {"total": 3, "passed": 3, "failed": 0, "skipped": 0}},
    ]
    # Budget (performance) figures are measured on the owner's Mac, not here, and are not recorded.
    assert "ms" not in json.dumps(record["unit_tests"]) and "budget_ms" not in record


def test_record_reads_failed_and_skipped_tests(tmp_path: Path) -> None:
    write_build(tmp_path / "dist", Build())
    write(tmp_path / "tests.txt", " Test Files  1 failed | 404 passed | 2 skipped (407)\n      Tests  3 failed | 3730 passed | 5 skipped (3738)\n")
    code, output = run("record", "--dist", tmp_path / "dist", "--tests", tmp_path / "tests.txt", "--out", tmp_path / "record.json")
    assert code == 0, output
    only = json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))["unit_tests"][0]
    assert only["files"] == {"total": 407, "passed": 404, "failed": 1, "skipped": 2}
    assert only["tests"] == {"total": 3738, "passed": 3730, "failed": 3, "skipped": 5}


def test_record_refuses_output_with_no_test_summary(tmp_path: Path) -> None:
    write_build(tmp_path / "dist", Build())
    write(tmp_path / "tests.txt", "everything is fine, trust me\n")
    code, output = run("record", "--dist", tmp_path / "dist", "--tests", tmp_path / "tests.txt", "--out", tmp_path / "record.json")
    assert code != 0 and "no vitest summary" in output
    assert not (tmp_path / "record.json").exists()


def make_record(tmp_path: Path) -> Path:
    write_build(tmp_path / "baseline", Build())
    write(tmp_path / "tests.txt", NPM_TEST_OUTPUT)
    code, output = run("record", "--dist", tmp_path / "baseline", "--tests", tmp_path / "tests.txt", "--out", tmp_path / "record.json")
    assert code == 0, output
    return tmp_path / "record.json"


def test_verify_is_green_on_a_move_and_red_on_a_change(tmp_path: Path) -> None:
    record = make_record(tmp_path)
    write_build(tmp_path / "moved", Build(**MOVE))
    code, output = run("verify", "--dist", tmp_path / "moved", "--record", record)
    assert code == 0 and output.startswith("SAME as the baseline"), output
    write_build(tmp_path / "changed", Build(**{**MOVE, "compare_op": ">="}))
    code, output = run("verify", "--dist", tmp_path / "changed", "--record", record)
    assert code == 1 and output.startswith("DIFFERENT"), output
    assert "compare <raw baseline dist> <this dist>" in output


def test_verify_is_red_when_a_test_fails(tmp_path: Path) -> None:
    record = make_record(tmp_path)
    write_build(tmp_path / "moved", Build(**MOVE))
    write(tmp_path / "now.txt", " Test Files  1 failed | 404 passed (405)\n      Tests  1 failed | 3733 passed (3734)\n")
    code, output = run("verify", "--dist", tmp_path / "moved", "--record", record, "--tests", tmp_path / "now.txt")
    assert code == 1 and "a test fails" in output, output
    write(tmp_path / "now.txt", NPM_TEST_OUTPUT)
    code, output = run("verify", "--dist", tmp_path / "moved", "--record", record, "--tests", tmp_path / "now.txt")
    assert code == 0, output
    assert "main: 3734/3734 tests passed in 405 files (baseline 3734/3734 in 405)" in output


def test_verify_refuses_a_record_made_by_another_normaliser(tmp_path: Path) -> None:
    record = make_record(tmp_path)
    data = json.loads(record.read_text(encoding="utf-8"))
    data["normaliser_version"] = 0
    record.write_text(json.dumps(data), encoding="utf-8")
    write_build(tmp_path / "same", Build())
    code, output = run("verify", "--dist", tmp_path / "same", "--record", record)
    assert code == 1 and "normaliser" in output


def test_a_folder_that_is_not_a_build_is_an_error_not_a_pass(tmp_path: Path) -> None:
    code, output = run("compare", tmp_path / "nowhere", tmp_path / "nowhere-either")
    assert code == 2 and "not a build folder" in output


def test_the_committed_baseline_record_is_complete() -> None:
    """The "before" of every later PL4 slice, written by `record` from the raw copy of the build taken before PL4 moved
    anything, with the unit-test counts of `npm test --workspace apps/workspace` at that moment."""
    assert RECORD.exists(), "apps/workspace/PL4_BASELINE.json is the baseline record: run `dist_compare.mjs record`"
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{64}", record["normalised_hash"])
    assert record["files"]["total"] > 0 and record["files"]["by_kind"]["js"] >= 1 and record["files"]["by_kind"]["css"] >= 1
    runs = {run["run"]: run for run in record["unit_tests"]}
    assert set(runs) == {"main", "budget"}
    for run_ in runs.values():
        assert run_["tests"]["failed"] == 0 and run_["files"]["failed"] == 0
        assert run_["tests"]["passed"] == run_["tests"]["total"] - run_["tests"]["skipped"] > 0
    # Written by the normaliser the script has now: a record made by another version cannot be compared with.
    assert record["normaliser_version"] == NORMALISER_VERSION
    # The Mac's performance budget figures (slice PL4e, 22 November 2026): a record holds them, or says they are not recorded.
    budget = record["budget"]
    assert "not_recorded" not in record
    assert set(budget["unit"]) == {"MatrixView.budget", "settledAnchor.budget", "communityLinks.budget"}
    for name, test in budget["unit"].items():
        assert len(test["runs_ms"]) == 3 and all(ms < test["limit_ms"] for ms in test["runs_ms"] if name != "MatrixView.budget"), name
    assert len(budget["browser"]["perf_first_frame"]["runs_ms"]) == 2 and len(budget["browser"]["perf_sweep"]["runs_ms_per_frame"]) == 2
    assert budget["date"] == "2026-11-22" and "Mac" in budget["machine"]


# ------------------------------------------------------------------------------- the budget figures survive a re-record

BUDGET = {"date": "2026-11-22", "machine": "the owner's Mac", "unit": {"a": {"limit_ms": 1000, "runs_ms": [85, 90, 90]}}}


def record_with_budget(tmp_path: Path) -> Path:
    record = make_record(tmp_path)
    data = json.loads(record.read_text(encoding="utf-8"))
    data.pop("not_recorded", None)
    data["budget"] = BUDGET
    record.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return record


def plant_that_drops_the_budget(tmp_path: Path) -> Path:
    """A copy of the script (in a folder shaped like Core, so it finds node_modules) whose `makeRecord` forgets `budget`:
    the exact line a careless edit would lose, in the shape the real script has."""
    core = tmp_path / "plant-core"
    (core / "scripts").mkdir(parents=True)
    (core / "package.json").write_text("{}", encoding="utf-8")
    (core / "node_modules").symlink_to(CORE / "node_modules")
    source = SCRIPT.read_text(encoding="utf-8")
    line = "    record.budget = budget;\n"
    assert source.count(line) == 1, "the plant must hit the one carry-forward line"
    (core / "scripts" / "dist_compare.mjs").write_text(source.replace(line, "    // dropped\n"), encoding="utf-8")
    return core / "scripts" / "dist_compare.mjs"


def run_script(script: Path, *args: str | Path) -> tuple[int, str]:
    done = subprocess.run([node(), str(script), *map(str, args)], cwd=CORE, capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout + done.stderr


def test_record_carries_an_existing_budget_forward(tmp_path: Path) -> None:
    record = record_with_budget(tmp_path)
    before = json.loads(record.read_text(encoding="utf-8"))
    write_build(tmp_path / "moved", Build(**MOVE))
    code, output = run("record", "--dist", tmp_path / "moved", "--tests", tmp_path / "tests.txt", "--out", record)
    assert code == 0, output
    after = json.loads(record.read_text(encoding="utf-8"))
    assert after["budget"] == BUDGET and "not_recorded" not in after
    # Nothing else in the record changed: the move is the same build, so its hash and counts are the same.
    assert {k: v for k, v in after.items() if k != "budget"} == {k: v for k, v in before.items() if k != "budget"}


def test_a_record_with_no_budget_still_says_it_is_not_recorded(tmp_path: Path) -> None:
    record = make_record(tmp_path)
    data = json.loads(record.read_text(encoding="utf-8"))
    assert "budget" not in data and "performance" in data["not_recorded"].lower()


def test_rebaseline_carries_an_existing_budget_forward(tmp_path: Path) -> None:
    record = record_with_budget(tmp_path)
    write_build(tmp_path / "moved", Build(**MOVE))
    write(tmp_path / "declared.tsv", "# no declared units: a move\n")
    code, output = run(
        "rebaseline", "--declared", tmp_path / "declared.tsv", "--baseline", tmp_path / "baseline", "--dist", tmp_path / "moved",
        "--tests", tmp_path / "tests.txt", "--out", record,
    )
    assert code == 0, output
    after = json.loads(record.read_text(encoding="utf-8"))
    assert after["budget"] == BUDGET and "not_recorded" not in after


@pytest.mark.parametrize("how", ["record", "rebaseline"])
def test_a_script_that_drops_the_budget_is_red(tmp_path: Path, how: str) -> None:
    """Rule 15: the carry-forward line removed from the real script, each way of re-recording: the same tests go red."""
    plant = plant_that_drops_the_budget(tmp_path)
    record = record_with_budget(tmp_path)
    write_build(tmp_path / "moved", Build(**MOVE))
    if how == "record":
        code, output = run_script(plant, "record", "--dist", tmp_path / "moved", "--tests", tmp_path / "tests.txt", "--out", record)
    else:
        write(tmp_path / "declared.tsv", "# no declared units: a move\n")
        code, output = run_script(
            plant, "rebaseline", "--declared", tmp_path / "declared.tsv", "--baseline", tmp_path / "baseline", "--dist", tmp_path / "moved",
            "--tests", tmp_path / "tests.txt", "--out", record,
        )
    assert code == 0, output
    after = json.loads(record.read_text(encoding="utf-8"))
    assert "budget" not in after, "the plant must lose the figures, or the tests above prove nothing"
