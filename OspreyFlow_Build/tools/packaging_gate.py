"""The packaging-time artefact-hygiene assertions `06_DECISIONS.md` names and does not build —
ADR-034 §B7 ("Packaging's own artefact-hygiene properties... Not addable in this session — no
packaging/harness step exists yet to attach either assertion to... Recorded here as required work
owned by Trigger A") and ADR-035 §C2 ("An assertion on the packaging step, failing the build, that
no internal demo's id, directory path or dataset filename appears anywhere in the built artefact —
including inside image layers"). `tools/osprey_bundle.py`'s own extended `main()` is that step;
these are its assertions, kept separate so each is independently unit-testable against a fabricated
artefact (`tests/licence_check/test_gpl_rejection.py`'s own "prove the gate with a fixture that
intentionally violates it" pattern, reused rather than a mocked return value) without needing a
real `docker build`/`tar` for every case.

**Three checks, three different questions, deliberately not merged into one:**

1. `find_private_tree_files` — B7 #1: does a path *originating in the private build tree* appear
   in the artefact. Reuses `product_tree_link_check.py`'s own `PRIVATE_TREE_MARKERS` — the same
   canonical list, not a second, divergent one — matched as a substring of each artefact path, the
   same imprecise-on-purpose matching that gate already accepts for the same reason (these names
   are cited inconsistently; a bare-name check is what actually catches every real case checked
   while `product_tree_link_check.py` was built).
2. `find_authorship_identifiers` — B7 #2: does an identifier from ADR-034 §B5's own verified set
   (`git grep -liE "ayan\\.?kar|ayankarsolirius|solirius"`, reused as the identical pattern rather
   than re-derived) appear in any artefact text, including build metadata and image labels — not
   only file paths, since a version string built from a git author field is exactly the shape §B7
   #2 names.
3. `find_internal_demo_data` — ADR-035 §C2: does any `internal`-classified demo's own path
   (`scripts/demo_registry.py`), or either of the two fixed internal-only locations
   (`config/real_data_exceptions.yaml`, `demo-data/`) — real even though no registry entry
   currently points there, since both are named directly by ADR-035 §C1/§C2 regardless of what is
   currently registered — appear in the artefact.

**Reading a real artefact's own file list, including inside image layers.** `tarball_members` reads
a `.tar`/`.tar.gz` bundle's own member names. `docker_save_layer_paths` reads every file path that
was ever written to *any* layer of an image `docker save` produced — not merely the final,
squashed filesystem view, because a file deleted in a later layer is still "invisible at runtime,
fully recoverable from the tarball" (ADR-034 §B7's own words), and a check against only the final
view would miss exactly that case.
"""

from __future__ import annotations

import json
import re
import tarfile
from collections.abc import Iterable
from pathlib import Path

from scripts.demo_registry import REGISTRY, DemoManifest, internal_manifests

from tools.layout import REPO as REPO_ROOT
from tools.product_tree_link_check import PRIVATE_TREE_MARKERS

#: `06_DECISIONS.md` ADR-034 §B2/§B6's addendum: "the third `licence-check` leg... Apache 2.0 text
#: byte-identical; NOTICE naming 'The OspreyFlow Authors'". The reference copy lives in `tests/
#: fixtures/` rather than being re-typed inline here, so both the repository's own root `LICENSE`
#: and any bundle's copy of it are compared against the one stored text, not against each other —
#: a drift in either shows up as a real diff rather than the two files silently agreeing by both
#: having changed the same way.
#:
#: **On "byte-identical," stated honestly rather than merely asserted.** This reference was
#: transcribed from the canonical `https://www.apache.org/licenses/LICENSE-2.0.txt` and
#: cross-checked, paragraph for paragraph, against a live fetch of that same URL during this
#: session — but the fetch itself passed through a summarising model and reformatted (added bold
#: markers, rewrapped lines), so it could confirm wording and paragraph order, not serve as a
#: byte-for-byte diff target. Treat this as a careful transcription verified for *content*, not a
#: tool-verified byte-for-byte copy of the upstream file — worth one authoritative diff before
#: Trigger B, named here rather than left implicit.
APACHE_2_0_LICENSE_REFERENCE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "apache-2.0-license-2004.txt"
)

#: ADR-034 §B6.
NOTICE_HOLDER_TEXT = "The OspreyFlow Authors"

#: ADR-035 §C1/§C2's own two fixed internal-only locations — real regardless of what the registry
#: currently enumerates, since real datasets admitted through either never belong in any artefact.
_ALWAYS_INTERNAL_MARKERS: tuple[str, ...] = (
    "config/real_data_exceptions.yaml",
    "demo-data/",
    "OspreyFlow_Data/",
)

#: ADR-034 §B5's own verified pattern, reused rather than re-derived: `git grep -liE
#: "ayan\.?kar|ayankarsolirius|solirius"` matched exactly one tracked file at the time B5 was
#: written. The third identity ("OspreyFlow" / the GitHub noreply address) is already neutral and
#: is not a search pattern, per B5's own text.
AUTHORSHIP_PATTERN = re.compile(r"ayan\.?kar|ayankarsolirius|solirius", re.IGNORECASE)


def find_private_tree_files(artefact_paths: Iterable[str]) -> list[str]:
    """ADR-034 §B7 #1. Returns every artefact path containing a private-tree marker."""
    violations = []
    for path in artefact_paths:
        for marker in PRIVATE_TREE_MARKERS:
            if marker in path:
                violations.append(path)
                break
    return violations


def find_authorship_identifiers(text_blobs: dict[str, str]) -> list[str]:
    """ADR-034 §B7 #2. `text_blobs` maps a label (a file path, or a metadata field name such as
    `"image.label:org.opencontainers.image.authors"`) to the text to scan. Returns `"label:
    matched-text"` for every hit."""
    violations = []
    for label, text in text_blobs.items():
        match = AUTHORSHIP_PATTERN.search(text)
        if match:
            violations.append(f"{label}: {match.group(0)!r}")
    return violations


def find_internal_demo_data(
    artefact_paths: Iterable[str], registry: tuple[DemoManifest, ...] = REGISTRY
) -> list[str]:
    """ADR-035 §C2, extended by ADR-114 Amendment 1 decision 1. Returns every artefact path that
    must never appear in a shipped artefact: either of the two fixed internal-only locations, a
    path belonging to an `internal` registry entry, or a path belonging to any manifest that is not
    seeded (`not is_seeded`, strict and fail-closed), whatever its `distribution`. A downloadable
    pack such as PaySim is `shipped` yet its data must still never be bundled."""
    internal_paths = {p for manifest in internal_manifests(registry) for p in manifest.paths} | {
        p for manifest in registry if not manifest.is_seeded for p in manifest.paths
    }
    violations = []
    for path in artefact_paths:
        normalised = path.lstrip("./")
        if any(marker in normalised for marker in _ALWAYS_INTERNAL_MARKERS):
            violations.append(path)
            continue
        if any(normalised == p or normalised.startswith(p) for p in internal_paths):
            violations.append(path)
    return violations


def check_license_and_notice(
    license_text: str | None,
    notice_text: str | None,
    *,
    reference_path: Path = APACHE_2_0_LICENSE_REFERENCE_PATH,
) -> list[str]:
    """ADR-034 §B2/§B6's addendum, item 2f of the packaging brief: "LICENSE and NOTICE present in
    the product subtree and the tarball... Absent → red." Returns a violation string for each
    problem; empty means both files are present and correct."""
    violations = []
    if license_text is None:
        violations.append("LICENSE is missing")
    elif license_text != reference_path.read_text(encoding="utf-8"):
        violations.append("LICENSE does not match the reference Apache-2.0 text")
    if notice_text is None:
        violations.append("NOTICE is missing")
    elif NOTICE_HOLDER_TEXT not in notice_text:
        violations.append(f"NOTICE does not name {NOTICE_HOLDER_TEXT!r}")
    return violations


def tarball_members(tar_path: Path) -> list[str]:
    """Every member name in a `.tar`/`.tar.gz` artefact — the bundle's own file list, read the
    same way a recipient inspecting the artefact would (`tar tf`), not assumed from what the
    packaging step believes it wrote."""
    with tarfile.open(tar_path) as tar:
        return list(tar.getnames())


def docker_save_layer_paths(save_tar_path: Path) -> set[str]:
    """Every file path in every layer of an image archived by `docker save -o save_tar_path
    <image>` — the union across layers, not only the final filesystem view (see this module's own
    docstring for why the union is the correct, conservative reading of ADR-034 §B7 #1)."""
    paths: set[str] = set()
    with tarfile.open(save_tar_path) as outer:
        manifest_member = outer.getmember("manifest.json")
        manifest_file = outer.extractfile(manifest_member)
        if manifest_file is None:
            return paths
        manifest = json.loads(manifest_file.read().decode("utf-8"))
        layer_tar_names = {layer for entry in manifest for layer in entry.get("Layers", [])}
        for layer_name in layer_tar_names:
            layer_member = outer.getmember(layer_name)
            layer_file = outer.extractfile(layer_member)
            if layer_file is None:
                continue
            with tarfile.open(fileobj=layer_file) as layer_tar:
                paths.update(layer_tar.getnames())
    return paths


def check_artefact(
    artefact_paths: Iterable[str],
    *,
    text_blobs: dict[str, str] | None = None,
    registry: tuple[DemoManifest, ...] = REGISTRY,
) -> dict[str, list[str]]:
    """Runs every check above against one artefact's own path list (and, optionally, metadata text
    to scan for authorship identifiers) and returns `{check_name: [violations]}` for only the
    checks that found something — empty dict means clean."""
    paths = list(artefact_paths)
    findings: dict[str, list[str]] = {}
    private_tree = find_private_tree_files(paths)
    if private_tree:
        findings["private_tree_files"] = private_tree
    internal_demo = find_internal_demo_data(paths, registry)
    if internal_demo:
        findings["internal_demo_data"] = internal_demo
    if text_blobs:
        authorship = find_authorship_identifiers(text_blobs)
        if authorship:
            findings["authorship_identifiers"] = authorship
    return findings
