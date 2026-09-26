"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 2 — the artefacts diff before Launch
(`05_DEPLOYMENT.md` §2.1/§2.4). `POST /api/artefacts/generate` wraps `harness.render.render` and
`diff_for` exactly as `python -m harness.render` itself does — no second renderer, no invented
capability."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from harness.webapp import create_app


def _fake_resolver(image: object) -> str:
    return "sha256:" + f"{abs(hash(image)):064x}"[:64]


def _client(config_path: Path, out_root: Path) -> TestClient:
    app = create_app(config_path=config_path, out_root=out_root, render_resolver=_fake_resolver)
    return TestClient(app, client=("127.0.0.1", 51000))


def test_generate_writes_the_four_artefacts_and_a_copy_of_osprey_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})

    response = client.post("/api/artefacts/generate")
    assert response.status_code == 200
    body = response.json()
    assert set(body["artefacts"]) == {
        "compose.yaml",
        "deployment.env",
        "versions.lock",
        "RUNBOOK.md",
    }
    assert body["confirmed"] is False
    assert body["osprey_yaml"] == config_path.read_text(encoding="utf-8")

    out_dir = out_root / "local-lite"
    on_disk = (out_dir / "compose.yaml").read_text(encoding="utf-8")
    assert on_disk == body["artefacts"]["compose.yaml"]
    assert (out_dir / "osprey.yaml").is_file()


def test_the_first_generate_shows_every_artefact_as_changed(tmp_path: Path) -> None:
    """§2.4's own "before it runs, as a diff against the current state" — nothing on disk yet, so
    every path is new."""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})

    body = client.post("/api/artefacts/generate").json()
    assert set(body["diffs"]) == {"compose.yaml", "deployment.env", "versions.lock", "RUNBOOK.md"}


def test_generating_again_with_no_change_shows_nothing_changed(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})

    client.post("/api/artefacts/generate")
    second = client.post("/api/artefacts/generate").json()
    assert second["diffs"] == {}


def test_a_same_profile_change_shows_the_real_diff_before_it_is_written(tmp_path: Path) -> None:
    """The change-preview guard's own real value: publishing the Conduit's port changes
    `compose.yaml`'s own `api:` service, and the diff proves that is what's shown, not merely
    that something is. (A *profile* switch renders into its own `deploy/generated/<profile>/`
    directory — `harness/render.py`'s own docstring: "rendering per-profile keeps two renders
    from overwriting each other" — so it is a fresh render there, correctly, not a diff against a
    different profile's own directory; not the case this test exercises.)"""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    client.post("/api/artefacts/generate")

    client.put("/api/config", json={"network": {"expose_conduit": True}})
    body = client.post("/api/artefacts/generate").json()
    assert "compose.yaml" in body["diffs"]
    assert "OSPREY_API_PORT" in body["diffs"]["compose.yaml"]


def test_get_artefacts_before_any_generate_is_a_clean_404(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated")
    response = client.get("/api/artefacts")
    assert response.status_code == 404


def test_downloading_one_artefact_returns_its_real_content(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    generated = client.post("/api/artefacts/generate").json()

    response = client.get("/api/artefacts/RUNBOOK.md")
    assert response.status_code == 200
    assert response.text == generated["artefacts"]["RUNBOOK.md"]
    assert "attachment" in response.headers["content-disposition"]


def test_downloading_before_any_generate_is_a_clean_404(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated")
    response = client.get("/api/artefacts/compose.yaml")
    assert response.status_code == 404


def test_confirm_requires_a_prior_generate(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated")
    response = client.post("/api/artefacts/confirm")
    assert response.status_code == 422


def test_confirm_after_generate_is_reflected_in_get_artefacts(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    client.post("/api/artefacts/generate")

    assert client.get("/api/artefacts").json()["confirmed"] is False
    confirmed = client.post("/api/artefacts/confirm").json()
    assert confirmed["confirmed"] is True
    assert client.get("/api/artefacts").json()["confirmed"] is True


def test_a_second_generate_resets_confirmation(tmp_path: Path) -> None:
    """A regenerated artefact set has not itself been reviewed again — confirming the first set
    must not silently carry over to a changed one."""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    client.post("/api/artefacts/generate")
    client.post("/api/artefacts/confirm")

    client.post("/api/artefacts/generate")
    assert client.get("/api/artefacts").json()["confirmed"] is False
