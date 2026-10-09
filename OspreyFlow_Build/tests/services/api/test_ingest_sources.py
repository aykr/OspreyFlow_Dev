"""`GET /v1/investigations/{id}/ingest/source-files`'s refusals — owner ruling R6, 27 September
2026.

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

from tests.services.api.any_case import AnyCase

#: ADR-099 Amendment 3: the Studio's routes are the case's.
CASE = "/v1/investigations/inv-1"


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
    from services.api.app import app, get_audit, get_investigations, get_principal

    from tests.services.api.test_studio_recipe_routes import SOURCE_AUTHOR, _FakeAudit

    (tmp_path / "cdr.csv").write_text("a\n1\n", encoding="utf-8")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    try:
        response = TestClient(app).get(f"{CASE}/ingest/source-files")
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
    from services.api.app import app, get_audit, get_investigations, get_principal

    from tests.services.api.test_studio_recipe_routes import NO_ROLE_ANALYST, _FakeAudit

    (tmp_path / "secret-evidence.csv").write_text("a\n1\n", encoding="utf-8")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    app.dependency_overrides[get_principal] = lambda: NO_ROLE_ANALYST
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    try:
        response = TestClient(app).get(f"{CASE}/ingest/source-files")
        assert response.status_code == 403, response.text
        assert "secret-evidence" not in response.text, (
            "the refusal named a file in the mount — a principal who may not list it must not "
            f"learn what is in it: {response.text}"
        )
    finally:
        app.dependency_overrides.clear()


# --- Upload from the analyst's computer (ADR-067, owner ruling of 3 October 2026) ----------------
#
# The owner asked for a real file picker. Ruling R6 had put browser upload after the milestone; it
# is now in, and it is the first thing that WRITES into the ingest area. The property R6 protected
# (the Conduit never alters operator-supplied evidence) is kept by writing only into one separate
# subfolder, `uploaded/`, and by never overwriting anything. Each refusal below has a case, and
# each planted violation takes the shape a real request takes.

import asyncio  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

from services.api.ingest_sources import (  # noqa: E402
    UPLOAD_SUBDIR,
    UploadRefused,
    save_upload,
    validate_upload_name,
)


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


def _save(
    root: Path, name: str, *parts: bytes, max_bytes: int = 1024, dataset_id: str | None = None
):
    return asyncio.run(
        save_upload(root, name, _chunks(*parts), max_bytes=max_bytes, dataset_id=dataset_id)
    )


def _refusal(root: Path, name: str, *parts: bytes, max_bytes: int = 1024) -> UploadRefused:
    with pytest.raises(UploadRefused) as caught:
        _save(root, name, *parts, max_bytes=max_bytes)
    return caught.value


@pytest.mark.parametrize(
    "name",
    ["carrier a 2026-09.csv", "Report.PDF", "extract.tar.gz", "voice_01.wav", "a.b.c.csv"],
)
def test_ordinary_names_of_known_types_are_accepted(name: str) -> None:
    assert validate_upload_name(name) == name


@pytest.mark.parametrize(
    "name, code",
    [
        ("", "bad_name"),
        ("   ", "bad_name"),
        ("..", "bad_name"),
        ("../evil.csv", "bad_name"),
        ("sub/evil.csv", "bad_name"),
        ("sub\\evil.csv", "bad_name"),
        (".hidden.csv", "bad_name"),
        ("nul\x00.csv", "bad_name"),
        ("tab\t.csv", "bad_name"),
        ("x" * 201 + ".csv", "bad_name"),
        ("noextension", "type_not_allowed"),
        ("run.exe", "type_not_allowed"),
        ("script.sh", "type_not_allowed"),
        ("module.py", "type_not_allowed"),
        ("archive.csv.exe", "type_not_allowed"),
    ],
)
def test_names_that_could_escape_or_hide_or_run_are_refused(name: str, code: str) -> None:
    with pytest.raises(UploadRefused) as caught:
        validate_upload_name(name)
    assert caught.value.code == code, (name, caught.value.code)


def test_an_upload_lands_in_the_uploaded_folder_with_its_bytes_intact(root: Path) -> None:
    saved = _save(root, "new.csv", b"a,b\n", b"1,2\n")
    assert (root / UPLOAD_SUBDIR / "new.csv").read_bytes() == b"a,b\n1,2\n"
    assert saved.name == "new.csv"
    assert saved.source_location == str(root / UPLOAD_SUBDIR / "new.csv")
    assert saved.size_bytes == 8
    assert saved.uploaded is True


def test_an_upload_never_overwrites_a_file_of_the_same_name(root: Path) -> None:
    """**The planted violation is a name that already exists in each place it could.** Overwriting
    in `uploaded/` would silently replace data a draft already points at; matching an operator's
    file in the root would let the same name mean two things in the picker."""
    _save(root, "again.csv", b"first")
    assert _refusal(root, "again.csv", b"second").code == "exists"
    assert (root / UPLOAD_SUBDIR / "again.csv").read_bytes() == b"first"

    assert _refusal(root, "cdr-carrier-a.csv", b"x").code == "exists"
    assert (root / "cdr-carrier-a.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_a_refused_upload_leaves_nothing_behind(root: Path) -> None:
    """Too large, empty and duplicate must all clean up their temporary part-file; a stray
    `.upload-*.part` would be invisible in the picker (dotfiles are skipped) and never removed."""
    assert _refusal(root, "big.csv", b"x" * 600, b"x" * 600, max_bytes=1000).code == "too_large"
    assert _refusal(root, "empty.csv", b"").code == "empty"
    leftovers = list((root / UPLOAD_SUBDIR).iterdir()) if (root / UPLOAD_SUBDIR).exists() else []
    assert leftovers == [], leftovers


def test_the_size_limit_stops_reading_at_the_limit_not_after_the_whole_body(root: Path) -> None:
    """Counting while streaming is what makes the limit a limit: a check after the fact would have
    already written the whole file to disk."""
    read: list[int] = []

    async def counting() -> AsyncIterator[bytes]:
        for i in range(100):
            read.append(i)
            yield b"x" * 100

    with pytest.raises(UploadRefused) as caught:
        asyncio.run(save_upload(root, "huge.csv", counting(), max_bytes=250))
    assert caught.value.code == "too_large"
    assert len(read) < 10, f"read {len(read)} chunks of a 250-byte limit"


def test_uploaded_files_are_listed_and_marked_and_operator_files_are_not(root: Path) -> None:
    _save(root, "mine.csv", b"1")
    listing = list_source_files(root)
    flags = {f.name: f.uploaded for f in listing.files}
    assert flags == {"cdr-carrier-a.csv": False, "device-extract.xml": False, "mine.csv": True}


def test_a_symlink_or_folder_inside_uploaded_is_not_listed(root: Path, tmp_path: Path) -> None:
    """The uploaded folder is the one place below the root that is listed, so the same
    resolve-then-compare rule has to hold for it: a link out of it, or a nested folder, is skipped."""
    folder = root / UPLOAD_SUBDIR
    folder.mkdir()
    outside = tmp_path.parent / "elsewhere.txt"
    outside.write_text("not evidence", encoding="utf-8")
    (folder / "link.csv").symlink_to(outside)
    (folder / "nested").mkdir()
    (folder / "nested" / "deep.csv").write_text("x", encoding="utf-8")
    _save(root, "real.csv", b"1")

    names = {f.name for f in list_source_files(root).files}
    assert "link.csv" not in names and "deep.csv" not in names and "nested" not in names
    assert "real.csv" in names


def test_the_uploaded_folder_is_not_itself_offered_as_a_file(root: Path) -> None:
    _save(root, "one.csv", b"1")
    assert UPLOAD_SUBDIR not in {f.name for f in list_source_files(root).files}


# --- the upload route (CLAUDE.md rule 4: its own access-control case) ---------------------------


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, principal_name: str = "SOURCE_AUTHOR"):
    from fastapi.testclient import TestClient
    from services.api.app import app, get_audit, get_investigations, get_principal

    from tests.services.api import test_studio_recipe_routes as fixtures

    audit = fixtures._FakeAudit()
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    app.dependency_overrides[get_principal] = lambda: getattr(fixtures, principal_name)
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: audit
    return TestClient(app), app, audit


def test_a_source_author_can_upload_and_the_file_is_then_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app, _audit = _client(monkeypatch, tmp_path)
    try:
        response = client.post(
            f"{CASE}/ingest/source-files",
            params={"name": "carrier.csv"},
            content=b"a,b\n1,2\n",
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["name"] == "carrier.csv" and body["uploaded"] is True
        assert body["source_location"] == str(tmp_path / UPLOAD_SUBDIR / "carrier.csv")
        listed = client.get(f"{CASE}/ingest/source-files").json()["files"]
        assert [f["name"] for f in listed] == ["carrier.csv"]
    finally:
        app.dependency_overrides.clear()


def test_an_upload_is_audited_with_its_name_and_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app, audit = _client(monkeypatch, tmp_path)
    try:
        client.post(f"{CASE}/ingest/source-files", params={"name": "c.csv"}, content=b"12345")
        recorded = [r for r in audit.records if r.get("action") == "upload_ingest_source_file"]
        assert len(recorded) == 1, audit.records
        assert recorded[0]["resolved_query"] == {"name": "c.csv", "size_bytes": 5}
    finally:
        app.dependency_overrides.clear()


def test_a_principal_without_the_source_author_role_cannot_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Rule 4 for the first route that writes here.** The refusal must happen before a byte is
    written, and must not say anything about what is already in the folder."""
    client, app, _audit = _client(monkeypatch, tmp_path, "NO_ROLE_ANALYST")
    (tmp_path / "secret-evidence.csv").write_text("a\n1\n", encoding="utf-8")
    try:
        response = client.post(
            f"{CASE}/ingest/source-files", params={"name": "sneaky.csv"}, content=b"data"
        )
        assert response.status_code == 403, response.text
        assert "secret-evidence" not in response.text
        assert not (tmp_path / UPLOAD_SUBDIR).exists() or not any(
            (tmp_path / UPLOAD_SUBDIR).iterdir()
        ), "a refused principal's upload was written"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "name, status",
    [("../evil.csv", 400), ("x.exe", 415), (".hidden.csv", 400), ("a/b.csv", 400)],
)
def test_the_route_refuses_unsafe_names_and_writes_nothing_outside_uploaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, status: int
) -> None:
    client, app, _audit = _client(monkeypatch, tmp_path / "ingest")
    (tmp_path / "ingest").mkdir()
    try:
        response = client.post(
            f"{CASE}/ingest/source-files", params={"name": name}, content=b"data"
        )
        assert response.status_code == status, (name, response.status_code, response.text)
        written = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert written == [], written
    finally:
        app.dependency_overrides.clear()


def test_the_route_says_409_for_an_existing_name_and_413_for_a_file_over_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app, _audit = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("OSPREY_INGEST_MAX_UPLOAD_BYTES", "10")
    try:
        assert client.post(f"{CASE}/ingest/source-files", params={"name": "a.csv"}, content=b"1234").status_code == 201
        assert client.post(f"{CASE}/ingest/source-files", params={"name": "a.csv"}, content=b"5678").status_code == 409
        too_big = client.post(f"{CASE}/ingest/source-files", params={"name": "b.csv"}, content=b"x" * 11)
        assert too_big.status_code == 413, too_big.text
        assert not (tmp_path / UPLOAD_SUBDIR / "b.csv").exists()
    finally:
        app.dependency_overrides.clear()


# --- ADR-099 Amendment 3 part (d): a source file belongs to a dataset --------------------------


def test_an_upload_made_in_a_case_lands_in_its_datasets_folder(root: Path) -> None:
    saved = _save(root, "calls.csv", b"a\n", dataset_id="fixture-corp")
    assert (root / UPLOAD_SUBDIR / "fixture-corp" / "calls.csv").read_bytes() == b"a\n"
    assert saved.dataset_id == "fixture-corp" and saved.uploaded is True


def test_a_case_is_offered_its_datasets_files_and_not_another_datasets(root: Path) -> None:
    """A case reading Fixture Corp sees Fixture Corp's uploads and its operator drops (a folder of
    that dataset's id under the root), never Enron's; the files placed in the root before the
    amendment, in no dataset yet, are offered and marked so (`dataset_id` none)."""
    _save(root, "mine.csv", b"1", dataset_id="fixture-corp")
    _save(root, "theirs.csv", b"1", dataset_id="enron")
    (root / "fixture-corp").mkdir()
    (root / "fixture-corp" / "dropped.csv").write_text("x", encoding="utf-8")
    listing = list_source_files(root, datasets=["fixture-corp"])
    offered = {f.name: f.dataset_id for f in listing.files}
    assert offered == {
        "cdr-carrier-a.csv": None,
        "device-extract.xml": None,
        "mine.csv": "fixture-corp",
        "dropped.csv": "fixture-corp",
    }


def test_a_dataset_id_that_is_not_a_plain_folder_name_is_never_made_a_path(root: Path) -> None:
    """The folder is named for the dataset, so its id must be a plain name: anything that could
    climb out of the root is refused rather than joined."""
    from services.api.ingest_sources import UploadRefused

    with pytest.raises(UploadRefused):
        _save(root, "x.csv", b"1", dataset_id="../escape")
    assert {f.name for f in list_source_files(root, datasets=["../escape"]).files} == {
        "cdr-carrier-a.csv",
        "device-extract.xml",
    }


# --- An ingest folder that cannot be written --------------------------------------------------
#
# 9 October 2026, the data engineer's journey: the deployment had been rendered before ADR-067's
# writable `uploaded/` mount existed, so the whole ingest root was read-only in the container. The
# upload died in `mkdir` with `OSError: [Errno 30] Read-only file system` and the Studio showed "The
# upload was refused (500)". The planted fault is that same error, from that same call.


def _read_only_mkdir(monkeypatch: pytest.MonkeyPatch) -> None:
    import errno

    def refuse(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError(errno.EROFS, "Read-only file system", str(self))

    monkeypatch.setattr(Path, "mkdir", refuse)


def test_a_read_only_ingest_folder_is_a_refusal_that_says_so(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _read_only_mkdir(monkeypatch)
    refusal = _refusal(root, "calls.csv", b"a,b\n")
    assert refusal.code == "not_writable"
    assert "cannot be written" in refusal.message


def test_a_folder_the_server_may_not_write_is_the_same_refusal(root: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root writes through a read-only mode")
    (root / UPLOAD_SUBDIR).mkdir()
    (root / UPLOAD_SUBDIR).chmod(0o555)
    try:
        assert _refusal(root, "calls.csv", b"a,b\n").code == "not_writable"
    finally:
        (root / UPLOAD_SUBDIR).chmod(0o755)


def test_the_route_says_503_with_a_sentence_for_a_read_only_ingest_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app, _audit = _client(monkeypatch, tmp_path)
    _read_only_mkdir(monkeypatch)
    try:
        response = client.post(
            f"{CASE}/ingest/source-files", params={"name": "calls.csv"}, content=b"a,b\n"
        )
        assert response.status_code == 503, response.text
        assert "cannot be written" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
