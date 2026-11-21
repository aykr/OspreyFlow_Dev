"""The licence register for what the code gate does not see: model weights, map data, font files and
base images (PL11; the owner's rulings of 21 November 2026).

`tools/licence_check.py` reads the licences packages declare. A model weight, a map dataset, a font
file and an image's contents are not packages, so nothing read them. `spec/LICENCE_REGISTER.yaml`
has a row for each the code names, and this module **re-derives that list from the code** and
holds the two to each other. It is the register's companion: its logic, and `HELD_FOR_OWNER`.

**The definition a row is judged by** (the owner, 21 November 2026; `spec/00_ARCHITECTURE.md` §7's
stricter allowlist stays as it is, for code): software and base images are open source when their
licence is approved by the Open Source Initiative (which includes GPL-2.0 with the Classpath
exception); model weights, by the same test on the weights' own licence; data, by a recognised
open-data licence, which covers ODbL and OGL. Each row says which of the four tests it passed:
`osi-software`, `osi-weights`, `open-data` or `restricted` (the name of failing: nothing passes it).

**What the gate fails on** (`find_register_violations`; each is shown red in
`tests/licence_check/test_register.py`, planted at the shape the code reads): a weight, map dataset,
font family or image the code names that has no row; a pin (revision, digest, tag or hash) that
differs between the code and the row; a row nothing in the code names; a licence that does not pass
the row's stated test, or a test that is not one of the four; a `confirmed` row with no "where
read";
a `conditional` row with no owner ruling; a `restricted` row that is not conditional; an
`unconfirmed` row that states a licence or does not say what must be read; a name that is both held
for the owner and registered.

**What it does not fail on, and the release refuses** (`release_refusal`): an `unconfirmed` row, and
a name in `HELD_FOR_OWNER`. The gate allows them so that `make ci` stays green while the owner
decides; a release is refused while any is left, as it is while a live test is owed.

**What it reads** (`read_sources`): the Dockerfiles (`FROM`), `harness/*.py` (the `ServiceImage`
list and every `*_IMAGE` constant), the Ollama pull script in `harness/render.py`, the closed model
lists in `packages/schemas/deployment.py`, the recogniser adapters' default models, the Stanza
models' pin file, `packages/design/fonts.json`, the basemap build's regions and pinned planetiler,
`osprey.yaml`'s map providers and `providers/*.yaml`. **Not read**, said here so it is not mistaken
for covered: `deploy/compose/dev.yaml` (the developer stack), the Helm chart's values (it names no
third-party image of its own), and anything the code fetches under a name that exists only at run
time inside a third-party tool (planetiler's list lives in its jar: the register records it, and
`tests/licence_check/test_register_pins.py` holds the record to the register, not to the jar).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tools.layout import BUILD, CORE

REGISTER_PATH = BUILD / "spec" / "LICENCE_REGISTER.yaml"

#: The four tests a row can have passed (the owner's ruling 1, 21 November 2026).
TESTS = ("osi-software", "osi-weights", "open-data", "restricted")
STATUSES = ("confirmed", "unconfirmed", "conditional")
KINDS = ("weight", "map-data", "font", "image")
#: Columns every row carries (an `unconfirmed` row carries `licence` and `where_read` as null).
#: Optional: `note`, `owner_ruling`, `must_read`, `os_packages` (required of an image).
COLUMNS = (
    "id",
    "kind",
    "name",
    "pin",
    "ships",
    "named_in",
    "licence",
    "where_read",
    "test",
    "status",
)
OS_SCANS = ("yes", "no", "partly")

#: Names the register could not take because the licence read does not pass the definition, put to
#: the owner (the conductor takes each to him). A held name is **not** a row: the gate does not fail
#: on the code naming it, and the release check refuses while any is here. When the owner rules, the
#: name leaves this set and becomes a row (a name in both is a violation).
#:
#: `ghcr.io/berriai/litellm`: the image the renderer pins (`harness/render.py`, by digest) carries
#: `/app/enterprise` under the BerriAI Enterprise licence, which is proprietary (21 November 2026;
#: the licence text and where it was read are in PL11's report to the owner).
HELD_FOR_OWNER: frozenset[str] = frozenset({"ghcr.io/berriai/litellm"})

#: Licences the Open Source Initiative approves, by SPDX identifier in lower case
#: (opensource.org/licenses, as read for the owner's definition). A `WITH` exception is one term:
#: `gpl-2.0-only with classpath-exception-2.0` is listed whole because the owner named it.
#: Extended only by editing this set, with the OSI page that approves the licence.
OSI_APPROVED = frozenset(
    {
        "0bsd", "afl-3.0", "agpl-3.0-only", "agpl-3.0-or-later", "apache-2.0", "artistic-2.0",
        "bsd-2-clause", "bsd-3-clause", "bsl-1.0", "cddl-1.0", "cnri-python", "epl-1.0", "epl-2.0",
        "eupl-1.2", "gpl-2.0-only", "gpl-2.0-or-later", "gpl-3.0-only", "gpl-3.0-or-later", "isc",
        "lgpl-2.1-only", "lgpl-2.1-or-later", "lgpl-3.0-only", "lgpl-3.0-or-later", "mit",
        "mit-0", "mpl-2.0", "ncsa", "ofl-1.1", "postgresql", "psf-2.0", "python-2.0", "unlicense",
        "zlib",
        "gpl-2.0-only with classpath-exception-2.0",
        "gpl-2.0-with-classpath-exception",
    }
)  # fmt: skip

#: Recognised open-data licences (the owner: "which covers ODbL and OGL"), by identifier in lower
#: case. `public-domain` is a dedication, not a licence, and is named only for a source that says so
#: in its own terms (Natural Earth; a US federal work).
OPEN_DATA = frozenset(
    {
        "odbl-1.0", "ogl-uk-3.0", "cc0-1.0", "cc-by-3.0", "cc-by-4.0", "cc-by-sa-4.0", "odc-by-1.0",
        "pddl-1.0", "public-domain",
    }
)  # fmt: skip


@dataclass(frozen=True)
class Named:
    """One thing the code names: its kind, its name as the code writes it, its pin, and where."""

    kind: str
    name: str
    pin: str
    files: tuple[str, ...]


# --- the licence test ---------------------------------------------------------------------------


def _expression(text: str, term_ok: Any) -> bool:
    """`text` as an SPDX-style expression: OR needs one passing term, AND every one."""
    parts = [p.strip() for p in re.split(r"(\(|\)|\s+and\s+|\s+or\s+)", text.lower()) if p.strip()]
    parts = [p if p in ("(", ")") else p.strip() for p in parts]
    position = 0

    def peek() -> str | None:
        return parts[position] if position < len(parts) else None

    def take() -> str:
        nonlocal position
        position += 1
        return parts[position - 1]

    def either() -> bool:
        result = both()
        while peek() == "or":
            take()
            result = both() or result
        return result

    def both() -> bool:
        result = atom()
        while peek() == "and":
            take()
            result = atom() and result
        return result

    def atom() -> bool:
        token = peek()
        if token is None or token in ("and", "or", ")"):
            raise ValueError("expected a licence")
        take()
        if token == "(":
            result = either()
            if peek() != ")":
                raise ValueError("unbalanced parenthesis")
            take()
            return result
        return bool(term_ok(" ".join(token.split())))

    try:
        result = either()
    except ValueError:
        return False
    return result and position == len(parts)


def licence_passes(licence: str | None, test: str) -> bool:
    """Does `licence` pass `test`? `restricted` is the name of failing, so nothing passes it; a test
    that is not one of the four passes nothing."""
    if not licence or not licence.strip():
        return False
    if test in ("osi-software", "osi-weights"):
        return _expression(licence, lambda term: term in OSI_APPROVED)
    if test == "open-data":
        return _expression(licence, lambda term: term in OPEN_DATA)
    return False


# --- what the code names ------------------------------------------------------------------------

#: Named files, relative to the product folder. A missing one is an error, never an empty answer.
NAMED_FILES = (
    "osprey.yaml",
    "packages/schemas/deployment.py",
    "packages/design/fonts.json",
    "apps/workspace/package.json",
    "scripts/build_local_basemap.py",
    "scripts/fetch_basemap_glyphs.py",
    "services/ner/models.sha256",
    "services/laurium/requirements.txt",
    "packages/adapters/recognise_spacy/adapter.py",
    "packages/adapters/recognise_transformers/adapter.py",
)


def read_sources(core: Path = CORE) -> dict[str, str]:
    """The text of every file the derivation reads, by its path relative to `core`."""
    found: dict[str, str] = {}
    for name in NAMED_FILES:
        found[name] = (core / name).read_text(encoding="utf-8")
    for pattern in ("harness/*.py", "providers/*.yaml"):
        for path in sorted(core.glob(pattern)):
            found[path.relative_to(core).as_posix()] = path.read_text(encoding="utf-8")
    for path in sorted(core.rglob("Dockerfile*")):
        if {"node_modules", ".venv"} & set(path.parts):
            continue
        found[path.relative_to(core).as_posix()] = path.read_text(encoding="utf-8")
    return found


def split_image(reference: str) -> tuple[str, str]:
    """`(name, pin)`: the pin is whatever follows the name, tag and digest together
    (`3.13-slim@sha256:…`, `sha256:…`, `8.0`); `latest` when there is none."""
    head, _, tail = reference.rpartition("/")
    match = re.match(r"^([^:@]+)(?:[:@](.*))?$", tail)
    if not match:
        return reference, "latest"
    name = f"{head}/{match.group(1)}" if head else match.group(1)
    return name, match.group(2) or "latest"


def _dockerfile_images(text: str) -> list[str]:
    """Each image a Dockerfile's `FROM` lines name: not an earlier stage, not `scratch`, not an
    argument the build fills in."""
    joined = re.sub(r"\\\r?\n", " ", text)
    stages: set[str] = set()
    images: list[str] = []
    for line in joined.splitlines():
        line = line.strip()
        match = re.match(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", line, re.I)
        if not match:
            continue
        reference, alias = match.group(1), match.group(2)
        if alias:
            stages.add(alias.lower())
        if reference.lower() in stages or reference.lower() == "scratch" or "$" in reference:
            continue
        images.append(reference)
    return images


def _module_constants(tree: ast.AST) -> dict[str, ast.expr]:
    found: dict[str, ast.expr] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name):
            found[target.id] = value
    return found


def _string(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _harness_images(sources: dict[str, str]) -> list[tuple[str, str]]:
    """`(reference, file)` for each `ServiceImage(service, "<literal>")` and each module-level
    `*_IMAGE = "<literal>"` in `harness/*.py`. An owned image (an f-string) and a parameter are not
    a third-party reference and are left out."""
    constants: dict[str, str] = {}
    trees: dict[str, ast.AST] = {}
    for path, text in sources.items():
        if path.startswith("harness/") and path.endswith(".py"):
            trees[path] = ast.parse(text)
            for name, value in _module_constants(trees[path]).items():
                literal = _string(value)
                if literal is not None:
                    constants[name] = literal
    found: list[tuple[str, str]] = []
    for path, tree in trees.items():
        for name, value in _module_constants(tree).items():
            literal = _string(value)
            if name.endswith("_IMAGE") and literal is not None:
                found.append((literal, path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ServiceImage"
                and len(node.args) >= 2
            ):
                arg = node.args[1]
                literal = _string(arg)
                if literal is None and isinstance(arg, ast.Name):
                    literal = constants.get(arg.id)
                if literal is not None:
                    found.append((literal, path))
    return found


def _dict_of_strings(tree: ast.AST, name: str) -> dict[str, str]:
    node = _module_constants(tree).get(name)
    if isinstance(node, ast.Dict):
        return {
            k: v
            for k, v in (
                (_string(a), _string(b)) for a, b in zip(node.keys, node.values, strict=True)
            )
            if k is not None and v is not None
        }
    return {}


def _strings_of(tree: ast.AST, name: str) -> list[str]:
    node = _module_constants(tree).get(name)
    if isinstance(node, ast.Tuple | ast.List):
        return [s for s in (_string(e) for e in node.elts) if s is not None]
    return []


def _weights(sources: dict[str, str]) -> list[tuple[str, str, str]]:
    """`(name, pin, file)` for each model weight."""
    found: list[tuple[str, str, str]] = []
    render = sources["harness/render.py"]
    for model, manifest in re.findall(
        r"pull_and_verify ([A-Za-z0-9_.:/-]+) ([0-9a-f]{12})\b", render
    ):
        found.append((model, manifest, "harness/render.py"))
    deployment = "packages/schemas/deployment.py"
    tree = ast.parse(sources[deployment])
    for table in ("EXTRACTION_MODELS", "VISION_MODELS", "EMBEDDING_MODELS"):
        found += [(m, i, deployment) for m, i in _dict_of_strings(tree, table).items()]
    revisions = _dict_of_strings(tree, "TRANSCRIPTION_MODEL_REVISIONS")
    for model in _strings_of(tree, "TRANSCRIPTION_MODELS"):
        found.append((model, revisions.get(model, "none"), deployment))
    # Stanza: the language the image's build downloads, pinned by the hash file it checks against.
    ner = sources["services/ner/Dockerfile"]
    for language in re.findall(r"stanza\.download\(\s*'(\w+)'", ner):
        digest = hashlib.sha256(sources["services/ner/models.sha256"].encode()).hexdigest()
        found.append((f"stanza:{language}", f"sha256:{digest}", "services/ner/Dockerfile"))
    # spaCy: the default pipeline, pinned by the hash Laurium's requirements install it under.
    spacy = sources["packages/adapters/recognise_spacy/adapter.py"]
    named = re.search(r'pipeline_name: str = "([^"]+)"', spacy)
    if named:
        wheel = re.search(
            re.escape(named.group(1).replace("_", "-"))
            + r" @ \S+ \\\s*--hash=sha256:([0-9a-f]{64})",
            sources["services/laurium/requirements.txt"],
        )
        pin = f"sha256:{wheel.group(1)}" if wheel else "none"
        found.append((named.group(1), pin, "packages/adapters/recognise_spacy/adapter.py"))
    # The transformers recogniser's default model: pinned by the revision it loads.
    adapter = "packages/adapters/recognise_transformers/adapter.py"
    transformers = sources[adapter]
    named = re.search(r'model_name: str = "([^"]+)"', transformers)
    if named:
        revision = re.search(re.escape(f'"{named.group(1)}": ') + r'"([0-9a-f]{40})"', transformers)
        found.append((named.group(1), revision.group(1) if revision else "none", adapter))
    return found


def _fonts(sources: dict[str, str]) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    package = json.loads(sources["apps/workspace/package.json"])
    versions = {**package.get("devDependencies", {}), **package.get("dependencies", {})}
    for font in json.loads(sources["packages/design/fonts.json"])["fonts"]:
        source = font["source"]
        found.append(
            (
                font["family"],
                f"{source} {versions.get(source, 'unpinned')}",
                "packages/design/fonts.json",
            )
        )
    # The basemap's label glyphs, fetched by an operator, pinned by release and SHA-256.
    glyphs = sources["scripts/fetch_basemap_glyphs.py"]
    tree = ast.parse(glyphs)
    constants = _module_constants(tree)
    url = _string(constants.get("RELEASE_URL")) or ""
    release = re.search(r"/download/([^/]+)/", url)
    sha = _string(constants.get("RELEASE_SHA256")) or "none"
    for family in _strings_of(tree, "STYLE_FONTS"):
        found.append(
            (
                family,
                f"{release.group(1) if release else 'unpinned'} sha256:{sha}",
                "scripts/fetch_basemap_glyphs.py",
            )
        )
    return found


def _maps(sources: dict[str, str]) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []

    def declared(document: Any) -> str:
        licence = (document or {}).get("licence") or {}
        return str(licence.get("id")) if isinstance(licence, dict) else str(licence)

    document = yaml.safe_load(sources["osprey.yaml"]) or {}
    for provider in (document.get("map") or {}).get("providers") or []:
        found.append((str(provider["id"]), declared(provider), "osprey.yaml"))
    for path, text in sources.items():
        if path.startswith("providers/") and path.endswith(".yaml"):
            found.append((Path(path).stem, declared(yaml.safe_load(text)), path))
    basemap = "scripts/build_local_basemap.py"
    tree = ast.parse(sources[basemap])
    for region, url in _dict_of_strings(tree, "GEOFABRIK_REGIONS").items():
        found.append((f"osm-local-{region}", url, basemap))
    constants = _module_constants(tree)
    if "PLANETILER_PIN" in constants:
        pinned = ast.literal_eval(constants["PLANETILER_PIN"])
        found.append(("planetiler", f"{pinned['version']} sha256:{pinned['sha256']}", basemap))
    if "PLANETILER_SOURCES" in constants:
        for key, entry in ast.literal_eval(constants["PLANETILER_SOURCES"]).items():
            found.append((f"planetiler:{key}", f"sha256:{entry['sha256']}", basemap))
    return found


def named_by_code(sources: dict[str, str]) -> list[Named]:
    """Everything the code names: one entry per `(kind, name, pin)`, with the files naming it."""
    seen: dict[tuple[str, str, str], list[str]] = {}

    def add(kind: str, name: str, pin: str, path: str) -> None:
        files = seen.setdefault((kind, name, pin), [])
        if path not in files:
            files.append(path)

    for path, text in sources.items():
        if Path(path).name.startswith("Dockerfile"):
            for reference in _dockerfile_images(text):
                name, pin = split_image(reference)
                add("image", name, pin, path)
    for reference, path in _harness_images(sources):
        name, pin = split_image(reference)
        add("image", name, pin, path)
    for name, pin, path in _weights(sources):
        add("weight", name, pin, path)
    for name, pin, path in _fonts(sources):
        add("font", name, pin, path)
    for name, pin, path in _maps(sources):
        add("map-data", name, pin, path)
    return [Named(k, n, p, tuple(f)) for (k, n, p), f in sorted(seen.items())]


# --- the register -------------------------------------------------------------------------------


def load_register(path: Path = REGISTER_PATH) -> list[dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(document["rows"])


def _row_violations(row: dict[str, Any], core: Path) -> list[str]:
    label = f"{row.get('id', '?')} {row.get('name', '?')!r}"
    out: list[str] = []
    test, status = row.get("test"), row.get("status")
    if test not in TESTS:
        out.append(f"{label}: the test {test!r} is not one of {', '.join(TESTS)}")
    if status not in STATUSES:
        out.append(f"{label}: the status {status!r} is not one of {', '.join(STATUSES)}")
    if row.get("kind") not in KINDS:
        out.append(f"{label}: the kind {row.get('kind')!r} is not one of {', '.join(KINDS)}")
    for column in COLUMNS:
        if column not in row:
            out.append(f"{label}: no {column} column")
    licence = row.get("licence")
    if status == "unconfirmed":
        if licence:
            out.append(f"{label}: unconfirmed, so no licence may be written (read it first)")
        if not str(row.get("must_read") or "").strip():
            out.append(f"{label}: unconfirmed, and must_read does not say what to read and where")
    elif status in ("confirmed", "conditional"):
        if status == "confirmed":
            if not str(row.get("where_read") or "").strip():
                out.append(f"{label}: confirmed, but says nothing of where it was read")
            if test == "restricted":
                out.append(
                    f"{label}: fails the definition (test restricted) and is not conditional with "
                    "an owner ruling"
                )
            elif test in TESTS and not licence_passes(licence, test):
                out.append(f"{label}: the licence {licence!r} does not pass the test {test}")
        else:
            if not str(row.get("owner_ruling") or "").strip():
                out.append(f"{label}: conditional, but cites no owner ruling")
            if not str(row.get("where_read") or "").strip():
                out.append(f"{label}: conditional, but says nothing of where it was read")
            if test in ("osi-software", "osi-weights", "open-data") and not licence_passes(
                licence, test
            ):
                out.append(f"{label}: the licence {licence!r} does not pass the test {test}")
    if row.get("kind") == "image":
        packages = row.get("os_packages")
        if not isinstance(packages, dict) or packages.get("scan") not in OS_SCANS:
            out.append(
                f"{label}: an image row needs os_packages with scan one of {', '.join(OS_SCANS)}"
            )
        elif not str(packages.get("covered_by") or "").strip():
            out.append(
                f"{label}: os_packages does not say how the operating-system packages are covered"
            )
    for named_in in row.get("named_in") or []:
        if not (core / named_in).exists():
            out.append(f"{label}: named_in {named_in!r} is not a file")
    return out


def find_register_violations(
    rows: list[dict[str, Any]],
    named: list[Named],
    held: frozenset[str] = HELD_FOR_OWNER,
    core: Path = CORE,
) -> list[str]:
    """Every way the register and the code part; empty when they agree."""
    out: list[str] = []
    ids = [r.get("id") for r in rows]
    out += [f"the row id {i!r} is used twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for row in rows:
        out += _row_violations(row, core)

    by_code: dict[tuple[str, str], list[Named]] = {}
    for item in named:
        by_code.setdefault((item.kind, item.name), []).append(item)
    by_register: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_register.setdefault((row.get("kind", "?"), row.get("name", "?")), []).append(row)

    for (kind, name), items in sorted(by_code.items()):
        listed = by_register.get((kind, name), [])
        if not listed:
            if name not in held:
                files = ", ".join(sorted({f for i in items for f in i.files}))
                out.append(f"{kind} {name!r} (named in {files}) is not in the register")
            continue
        code_pins = sorted({i.pin for i in items})
        register_pins = sorted({str(r.get("pin")) for r in listed})
        loose_code = [p for p in code_pins if p not in register_pins]
        loose_register = [p for p in register_pins if p not in code_pins]
        for code_pin, register_pin in zip(loose_code, loose_register, strict=False):
            out.append(
                f"{kind} {name!r}: pin differs — the code pins {code_pin!r}, "
                f"the register {register_pin!r}"
            )
        for code_pin in loose_code[len(loose_register) :]:
            # The code names this one thing at two places (the pull script and a closed list) and
            # they disagree, so the register's pin is still named and nothing pairs with this one.
            out.append(
                f"{kind} {name!r}: pin differs — the code pins {code_pin!r}, which is not in the "
                f"register (it holds {', '.join(repr(p) for p in register_pins)})"
            )
        for register_pin in loose_register[len(loose_code) :]:
            out.append(f"{kind} {name!r}: the register's pin {register_pin!r} is one no code names")

    for (kind, name), listed in sorted(by_register.items()):
        if (kind, name) not in by_code:
            out.append(
                f"the register row {listed[0].get('id')} {name!r} ({kind}) names something "
                "no code names"
            )

    registered = {r.get("name") for r in rows}
    for name in sorted(held & registered):
        out.append(
            f"{name!r} is held for the owner and registered: a held name is not a row until "
            "he rules, and then it leaves HELD_FOR_OWNER"
        )
    return out


def release_refusal(
    rows: list[dict[str, Any]] | None = None, held: frozenset[str] = HELD_FOR_OWNER
) -> str | None:
    """Why a release must wait for the register, in words that name each row and each held name, or
    None when nothing is unconfirmed or held (the way a release waits for an owed live test)."""
    rows = load_register() if rows is None else rows
    lines: list[str] = []
    for row in rows:
        if row.get("status") == "unconfirmed":
            lines.append(
                f"  unconfirmed: {row.get('id')} {row.get('name')!r} — read: {row.get('must_read')}"
            )
    for name in sorted(held):
        lines.append(f"  held for the owner: {name!r} — its licence does not pass the definition")
    if not lines:
        return None
    return "the licence register (spec/LICENCE_REGISTER.yaml) is not settled:\n" + "\n".join(lines)
