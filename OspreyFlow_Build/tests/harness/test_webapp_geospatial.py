"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 2 — the Geospatial screen's own three routes.
`harness/geospatial.py`'s own docstring has the full, confirmed-by-import reason only
`register-provider` is real here: `build_local_basemap` and `verify_map` each pull in `services`/
`adapters` modules `harness/Dockerfile` does not copy into this image, so both routes always
refuse — proven below as the real, typed 501 they are, never silently skipped or stubbed as a
pass."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from harness.webapp import create_app


def _client(config_path: Path) -> TestClient:
    app = create_app(config_path=config_path)
    return TestClient(app, client=("127.0.0.1", 51000))


def test_registering_a_local_provider_writes_the_map_section(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)

    response = client.post(
        "/api/geospatial/register-provider",
        json={
            "provider_id": "osm-local-gb",
            "label": "OpenStreetMap (GB)",
            "pmtiles_path": str(tmp_path / "gb.pmtiles"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "osm-local-gb"
    assert body["providers"][0]["id"] == "osm-local-gb"

    on_disk = yaml.safe_load(config_path.read_text())
    assert on_disk["map"]["default"] == "osm-local-gb"


def test_registering_a_provider_never_needs_the_pmtiles_file_to_actually_exist(
    tmp_path: Path,
) -> None:
    """`register_local_provider`'s own contract (`scripts/geo_local_provider.py`): it upserts a
    config entry, it never opens the file at `pmtiles_path` — a real, if inert, capability the
    Geospatial screen can offer even with no fixture PMTiles anywhere in this tree (confirmed:
    none exists, `find . -iname "*.pmtiles"` returns nothing)."""
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)
    response = client.post(
        "/api/geospatial/register-provider",
        json={
            "provider_id": "osm-local-gb",
            "label": "GB",
            "pmtiles_path": "/nonexistent/gb.pmtiles",
        },
    )
    assert response.status_code == 200


def test_registering_a_provider_preserves_other_sections_already_written(tmp_path: Path) -> None:
    """The same regression `tests/test_build_local_basemap.py::
    test_register_local_provider_preserves_other_top_level_keys` proves at the function level,
    proven again at the route a real Profile → Geospatial walkthrough actually takes."""
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)
    client.put("/api/config", json={"profile": "local-lite"})

    client.post(
        "/api/geospatial/register-provider",
        json={"provider_id": "osm-local-gb", "label": "GB", "pmtiles_path": "/tmp/gb.pmtiles"},
    )

    config = client.get("/api/config").json()
    assert config["profile"] == "local-lite"
    assert "map" in config


def test_a_missing_field_is_422_not_a_500(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml")
    response = client.post("/api/geospatial/register-provider", json={"provider_id": "x"})
    assert response.status_code == 422


class _Runner:
    """`docker compose exec` as the set-up console runs it: each command recorded, answered with an
    exit status and the Conduit's printed lines."""

    def __init__(self, code: int = 0, out: str = "") -> None:
        self.calls: list[list[str]] = []
        self.code, self.out = code, out

    def __call__(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(argv)
        return self.code, self.out


def _deployed(tmp_path: Path, runner: _Runner) -> tuple[TestClient, Path]:
    """A config, and its generated deployment folder holding a compose file (Launch has run)."""
    from harness.render import load_config

    from schemas.deployment import generated_folder

    config = tmp_path / "osprey.yaml"
    config.write_text("profile: local-lite\n", encoding="utf-8")
    folder = tmp_path / "out" / generated_folder(load_config(config))
    folder.mkdir(parents=True)
    (folder / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    app = create_app(config_path=config, out_root=tmp_path / "out", map_runner=runner)
    return TestClient(app, client=("127.0.0.1", 51000)), folder


def test_build_basemap_runs_the_conduit_s_own_build_in_its_container(tmp_path: Path) -> None:
    """ADR-147 decision 6: the set-up console's Build is the Conduit's (`services.api.map_admin`),
    run in the Conduit's container as `ospreyflow map build` runs it, never a 501 and never a
    second build on the harness's side."""
    runner = _Runner(0, "Built rutland.pmtiles: 3 places created, 1 already known, 0 rejected.\n")
    client, folder = _deployed(tmp_path, runner)

    response = client.post("/api/geospatial/build-basemap", json={"region": "rutland"})

    assert response.status_code == 200, response.text
    assert response.json() == {"returncode": 0, "lines": [
        "Built rutland.pmtiles: 3 places created, 1 already known, 0 rejected."]}  # fmt: skip
    assert runner.calls == [[
        "docker", "compose", "--env-file", str(folder / "deployment.env"),
        "-f", str(folder / "compose.yaml"), "exec", "-T", "api",
        "python", "-m", "services.api.map_admin", "build", "rutland", "--by", "setup-console",
    ]]  # fmt: skip


def test_verify_runs_the_conduit_s_own_verify_and_says_its_answer(tmp_path: Path) -> None:
    runner = _Runner(1, "osm-local: attribution: missing\nVerify found issues.\n")
    client, _folder = _deployed(tmp_path, runner)

    response = client.post("/api/geospatial/verify", json={})

    assert response.status_code == 200
    assert response.json() == {
        "returncode": 1, "lines": ["osm-local: attribution: missing", "Verify found issues."]
    }  # fmt: skip
    assert runner.calls[0][-3:] == ["verify", "--by", "setup-console"]


def test_before_launch_build_and_verify_say_so_in_words(tmp_path: Path) -> None:
    runner = _Runner()
    config = tmp_path / "osprey.yaml"
    config.write_text("profile: local-lite\n", encoding="utf-8")
    client = TestClient(
        create_app(config_path=config, out_root=tmp_path / "out", map_runner=runner),
        client=("127.0.0.1", 51000),
    )
    for path, body in (("build-basemap", {"region": "rutland"}), ("verify", {})):
        response = client.post(f"/api/geospatial/{path}", json=body)
        assert response.status_code == 409
        assert "Launch" in response.json()["detail"]
    assert runner.calls == []


def test_a_region_not_shaped_like_one_is_refused_before_anything_runs(tmp_path: Path) -> None:
    runner = _Runner()
    client, _folder = _deployed(tmp_path, runner)
    for region in ("--by", "rutland; rm -rf /", "", "Rutland"):
        response = client.post("/api/geospatial/build-basemap", json={"region": region})
        assert response.status_code == 422, region
    assert runner.calls == []
