"""A set's claims part never holds the map key file (ADR-147 decision 1: a provider's key typed in
*Admin › Maps* is "never in `osprey.yaml`, the maps file, a response, a log record, an audit row or a
backup"; spec 05 §6.1). On the cloud-platform shapes the claims run backs up the shared claim's
`map-settings` folder (`cloud_platform_backups.SHARED_PARTS`, the ADR-148 audit's ruling 3), where
the maps file (`maps.yaml`) and the map key file (`map-keys.yaml`, `600`) sit side by side
(`services/api/map_admin.py`); the maps file belongs in the set and the key file never does
(rules-b's find, 15 November 2026). Run as the claims run runs, against the S3 stand-in."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from typing import Any

import pytest
from services.api import platform_backup as pb

from tests.cloud_platform_backup.conftest import BUCKET, Running

PART = "shared-map-settings"


@pytest.fixture
def map_settings(tmp_path: Path) -> Path:
    """The claims folder as the claims run mounts the shared claim's `map-settings` subPath."""
    root = tmp_path / "claims"
    folder = root / PART
    folder.mkdir(parents=True)
    (folder / "maps.yaml").write_text("providers:\n  - name: os-maps\n    credential: admin\n")
    (folder / "map-keys.yaml").write_text("os-maps: synthetic-provider-key-0000\n")
    (folder / "map-keys.yaml").chmod(0o600)
    (folder / ".maps.lock").write_text("")
    return root


def _names(aws: Running, run: Any, claims: Path) -> list[str]:
    settings, _bucket, _stores, _ = run
    settings = pb.Settings(**{**settings.__dict__, "claims": (PART,), "claims_folder": claims,
                              "job_name": "ospreyflow-backup-claims-29906055"})  # fmt: skip
    part = pb.take_claims(settings, pb.Bucket(settings))
    data = aws.stand_in.read(BUCKET, part[PART]["key"])
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        return tar.getnames()


def test_the_claims_part_holds_the_maps_file_and_never_the_map_key_file(
    aws: Running, run: Any, map_settings: Path
) -> None:
    names = _names(aws, run, map_settings)
    assert "maps.yaml" in names, names
    assert "map-keys.yaml" not in names, (
        "a provider's key is never in a backup (ADR-147 decision 1)"
    )
    assert not any(b"synthetic-provider-key" in n.encode() for n in names)


def _finished_set(run: Any, claims: Path) -> tuple[pb.Settings, pb.Bucket, str]:
    """A finished set of one slot, its claims part `shared-map-settings`, as both runs make it."""
    from tests.cloud_platform_backup.test_platform_backup_claims import SLOT, Clock

    settings, bucket, stores, _ = run

    def with_claims(job: str) -> pb.Settings:
        return pb.Settings(**{**settings.__dict__, "claims": (PART,), "claims_folder": claims,
                              "job_name": f"{job}-{SLOT}", "claims_wait": 600})  # fmt: skip

    main, other = with_claims("ospreyflow-backup"), with_claims("ospreyflow-backup-claims")
    clock = Clock()
    clock.on_sleep.append(lambda: pb.take_claims(other, pb.Bucket(other)))
    return main, bucket, pb.take(main, bucket, stores, clock=clock, sleep=clock.sleep)["set"]


def test_a_restore_never_puts_a_key_back_from_a_set_and_keeps_the_deployment_s_own(
    aws: Running, run: Any, map_settings: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A set taken before this fix holds the key file: the restore leaves it out, and the key file
    on the claim, the deployment's own, stays as it is (as the standard shapes' restore leaves it on
    the volume; `map_admin` gives it to a provider only at the address it was entered for)."""
    monkeypatch.setattr(pb, "LEFT_OUT", {})  # the claims run as it was before the fix
    _main, bucket, set_id = _finished_set(run, map_settings)
    monkeypatch.undo()
    target = tmp_path / "restored"
    (target / PART).mkdir(parents=True)
    (target / PART / "map-keys.yaml").write_text("os-maps: the-deployment-s-own-key\n")
    (target / PART / "written after the set.yaml").write_text("not in the set\n")
    assert pb.fetch_claims(bucket, set_id, target) == [PART]
    root = target / PART
    assert (root / "maps.yaml").read_text() == (map_settings / PART / "maps.yaml").read_text()
    assert (root / "map-keys.yaml").read_text() == "os-maps: the-deployment-s-own-key\n"
    assert not (root / "written after the set.yaml").exists(), "the claim is the set's otherwise"


def test_a_restore_onto_a_claim_with_no_key_file_puts_none_there(
    aws: Running, run: Any, map_settings: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pb, "LEFT_OUT", {})
    _main, bucket, set_id = _finished_set(run, map_settings)
    monkeypatch.undo()
    target = tmp_path / "restored"
    pb.fetch_claims(bucket, set_id, target)
    assert not (target / PART / "map-keys.yaml").exists(), "never a key from a backup"


def test_restore_claims_names_each_provider_whose_key_is_entered_again(
    aws: Running,
    run: Any,
    map_settings: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (map_settings / PART / "maps.yaml").write_text(
        "providers:\n  - name: os-maps\n  - name: mapbox\n  - name: osm\nkeys_held: [mapbox, os-maps]\n"
    )
    main, _bucket, set_id = _finished_set(run, map_settings)
    target = tmp_path / "restored"
    restoring = pb.Settings(**{**main.__dict__, "claims_folder": target})
    monkeypatch.setattr(pb.Settings, "from_env", staticmethod(lambda *a, **k: restoring))
    monkeypatch.setattr(pb, "writers_stopped", lambda _s: None)
    assert pb.main(["restore-claims", "--set", set_id]) == 0
    said = capsys.readouterr().out
    assert f"{PART} put back from set {set_id}" in said
    assert "enter the key of mapbox, os-maps again, in Admin › Maps" in said, said
    assert "a backup never holds a map key" in said, said
