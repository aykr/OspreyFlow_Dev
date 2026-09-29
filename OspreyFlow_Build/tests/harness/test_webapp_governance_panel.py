"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 1 — the Governance screen's own real-data
exceptions panel over `scripts/real_data_exceptions.py`. The Governance screen's own config fields
need no test here: they round-trip through the same generic `PUT /api/config` `test_webapp_screens.
py` already proves for every other section. This file is the panel's own three routes only.

Every test injects its own `real_data_exceptions_path` (never the real, gitignored
`scripts.real_data_exceptions.CONFIG_PATH`) — this suite must never write to, or depend on the
contents of, the owner's own local file (`CLAUDE.md` rule 9 / ADR-035 §C3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from harness.webapp import create_app

_WELLFORMED = {
    "dataset": "Test Corpus",
    "approved_uses": ["local_development"],
    "added_by": "tester",
    "device": "test-host",
    "justification": "testing the panel",
    "decision_record": "ADR-035 §C3",
}


def _client(config_path: Path, real_data_exceptions_path: Path) -> TestClient:
    app = create_app(config_path=config_path, real_data_exceptions_path=real_data_exceptions_path)
    return TestClient(app, client=("127.0.0.1", 51000))


def test_no_local_file_means_an_empty_panel(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "real_data_exceptions.yaml")
    response = client.get("/api/real-data-exceptions")
    assert response.status_code == 200
    assert response.json() == {"exceptions": []}


def test_adding_an_exception_through_the_panel_is_readable_back(tmp_path: Path) -> None:
    rde_path = tmp_path / "real_data_exceptions.yaml"
    client = _client(tmp_path / "osprey.yaml", rde_path)

    response = client.post("/api/real-data-exceptions", json=_WELLFORMED)
    assert response.status_code == 201
    assert response.json()["dataset"] == "Test Corpus"
    assert response.json()["decision_record"] == "ADR-035 §C3"

    listed = client.get("/api/real-data-exceptions").json()["exceptions"]
    assert [e["dataset"] for e in listed] == ["Test Corpus"]

    # The panel writes only the local, gitignored file's own path — never a fixture or a
    # committed one (STANDING.md / CLAUDE.md rule 9).
    assert rde_path.exists()
    on_disk = yaml.safe_load(rde_path.read_text())
    assert on_disk["exceptions"][0]["dataset"] == "Test Corpus"


def test_adding_a_duplicate_dataset_through_the_panel_is_409(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "real_data_exceptions.yaml")
    client.post("/api/real-data-exceptions", json=_WELLFORMED)
    response = client.post("/api/real-data-exceptions", json=_WELLFORMED)
    assert response.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"decision_record": ""},
        {"decision_record": "not-a-real-reference"},
        {"decision_record": "ADR-35"},
        {"approved_uses": ["not_a_real_use"]},
        {"dataset": ""},
    ],
)
def test_a_malformed_entry_is_422_through_the_panel(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    """The same planted-violation shapes `tests/test_real_data_exceptions.py` already proves
    fail closed at the module level — proven again here at the route the browser panel actually
    calls, per `CLAUDE.md` rule 12's own "name the test" discipline."""
    client = _client(tmp_path / "osprey.yaml", tmp_path / "real_data_exceptions.yaml")
    body = {**_WELLFORMED, **overrides}
    response = client.post("/api/real-data-exceptions", json=body)
    assert response.status_code == 422


def test_removing_an_exception_through_the_panel(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "real_data_exceptions.yaml")
    client.post("/api/real-data-exceptions", json=_WELLFORMED)

    response = client.delete("/api/real-data-exceptions/Test Corpus")
    assert response.status_code == 200
    assert client.get("/api/real-data-exceptions").json() == {"exceptions": []}


def test_removing_a_dataset_not_present_is_404(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "real_data_exceptions.yaml")
    response = client.delete("/api/real-data-exceptions/Not There")
    assert response.status_code == 404


def test_an_entry_predating_decision_record_is_surfaced_as_422_not_silently_dropped(
    tmp_path: Path,
) -> None:
    """The queue brief's own instruction: "state... that any existing local entry is invalid
    until the owner adds the field — the maker cannot see that file and must not try." Proven
    here as the real, observable behaviour: a pre-existing entry missing `decision_record`
    surfaces as a 422 naming the field, not an empty list pretending nothing was ever admitted."""
    rde_path = tmp_path / "real_data_exceptions.yaml"
    rde_path.write_text(
        """
exceptions:
  - dataset: "Pre-existing Corpus"
    approved_uses: [local_development]
    added_by: someone
    added_date: "2026-09-20"
    device: some-host
    justification: admitted before decision_record existed
""",
        encoding="utf-8",
    )
    client = _client(tmp_path / "osprey.yaml", rde_path)
    response = client.get("/api/real-data-exceptions")
    assert response.status_code == 422
    assert "decision_record" in response.json()["detail"]
