"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part A's own exit test: "every screen round-trips its
answers through `osprey.yaml`; the rendered output matches Stage 2 §1's fixture for the same
answers" — for `local-lite` and `small`; "`cluster`'s stub behaviour is asserted as a stub, not
skipped" (the queue brief's own wording).

Each screen submits only its own top-level section (`PUT /api/config`'s own merge semantics,
`harness/webapp.py`'s own docstring has the reasoning) — proving both the round-trip and
`05_DEPLOYMENT.md` §2.1's "navigable in any order" property in the same test, rather than one
request carrying every answer at once.

**"Stage 2 §1's fixture" is `tests/harness/test_render.py::FIXTURE_CONFIG`, cited rather than
duplicated** — its own `governance`/`map` sections are written directly here (screens this round
does not build; `Governance`/`Geospatial` are explicitly out of this round's scope) so the
comparison is against the identical rendered bytes that file's own suite already proves stable,
not a fixture invented for this file alone. `local-lite`'s own case has no pre-existing textual
fixture to name-check against (`FIXTURE_CONFIG` is `profile: small`) — its own case instead proves
the same round-trip property directly: the API-driven config renders identically to constructing
the equivalent `OspreyConfig` and calling `render()` on it without going through this API at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from harness.render import ClusterRendererNotBuilt, load_config, render
from harness.webapp import create_app

from schemas.deployment import OspreyConfig

#: The two sections this round's own three screens do not cover — written directly to
#: `osprey.yaml` before the screens' own `PUT` calls, standing in for Governance/Geospatial
#: (out of this round's scope). Values are `FIXTURE_CONFIG`'s own, verbatim.
_GOVERNANCE_AND_MAP = """
governance:
  identity_provider: keycloak
  handling_scheme: uk-law-enforcement
  ontology: default
  real_data_exceptions: config/real_data_exceptions.yaml
map:
  default: osm-local
  providers:
    - id: osm-local
      label: OpenStreetMap
      kind: vector
      source: file:///data/tiles/osm-local.pmtiles
      attribution: "© OpenStreetMap contributors"
      licence: {id: ODbL, redistributable: true, client_scope: open}
"""

#: `test_render.py::FIXTURE_CONFIG`'s own `models` section, resubmitted here through the Models
#: screen's own route rather than imported, so this file does not depend on that one's internals.
_MODELS_ANSWER = {
    "local_only": False,
    "hosted_fallback": "example-hosted",
    "sendable_handling_codes": ["OFFICIAL"],
}


def _fake_resolver(image: object) -> str:
    """The identical deterministic resolver `test_render.py` uses, so a byte-for-byte comparison
    is not accidentally defeated by two different fake digests for the same image."""
    return "sha256:" + f"{abs(hash(image)):064x}"[:64]


def _client(config_path: Path) -> TestClient:
    app = create_app(config_path=config_path)
    # A loopback client tuple — `TestClient`'s own default (`("testclient", 50000)`) is not
    # loopback and is refused by `loopback_only_middleware`; `test_webapp_loopback.py` is what
    # proves that refusal itself, for real, so it is not re-tested by every other file's own
    # client construction here.
    return TestClient(app, client=("127.0.0.1", 51000))


@pytest.mark.parametrize(
    ("profile", "graph_store", "analytics_engine"),
    [
        ("small", "arcadedb", "duckdb"),
        ("local-lite", "arcadedb", "duckdb"),
    ],
)
def test_the_three_screens_round_trip_through_osprey_yaml_and_render_identically(
    tmp_path: Path, profile: str, graph_store: str, analytics_engine: str
) -> None:
    config_path = tmp_path / "osprey.yaml"
    config_path.write_text(_GOVERNANCE_AND_MAP, encoding="utf-8")
    client = _client(config_path)

    profile_response = client.put("/api/config", json={"profile": profile})
    assert profile_response.status_code == 200, profile_response.text

    components_response = client.put(
        "/api/config",
        json={
            "components": {
                "graph_store": graph_store,
                "analytics_engine": analytics_engine,
                "search": "opensearch",
            }
        },
    )
    assert components_response.status_code == 200, components_response.text

    models_response = client.put("/api/config", json={"models": _MODELS_ANSWER})
    assert models_response.status_code == 200, models_response.text

    # Round-trip, proven against an independently-constructed config, not against a second read
    # of the same file (which would only prove `load_config` is deterministic): the three
    # screens' own answers, written directly into a hand-built `OspreyConfig` rather than through
    # this API at all, must render to the identical bytes.
    hand_built = OspreyConfig.model_validate(
        {
            **yaml.safe_load(_GOVERNANCE_AND_MAP),
            "profile": profile,
            "components": {
                "graph_store": graph_store,
                "analytics_engine": analytics_engine,
                "search": "opensearch",
            },
            "models": _MODELS_ANSWER,
        }
    )
    via_api = load_config(config_path)
    assert via_api == hand_built

    rendered_via_api = render(via_api, resolver=_fake_resolver)
    rendered_hand_built = render(hand_built, resolver=_fake_resolver)
    assert rendered_via_api.artefacts == rendered_hand_built.artefacts


def test_small_profile_matches_stage_2_section_1s_own_fixture_byte_for_byte(tmp_path: Path) -> None:
    """The literal fixture-file comparison the queue brief names — `FIXTURE_CONFIG`'s own text,
    written to a second file this test does not touch through the API at all, rendered
    independently and diffed against the API-driven result above."""
    from tests.harness.test_render import FIXTURE_CONFIG

    fixture_path = tmp_path / "fixture-osprey.yaml"
    fixture_path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    fixture_rendered = render(load_config(fixture_path), resolver=_fake_resolver)

    config_path = tmp_path / "osprey.yaml"
    config_path.write_text(_GOVERNANCE_AND_MAP, encoding="utf-8")
    client = _client(config_path)
    assert client.put("/api/config", json={"profile": "small"}).status_code == 200
    assert (
        client.put(
            "/api/config",
            json={
                "components": {
                    "graph_store": "arcadedb",
                    "analytics_engine": "duckdb",
                    "search": "opensearch",
                    "storage": {
                        "data": "/srv/osprey/data",
                        "staging": "/srv/osprey/staging",
                        "backups": "/srv/osprey/backups",
                    },
                }
            },
        ).status_code
        == 200
    )
    assert client.put("/api/config", json={"models": _MODELS_ANSWER}).status_code == 200

    api_rendered = render(load_config(config_path), resolver=_fake_resolver)
    assert api_rendered.artefacts == fixture_rendered.artefacts


def test_cluster_profile_stub_behaviour_is_asserted_not_skipped(tmp_path: Path) -> None:
    """`06_DECISIONS.md` ADR-011: `profile: cluster` renders through a separate, not-yet-built
    renderer — `harness.render.render` already raises `ClusterRendererNotBuilt` rather than
    silently producing nothing or a wrong artefact. This test proves the API-driven round-trip
    reaches that same, real refusal — not a `pytest.skip`, which would prove nothing about
    `cluster`'s own behaviour at all.

    **`profile` and `components` submitted in one request, not two, and that is a real property
    found building this test, not a test-only convenience.** `PUT /api/config` validates the whole
    merged document on every write (`harness/webapp.py`'s own docstring), so switching `profile`
    to `cluster` alone, with `components` still at its schema default (`arcadedb`/`duckdb`), is
    itself a transiently invalid document and is refused — correctly, since nothing should ever
    land on disk in a state `§2.1`'s own filtering rule already forbids. A profile switch that
    invalidates already-stored components must be paired with a components update in the same
    write; `apps/harness`'s own Profile screen surfaces this via the consequences preview before
    either submit, rather than the API silently reconciling the two for the caller.
    """
    config_path = tmp_path / "osprey.yaml"
    config_path.write_text(_GOVERNANCE_AND_MAP, encoding="utf-8")
    client = _client(config_path)

    switch_response = client.put(
        "/api/config",
        json={
            "profile": "cluster",
            "cluster": {"hosts": [{"name": "node-1", "address": "10.0.0.1"}]},
            "components": {"graph_store": "janusgraph", "analytics_engine": "clickhouse"},
        },
    )
    assert switch_response.status_code == 200, switch_response.text

    config = load_config(config_path)
    with pytest.raises(ClusterRendererNotBuilt):
        render(config)


def test_an_invalid_component_for_the_profile_is_refused_with_a_named_field(tmp_path: Path) -> None:
    """§2.1's own filtering rule, enforced server-side even though `apps/harness`'s own screen
    also filters the options offered — the schema's own validation is the one that must hold
    regardless of what the browser happens to render (`CLAUDE.md` rule 3's own "never rely on the
    client" discipline, applied to a config screen rather than a graph query)."""
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)

    assert client.put("/api/config", json={"profile": "local-lite"}).status_code == 200
    refused = client.put(
        "/api/config",
        json={"components": {"graph_store": "janusgraph", "analytics_engine": "duckdb"}},
    )
    assert refused.status_code == 422
    assert "graph_store" in refused.text
    assert "local-lite" in refused.text


def test_get_config_returns_schema_defaults_when_no_file_exists_yet(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    assert not config_path.exists()
    client = _client(config_path)
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json()["profile"] == "local-lite"


def test_a_second_screens_answer_does_not_erase_the_firsts(tmp_path: Path) -> None:
    """§2.1's "navigable in any order" as a direct assertion: submitting Models after Profile must
    not revert Profile back to the schema's own default."""
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)

    assert client.put("/api/config", json={"profile": "small"}).status_code == 200
    assert client.put("/api/config", json={"models": _MODELS_ANSWER}).status_code == 200

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["profile"] == "small"
    assert config["models"]["hosted_fallback"] == "example-hosted"


def test_the_governance_screen_round_trips_through_osprey_yaml(tmp_path: Path) -> None:
    """`06_DECISIONS.md` ADR-049 Stage 2 §6's own exit test — "every screen round-trips its
    answers through `osprey.yaml`" — named per screen, part A's own three had this proof
    (`test_the_three_screens_round_trip_through_osprey_yaml_and_render_identically`); Governance's
    own config fields (as opposed to the exceptions panel, `test_webapp_governance_panel.py`'s own
    scope) had not, until this case. Geospatial's own equivalent is
    `test_registering_a_provider_preserves_other_sections_already_written`
    (`test_webapp_geospatial.py`); Preflight writes no section of its own, so it has none."""
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)

    answer = {
        "identity_provider": "keycloak",
        "handling_scheme": "us-criminal-intelligence",
        "ontology": "default",
        "real_data_exceptions": "config/real_data_exceptions.yaml",
    }
    response = client.put("/api/config", json={"governance": answer})
    assert response.status_code == 200
    assert response.json()["governance"] == answer

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["governance"] == answer

    # Read back through the same route a fresh page load uses, not only the file on disk.
    assert client.get("/api/config").json()["governance"] == answer
