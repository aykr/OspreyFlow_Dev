"""`GET /v1/ingest/source-files`'s refusals — owner ruling R6, 27 September 2026.

This route's whole job is to enumerate one directory and refuse everything else, so the refusals
are what is tested. Per `CLAUDE.md` rule 4 the access-control case is here rather than deferred,
and per rule 15 each planted violation takes the shape the real thing takes — a real symlink on a
real filesystem, not a hand-written path string that happens to contain `..`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from services.api.ingest_sources import ingest_root, is_inside, list_source_files


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "cdr-carrier-a.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "device-extract.xml").write_text("<x/>", encoding="utf-8")
    return tmp_path


def test_it_lists_the_files_in_the_root_with_a_usable_source_location(root: Path) -> None:
    listing = list_source_files(root)
    assert {f.name for f in listing.files} == {"cdr-carrier-a.csv", "device-extract.xml"}
    for file in listing.files:
        assert file.source_location == str(root / file.name), (
            "source_location must be the path the recipe engine will actually open — an analyst "
            "never types one, so a wrong value here is undiscoverable until the run fails"
        )
        assert file.size_bytes > 0


def test_a_symlink_pointing_outside_the_root_is_not_listed(root: Path, tmp_path: Path) -> None:
    """**The planted violation is a real symlink, because that is the real attack.** A string
    check on the unresolved path would list this happily: the name is inside the root and contains
    no `..` at all. Only resolving before comparing catches it."""
    secret = tmp_path.parent / "outside-the-root.txt"
    secret.write_text("not evidence", encoding="utf-8")
    (root / "innocent-looking.csv").symlink_to(secret)

    names = {f.name for f in list_source_files(root).files}
    assert "innocent-looking.csv" not in names, (
        "a symlink out of the ingest root was listed — resolve-then-compare is not in force, and "
        f"the Studio would offer a file outside the mount: {names}"
    )
    assert names == {"cdr-carrier-a.csv", "device-extract.xml"}


def test_is_inside_refuses_a_parent_escape_and_accepts_a_real_child(root: Path) -> None:
    assert is_inside(root, (root / "cdr-carrier-a.csv").resolve())
    assert not is_inside(root, (root / ".." / "elsewhere").resolve())
    assert not is_inside(root, Path("/etc/passwd"))


def test_directories_and_dotfiles_are_not_offered(root: Path) -> None:
    """No recursion and no host debris. A Connect stage that cannot express "descend" cannot be
    talked into descending, and `.DS_Store` is never evidence."""
    (root / "nested").mkdir()
    (root / "nested" / "deep.csv").write_text("x", encoding="utf-8")
    (root / ".DS_Store").write_text("junk", encoding="utf-8")

    names = {f.name for f in list_source_files(root).files}
    assert names == {"cdr-carrier-a.csv", "device-extract.xml"}, names


def test_a_missing_root_is_an_empty_listing_not_an_error(tmp_path: Path) -> None:
    """Docker creates a bind-mount source that does not exist, so "the operator has not put
    anything there yet" is a normal state and the Studio should say so rather than 500."""
    listing = list_source_files(tmp_path / "never-created")
    assert listing.files == []
    assert listing.root.endswith("never-created")


def test_the_root_comes_from_the_environment_the_renderer_sets(monkeypatch) -> None:
    """`harness/render.py` writes `OSPREY_INGEST_ROOT` into the deployment env precisely so this
    is not hard-coded twice; `tests/harness/test_render.py` asserts the other half."""
    monkeypatch.setenv("OSPREY_INGEST_ROOT", "/mnt/evidence/incoming")
    assert ingest_root() == Path("/mnt/evidence/incoming")
    monkeypatch.delenv("OSPREY_INGEST_ROOT")
    assert ingest_root() == Path("/var/lib/osprey/ingest")


def test_ordering_is_most_recent_first(root: Path) -> None:
    """An analyst who has just dropped a file in looks for it at the top."""
    newest = root / "just-arrived.csv"
    newest.write_text("x", encoding="utf-8")
    os.utime(newest, (2_000_000_000, 2_000_000_000))
    assert list_source_files(root).files[0].name == "just-arrived.csv"


# --- the route's own access control (CLAUDE.md rule 4) -------------------------------------------
# ruff: noqa: F811, F401  (the imported `client` fixture is used as each test's same-named parameter)


def test_the_route_lists_the_mounted_root_for_a_source_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from services.api.app import app, get_audit, get_principal

    from tests.services.api.test_studio_recipe_routes import SOURCE_AUTHOR, _FakeAudit

    (tmp_path / "cdr.csv").write_text("a\n1\n", encoding="utf-8")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    try:
        response = TestClient(app).get("/v1/ingest/source-files")
        assert response.status_code == 200, response.text
        assert [f["name"] for f in response.json()["files"]] == ["cdr.csv"]
        assert response.json()["files"][0]["source_location"] == str(tmp_path / "cdr.csv")
    finally:
        app.dependency_overrides.clear()


def test_a_principal_without_the_source_author_role_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Rule 4: every read path gets an access-control test, no exceptions.** The refusal must
    also not disclose whether the mount has anything in it — an analyst with no Studio role learns
    only that they may not ask, never how many files an operator has staged."""
    from fastapi.testclient import TestClient
    from services.api.app import app, get_audit, get_principal

    from tests.services.api.test_studio_recipe_routes import NO_ROLE_ANALYST, _FakeAudit

    (tmp_path / "secret-evidence.csv").write_text("a\n1\n", encoding="utf-8")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    app.dependency_overrides[get_principal] = lambda: NO_ROLE_ANALYST
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    try:
        response = TestClient(app).get("/v1/ingest/source-files")
        assert response.status_code == 403, response.text
        assert "secret-evidence" not in response.text, (
            "the refusal named a file in the mount — a principal who may not list it must not "
            f"learn what is in it: {response.text}"
        )
    finally:
        app.dependency_overrides.clear()
