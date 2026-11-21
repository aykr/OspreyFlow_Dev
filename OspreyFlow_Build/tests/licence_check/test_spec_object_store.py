"""No table in the specification names an object store other than the one the install renders (PL11
item 7).

`04_VAULT_BACKEND.md` §5's supporting-services table listed MinIO (AGPL-3.0) as the object store,
with a paragraph on its AGPL beneath it; `00_ARCHITECTURE.md`'s diagram and its
rejected-alternatives table, and `05_DEPLOYMENT.md`'s account of what is running, named it too. The
install has run SeaweedFS (Apache-2.0) since ADR-114 Amendment 9, when MinIO's public images were
withdrawn, so each stated a fact that was no longer true, and a licence that is not the one shipped.

What this reads, so that the test does not name an answer of its own: the object store the renderer
puts in the compose file (the image of the `objectstore` service in `harness/render.py`), and from
it the name the specification should use. The specification's own history (`06_DECISIONS.md`, whose
entries record what was decided on the day) is not a table of what ships and is not read; its
Amendment 9 is what says why MinIO went.

**The folders this test walks:** `OspreyFlow_Build/spec/`, every `*.md` (one `rglob`), except
`06_DECISIONS.md`; and `OspreyFlow_Core/harness/render.py` by name.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.layout import CORE, REPO

#: Self-hosted object stores a table in the specification must not name, unless it is the one
#: rendered.
OBJECT_STORES = {
    "minio": "MinIO",
    "ceph": "Ceph",
    "garage": "Garage",
    "rustfs": "RustFS",
    "seaweedfs": "SeaweedFS",
}
HISTORY = {"06_DECISIONS.md"}


def rendered_object_store() -> str:
    """The name of the object store `harness/render.py` renders, from its `objectstore`
    ServiceImage."""
    tree = ast.parse((CORE / "harness/render.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "ServiceImage"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "objectstore"
            and isinstance(node.args[1], ast.Constant)
        ):
            image = str(node.args[1].value)
            for key, name in OBJECT_STORES.items():
                if key in image.lower():
                    return name
            raise AssertionError(f"the rendered object store {image!r} is not one this test knows")
    raise AssertionError("harness/render.py renders no `objectstore` service")


def _lines_naming_a_store(text: str) -> list[tuple[int, str]]:
    """Table rows, and the diagram's `Object store:` label: the two shapes a store is named in as a
    fact about what runs."""
    return [
        (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if line.lstrip().startswith("|") or "Object store:" in line
    ]


def find_other_object_stores(spec_root: Path, rendered: str) -> list[str]:
    found: list[str] = []
    for path in sorted(spec_root.rglob("*.md")):
        if path.name in HISTORY:
            continue
        for number, line in _lines_naming_a_store(path.read_text(encoding="utf-8")):
            for name in OBJECT_STORES.values():
                if name != rendered and re.search(rf"\b{name}\b", line, re.I):
                    found.append(
                        f"{path.relative_to(spec_root)}:{number} names {name}, not {rendered}"
                    )
    return found


def test_the_rendered_object_store_is_the_one_the_decision_log_says() -> None:
    assert rendered_object_store() == "SeaweedFS"


def test_no_table_in_the_specification_names_another_object_store() -> None:
    assert find_other_object_stores(REPO / "spec", rendered_object_store()) == []


def test_the_supporting_services_table_names_the_rendered_one_with_its_licence() -> None:
    text = (REPO / "spec" / "04_VAULT_BACKEND.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| Object store |"))
    assert rendered_object_store() in row and "Apache-2.0" in row and "AGPL" not in row


def test_a_stale_row_of_the_old_shape_is_flagged(tmp_path: Path) -> None:
    """The very rows this slice corrected, planted as they were: the table row, the diagram label
    and the rejected-alternatives row."""
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "04_VAULT_BACKEND.md").write_text(
        "| Service | Choice | Licence | Role |\n| --- | --- | --- | --- |\n"
        "| Object store | MinIO | AGPL-3.0, run unmodified as a separate service | Documents |\n",
        encoding="utf-8",
    )
    (spec / "00_ARCHITECTURE.md").write_text(
        "   │  Working-set cache: Valkey     Object store: MinIO     Index: OpenSearch  │\n"
        "| MongoDB | SSPL | PostgreSQL / MinIO | |\n",
        encoding="utf-8",
    )
    found = find_other_object_stores(spec, "SeaweedFS")
    assert found == [
        "00_ARCHITECTURE.md:1 names MinIO, not SeaweedFS",
        "00_ARCHITECTURE.md:2 names MinIO, not SeaweedFS",
        "04_VAULT_BACKEND.md:3 names MinIO, not SeaweedFS",
    ]


def test_a_decision_log_entry_that_records_the_replacement_is_not_a_table_of_what_ships(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "06_DECISIONS.md").write_text(
        "| 3 | MinIO's public images are withdrawn | SeaweedFS |\n", encoding="utf-8"
    )
    assert find_other_object_stores(spec, "SeaweedFS") == []


def test_a_mention_in_prose_is_not_a_table() -> None:
    assert _lines_naming_a_store("It replaced MinIO (AGPL-3.0) under ADR-114 Amendment 9.\n") == []
