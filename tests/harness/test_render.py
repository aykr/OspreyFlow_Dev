"""`harness/render.py` — the four artefacts `05_DEPLOYMENT.md` §2.1 names, and the two of §2.4's
five guards that live with them.

`06_DECISIONS.md` ADR-049's Stage 2 §1, whose own exit test this file is:

> Rendering a fixture `osprey.yaml` is byte-stable across runs; a hand edit to a generated file is
> reported as drift; the diff names every changed path — for each of the four artefact kinds, each
> with its own planted drift of the real generated shape.

**On "the real generated shape" (`CLAUDE.md` rule 15's second clause).** Every planted failure below
edits a file this renderer actually produced, in the place it actually produces content — not a stub
written to look like one. The distinction is the one `06_DECISIONS.md` ADR-034 §B12 records from
`licence_check.mjs`: a violation that some other branch would have caught anyway proves the test can
fail, not that it fails for the reason it claims.

**On the digest resolver.** Tests inject a deterministic one. That is a seam, not a substitute for
the behaviour under test: what is asserted is that `versions.lock` names every image the compose
file runs and that each carries a digest — a property of the renderer. Whether Docker can resolve a
digest is Docker's property, and is exercised separately by
`test_strict_mode_refuses_to_write_an_unpinned_lock`, which uses the real refusal path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness.images import ImageRef, ServiceImage
from harness.render import (
    INGEST_CONTAINER_PATH,
    ClusterRendererNotBuilt,
    MissingDockerfileError,
    RenderResult,
    UnpinnedImagesError,
    diff_for,
    find_drift,
    git_sha,
    load_config,
    render,
    service_images,
    write,
    write_config_copy,
)

from schemas.deployment import DEFAULT_PUBLIC_ORIGIN, OspreyConfig, SearchBackend

ARTEFACTS = ("compose.yaml", "deployment.env", "versions.lock", "RUNBOOK.md")

FIXTURE_CONFIG = """
profile: small
components:
  graph_store: arcadedb
  analytics_engine: duckdb
  search: opensearch
  storage:
    data: /srv/osprey/data
    staging: /srv/osprey/staging
    backups: /srv/osprey/backups
models:
  local_only: false
  hosted_fallback: example-hosted
  sendable_handling_codes: [OFFICIAL]
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


def _fake_resolver(image: ImageRef) -> str | None:
    """Deterministic and total — every image resolves, so byte-stability is a property of the
    renderer rather than of whatever this machine happens to have pulled."""
    return "sha256:" + f"{abs(hash(image)):064x}"[:64]


#: Round 07: every existing test in this file predates the build/pull split and exercises the
#: developer path — declaring `source_path` here, once, keeps every one of them testing exactly
#: what it always did (`osprey/<service>:local`, `build:` stanzas, `local-build` lock entries)
#: rather than silently becoming pull-mode tests. `test_pull_mode...` below is the one, new,
#: explicit case for the other path, against this identical fixture.
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config(tmp_path: Path) -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return loaded.model_copy(
        update={"components": loaded.components.model_copy(update={"source_path": str(REPO_ROOT)})}
    )


@pytest.fixture
def rendered(config: OspreyConfig) -> RenderResult:
    return render(config, resolver=_fake_resolver)


def test_resolved_source_label_names_how_a_digest_was_actually_obtained(
    config: OspreyConfig,
) -> None:
    """`06_DECISIONS.md` ADR-049 Stage 2 §5b: `scripts.osprey_bundle.build_bundle` resolves
    digests from the registry, not the local daemon `render`'s own default targets — measured
    directly, running the real bundle build, that the label written into `versions.lock` must
    actually agree with which resolver produced the digest. A hardcoded `"local-docker-daemon"`
    label here would mislabel a registry-resolved digest as a machine-local snapshot, exactly the
    "one thing to verify against a registry, one lie about how it was checked" gap this test
    exists to catch."""
    result = render(config, resolver=_fake_resolver, resolved_source_label="registry")
    lock = yaml.safe_load(result.artefacts["versions.lock"])

    third_party_rows = [row for row in lock["images"] if row["source"] != "local-build"]
    assert third_party_rows, "fixture renders no third-party image to check the label against"
    for row in third_party_rows:
        assert row["source"] == "registry", (
            f"{row['service']}: expected the caller-supplied label 'registry', got "
            f"{row['source']!r} — resolved_source_label is not being threaded through"
        )


def test_resolved_source_label_defaults_to_local_docker_daemon(config: OspreyConfig) -> None:
    """The unchanged default for every existing caller (`harness.apply`) that does not pass the
    parameter at all."""
    result = render(config, resolver=_fake_resolver)
    lock = yaml.safe_load(result.artefacts["versions.lock"])

    third_party_rows = [row for row in lock["images"] if row["source"] != "local-build"]
    assert all(row["source"] == "local-docker-daemon" for row in third_party_rows)


# --- The four artefacts ------------------------------------------------------


def test_all_four_artefacts_are_produced_and_none_is_trivial(rendered: RenderResult) -> None:
    """§2.1 names four. A renderer producing two of them passes a "does it render" test and fails
    the specification, which is the gap this case exists for."""
    assert set(rendered.artefacts) == set(ARTEFACTS)
    for name in ARTEFACTS:
        content = rendered.artefacts[name]
        assert content.strip(), f"{name} is empty"
        assert len(content.splitlines()) > 5, f"{name} is a stub, not an artefact"
        assert "GENERATED by" in content, f"{name} carries no do-not-edit banner"


def test_versions_lock_names_every_image_in_the_compose_file_with_a_digest(
    rendered: RenderResult,
) -> None:
    """The cross-artefact assertion, and the one that would catch a lock file that drifted from the
    compose file it is supposed to pin. Both sides are parsed from the rendered output rather than
    from the renderer's own internals, so a bug that wrote the wrong list into one of them is
    visible here."""
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])
    lock = yaml.safe_load(rendered.artefacts["versions.lock"])

    compose_images = {service["image"] for service in compose["services"].values()}
    lock_images = {f"{row['repository']}:{row['tag']}" for row in lock["images"]}

    assert compose_images == lock_images, "versions.lock and compose.yaml name different images"
    assert compose_images, "the compose file declares no images at all"
    for row in lock["images"]:
        # Two kinds of image, two kinds of identity (Stage 2 §5a). A third-party image is pinned by
        # digest; an OspreyFlow-owned one is built here and pushed nowhere, so the commit it came
        # from is what identifies it. Both must say which they are — a lock file that does not
        # record provenance cannot be told apart from one resolved against a registry.
        if row["source"] == "local-build":
            assert row["digest"] == "local-build"
            assert row["built_from_git_sha"]
        else:
            assert row["digest"].startswith("sha256:"), f"{row['repository']} has no pinned digest"
            assert row["source"] == "local-docker-daemon"


def test_pull_mode_renders_owned_images_with_no_build_stanza_and_a_locked_digest(
    config: OspreyConfig,
) -> None:
    """Round 07 — `components.source_path` undeclared (the default; not this file's own `config`
    fixture, which declares it) renders the operator path: no `build:` stanza for any service, and
    `versions.lock` locks an owned image by digest exactly like a third-party one, refusing by
    name (`UnpinnedImagesError`) if the digest cannot be resolved — never silently `local-build`
    for a service nothing here actually built. Against the identical §1 fixture every other case
    in this file renders, with only `source_path` removed."""
    pull_config = config.model_copy(
        update={"components": config.components.model_copy(update={"source_path": None})}
    )
    owned_services = {i.service for i in service_images(pull_config) if i.owned}
    assert owned_services == {"workspace", "api", "ingest"}

    with pytest.raises(UnpinnedImagesError) as excinfo:
        render(pull_config, resolver=lambda _image: None)
    assert set(excinfo.value.images) >= {
        i.image for i in service_images(pull_config) if i.service in owned_services
    }

    result = render(pull_config, resolver=_fake_resolver)
    compose = yaml.safe_load(result.artefacts["compose.yaml"])
    for service in owned_services:
        assert "build" not in compose["services"][service], (
            f"{service}: pull mode must not emit a build: stanza"
        )
        assert compose["services"][service]["image"].startswith("ghcr.io/ospreyflow/"), (
            compose["services"][service]["image"]
        )

    lock = yaml.safe_load(result.artefacts["versions.lock"])
    owned_rows = [row for row in lock["images"] if row["service"] in owned_services]
    assert len(owned_rows) == len(owned_services)
    for row in owned_rows:
        assert row["digest"].startswith("sha256:"), row
        assert row["source"] != "local-build", (
            f"{row['service']}: pull mode recorded local-build — nothing here was built"
        )


# --- git_sha / OSPREY_BUILT_FROM_SHA — round 11 -----------------------------------------------


def test_git_sha_falls_back_to_the_baked_release_sha_when_there_is_no_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real shape a pull-mode render inside the released harness image is in
    (`harness/Dockerfile`'s own header: no `.git` at all). `tmp_path` is a real directory with no
    repository either, so `git rev-parse` genuinely fails here rather than being mocked to fail."""
    monkeypatch.setenv("OSPREY_BUILT_FROM_SHA", "deadbeefcafe")
    assert git_sha(tmp_path) == "deadbeefcafe"


def test_git_sha_prefers_a_real_checkout_over_the_baked_release_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A developer's own tree always has a real `.git` — the baked value exists only for the one
    case that has none, and must never override a real answer."""
    monkeypatch.setenv("OSPREY_BUILT_FROM_SHA", "should-never-be-read")
    assert git_sha(REPO_ROOT) not in {"should-never-be-read", "unknown"}


def test_git_sha_is_unknown_with_neither_git_nor_the_baked_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OSPREY_BUILT_FROM_SHA", raising=False)
    assert git_sha(tmp_path) == "unknown"


def test_the_runbook_carries_this_deployment_s_own_paths_not_a_template(
    rendered: RenderResult,
) -> None:
    """§2.1: "`RUNBOOK.md` written for *this* deployment with the real hostnames, ports and paths
    filled in." A runbook with placeholder paths would satisfy "is non-trivial" and nothing else."""
    runbook = rendered.artefacts["RUNBOOK.md"]
    assert "/srv/osprey/data" in runbook
    assert "/srv/osprey/staging" in runbook
    assert "/srv/osprey/backups" in runbook
    assert "http://localhost:8080/admin" in runbook
    assert "config/real_data_exceptions.yaml" in runbook
    assert "deploy/RUNBOOK.md" in runbook, (
        "the generated runbook must point at §6's hand-written recovery-time runbook rather than "
        "appear to be it"
    )


def test_the_rendered_env_names_the_public_origin_as_the_only_cors_origin(
    rendered: RenderResult,
) -> None:
    """**A rendered deployment must not carry the Vite development origin** (round 13b).

    Found by round 13's closing pass: the rendered `compose.yaml` set no `CORS_ALLOWED_ORIGINS`
    at all, so a deployed Conduit fell back to `services/api/app.py`'s own default —
    `http://localhost:5173`, the origin a developer's `npm run dev` serves the Glass from. The
    deployed Glass never noticed, because it reaches the Conduit same-origin through the
    workspace's nginx proxy and CORS does not apply to it; nothing else was looking.

    The value is `network.public_origin`, the field ADR-050 objection 2 already added for the
    OIDC redirect — the origin a browser genuinely uses to reach this deployment. Asserting it is
    *the only* one, not merely present: a list that happens to contain the right origin beside
    the wrong one is the same defect wearing a hat."""
    env = rendered.artefacts["deployment.env"]

    lines = [ln for ln in env.splitlines() if ln.startswith("CORS_ALLOWED_ORIGINS=")]
    assert lines, (
        "the rendered env sets no CORS_ALLOWED_ORIGINS, so the Conduit falls back to its own "
        "development default — see this test's docstring"
    )
    assert len(lines) == 1, lines

    value = lines[0].split("=", 1)[1]
    assert value == DEFAULT_PUBLIC_ORIGIN, (
        f"CORS_ALLOWED_ORIGINS is {value!r}; it must be exactly the deployment's own public "
        f"origin ({DEFAULT_PUBLIC_ORIGIN!r}) and nothing else"
    )
    assert "5173" not in value, f"the Vite development origin is in a rendered deployment: {value}"


def test_the_env_file_contains_no_secret_only_references(rendered: RenderResult) -> None:
    """§2.5: "It never sees a secret. Credentials are entered as references — an environment
    variable name or a secret-manager path. The harness records where to look, never what it
    found." Asserted as an absence, which is the only way this one can be tested."""
    env = rendered.artefacts["deployment.env"]
    for banned in ("PASSWORD=", "SECRET=", "TOKEN=", "playwithdata123"):
        assert banned not in env, f"the rendered env file contains {banned!r}"


# --- Byte-stability ----------------------------------------------------------


def test_rendering_the_same_config_twice_is_byte_identical(config: OspreyConfig) -> None:
    first = render(config, resolver=_fake_resolver)
    second = render(config, resolver=_fake_resolver)
    assert first.artefacts == second.artefacts


def test_byte_stability_holds_through_a_write_and_reread(
    config: OspreyConfig, tmp_path: Path
) -> None:
    """Stability in memory is not stability on disk — an encoding or newline difference at write
    time would pass the case above and still produce a file that never stops drifting."""
    out = tmp_path / "out"
    write(render(config, resolver=_fake_resolver), out)
    assert find_drift(render(config, resolver=_fake_resolver), out) == []


# --- §2.4 drift detection ----------------------------------------------------


@pytest.mark.parametrize("artefact", ARTEFACTS)
def test_a_hand_edit_to_each_generated_file_is_reported_as_drift_naming_that_path(
    config: OspreyConfig, tmp_path: Path, artefact: str
) -> None:
    """Red-then-green, per artefact, with the planted change taking the real shape: a real
    generated file, written by this renderer, edited the way a person would edit it — a line
    appended to the end. `find_drift` must name that path and no other.

    The `== []` assertion before the edit is what stops this passing vacuously: without it, a
    `find_drift` that reported every path always would satisfy the assertion after the edit.
    """
    out = tmp_path / "out"
    result = render(config, resolver=_fake_resolver)
    write(result, out)
    assert find_drift(result, out) == [], "freshly written output should not be drifted"

    target = out / artefact
    target.write_text(
        target.read_text(encoding="utf-8") + "\n# a person edited this by hand\n", encoding="utf-8"
    )

    assert find_drift(result, out) == [artefact]


@pytest.mark.parametrize("artefact", ARTEFACTS)
def test_a_deleted_generated_file_is_drift_too(
    config: OspreyConfig, tmp_path: Path, artefact: str
) -> None:
    """A missing artefact is as much a divergence between `osprey.yaml` and the deployment as an
    edited one, and is the easier of the two to miss: a drift check written as "compare the files
    that exist" reports nothing at all here."""
    out = tmp_path / "out"
    result = render(config, resolver=_fake_resolver)
    write(result, out)
    (out / artefact).unlink()

    assert find_drift(result, out) == [artefact]


# --- §2.4 change preview -----------------------------------------------------


def test_a_planted_change_produces_a_diff_naming_exactly_the_changed_path(
    config: OspreyConfig, tmp_path: Path
) -> None:
    """The change preview, with a real config change rather than an edited file: flipping the
    search backend to §3's reduced variant drops OpenSearch, so the compose file, the env file and
    the runbook change and `versions.lock` changes with them — while a diff against *unchanged*
    output is empty. Asserting the empty case first is what makes the second assertion mean
    something."""
    out = tmp_path / "out"
    write(render(config, resolver=_fake_resolver), out)
    assert diff_for(render(config, resolver=_fake_resolver), out) == {}

    reduced = config.model_copy(
        update={
            "components": config.components.model_copy(
                update={"search": SearchBackend.POSTGRES_FULLTEXT}
            )
        }
    )
    diffs = diff_for(render(reduced, resolver=_fake_resolver), out)

    assert set(diffs) == {"compose.yaml", "deployment.env", "versions.lock", "RUNBOOK.md"}
    assert "opensearch" in diffs["compose.yaml"]
    assert "-" in diffs["compose.yaml"], "a removal should show as a removed line"


def test_the_diff_names_only_the_path_that_actually_changed(
    config: OspreyConfig, tmp_path: Path
) -> None:
    """The sharper half of the preview: a change confined to one artefact must not report the other
    three. Planted on a real generated file, in its own real content."""
    out = tmp_path / "out"
    result = render(config, resolver=_fake_resolver)
    write(result, out)

    target = out / "RUNBOOK.md"
    target.write_text(target.read_text(encoding="utf-8").replace("/srv/osprey/data", "/tmp/wrong"))

    diffs = diff_for(result, out)
    assert set(diffs) == {"RUNBOOK.md"}
    assert "/tmp/wrong" in diffs["RUNBOOK.md"]
    assert "/srv/osprey/data" in diffs["RUNBOOK.md"]


# --- Profiles, the reduced variant, and the cluster stub ---------------------


def test_the_reduced_variant_drops_opensearch_from_the_rendered_stack(
    config: OspreyConfig,
) -> None:
    """Stage 2 §1's own half of `05_DEPLOYMENT.md` §3: able to render the reduced variant when
    asked. Offering it is Stage 2 §2's job and is not tested here."""
    reduced = config.model_copy(
        update={
            "components": config.components.model_copy(
                update={"search": SearchBackend.POSTGRES_FULLTEXT}
            )
        }
    )
    full_services = yaml.safe_load(
        render(config, resolver=_fake_resolver).artefacts["compose.yaml"]
    )
    reduced_services = yaml.safe_load(
        render(reduced, resolver=_fake_resolver).artefacts["compose.yaml"]
    )

    assert "opensearch" in full_services["services"]
    assert "opensearch" not in reduced_services["services"]
    assert "postgres" in reduced_services["services"], "the fallback's own backend must still run"
    assert "reduced variant" in render(reduced, resolver=_fake_resolver).artefacts["RUNBOOK.md"]


def test_local_lite_and_small_both_render() -> None:
    """ADR-011: Compose for both. Rendered separately so a profile-specific crash is not hidden by
    the other profile passing."""
    for profile in ("local-lite", "small"):
        config = OspreyConfig.model_validate({"profile": profile})
        result = render(config, resolver=_fake_resolver)
        assert set(result.artefacts) == set(ARTEFACTS)
        assert f"osprey-{profile}" in result.artefacts["compose.yaml"]


def test_the_cluster_profile_fails_loudly_rather_than_rendering_compose() -> None:
    """ADR-011: "Compose for `local-lite` and `small`; generated Kubernetes manifests for
    `cluster`" — a different renderer, not a toggle. Not built in Stage 2 §1, and a silent compose
    render would be the worse failure."""
    config = OspreyConfig.model_validate(
        {"profile": "cluster", "cluster": {"hosts": [{"name": "a", "address": "10.0.0.1"}]}}
    )
    with pytest.raises(ClusterRendererNotBuilt, match="not built in Stage 2"):
        render(config, resolver=_fake_resolver)


# --- The digest refusal ------------------------------------------------------


def test_strict_mode_refuses_to_write_an_unpinned_lock_and_names_the_images(
    config: OspreyConfig,
) -> None:
    """§2.1 requires "`versions.lock` with every image digest pinned" and §7 repeats it. A lock file
    full of `unresolved` would satisfy neither while looking like it did, so the renderer refuses
    and names what it could not resolve — the same "named refusal, not a silent partial" shape
    `scripts/osprey_bundle.py` already uses for a non-redistributable provider."""
    with pytest.raises(UnpinnedImagesError) as raised:
        render(config, resolver=lambda _image: None)

    # Owned images are never in the refusal: they are not resolved against a registry at all, so
    # there is no digest for them to be missing.
    expected = {image.image for image in service_images(config) if not image.owned}
    assert set(raised.value.images) == expected
    for image in expected:
        assert image in str(raised.value)


def test_allow_unpinned_marks_them_explicitly_rather_than_omitting_them(
    config: OspreyConfig,
) -> None:
    """The escape hatch must not quietly shrink the lock file: an image with no digest still
    appears, marked `unresolved` in that word, so nothing downstream reads a shorter list as a
    complete one."""
    result = render(config, resolver=lambda _image: None, allow_unpinned=True)
    lock = yaml.safe_load(result.artefacts["versions.lock"])

    assert len(lock["images"]) == len(service_images(config))
    third_party = [row for row in lock["images"] if row["source"] != "local-build"]
    assert third_party, "this fixture must declare at least one third-party image"
    assert {row["digest"] for row in third_party} == {"unresolved"}
    assert {row["source"] for row in third_party} == {"unresolved"}


def test_a_partially_resolvable_set_still_refuses_and_names_only_the_missing_ones(
    config: OspreyConfig,
) -> None:
    """The realistic case, and the one a pass/fail-on-all check would get wrong: some images pulled
    locally, some not. The refusal must name the unresolved ones only."""
    images = [image.image for image in service_images(config) if not image.owned]
    missing = {images[0], images[-1]}

    with pytest.raises(UnpinnedImagesError) as raised:
        render(config, resolver=lambda image: None if image in missing else _fake_resolver(image))

    assert set(raised.value.images) == missing


# --- Stage 2 §5a: owned images build, third-party images pull --------------------


def test_owned_services_render_a_build_context_and_third_party_ones_do_not(
    rendered: RenderResult,
) -> None:
    """The distinction Stage 2 §5a exists for. No registry publishes `ghcr.io/ospreyflow/api`, so
    a compose file naming one renders a stack that cannot start; owned services build from this
    repository instead. Third-party images keep their pinned upstream references, because those
    registries do publish them and a `build:` for ArcadeDB would be absurd."""
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])
    services = compose["services"]

    for owned in ("workspace", "api", "ingest"):
        assert "build" in services[owned], f"{owned} is ours and must build from the tree"
        assert services[owned]["build"]["dockerfile"].endswith("Dockerfile")
        assert services[owned]["image"].startswith("osprey/"), (
            f"{owned} must carry a local tag so versions.lock can name it and `up` need not rebuild"
        )

    for third_party in ("arcadedb", "postgres", "valkey", "minio", "keycloak"):
        assert "build" not in services[third_party], f"{third_party} is not ours to build"
        assert "/" in services[third_party]["image"] or ":" in services[third_party]["image"]


def test_every_rendered_build_context_points_at_a_dockerfile_that_exists(
    rendered: RenderResult,
) -> None:
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])
    for name, spec in compose["services"].items():
        if "build" not in spec:
            continue
        dockerfile = Path(__file__).resolve().parents[2] / spec["build"]["dockerfile"]
        assert dockerfile.is_file(), f"{name} builds from {dockerfile}, which does not exist"


def test_an_owned_service_without_a_dockerfile_fails_the_render_by_name(
    config: OspreyConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red-then-green for the refusal. A `build:` stanza pointing at a missing Dockerfile would
    otherwise surface as Docker's own error several steps later, during `compose build`, with a
    message that names a path rather than a service."""
    import harness.render as render_module

    real = render_module.service_images

    def with_a_phantom_service(cfg):
        images = list(real(cfg))
        images.append(
            ServiceImage(
                "phantom",
                "osprey/phantom:local",
                build_context=".",
                dockerfile="services/phantom/Dockerfile",
            )
        )
        return images

    monkeypatch.setattr(render_module, "service_images", with_a_phantom_service)

    with pytest.raises(MissingDockerfileError, match="phantom"):
        render_module.render(config, resolver=_fake_resolver)


def test_owned_images_are_recorded_as_local_builds_with_the_commit_they_came_from(
    rendered: RenderResult,
) -> None:
    """An image built here and pushed nowhere has no registry digest and never will until Stage 2
    §5b publishes one. What identifies it is the commit. Recording a digest the local daemon
    happens to hold for an overwritable tag would look like a pin and be worth nothing."""
    rows = yaml.safe_load(rendered.artefacts["versions.lock"])["images"]
    lock = {row["service"]: row for row in rows}

    for owned in ("workspace", "api", "ingest"):
        row = lock[owned]
        assert row["source"] == "local-build"
        assert row["digest"] == "local-build"
        assert row["built_from_git_sha"], f"{owned} records no commit"
        assert row["dockerfile"].endswith("Dockerfile")

    assert lock["arcadedb"]["source"] == "local-docker-daemon"
    assert "built_from_git_sha" not in lock["arcadedb"]


def test_every_published_port_is_overridable_with_the_spec_s_own_default(
    rendered: RenderResult,
) -> None:
    """Preflight found 8000 held by an unrelated container on a real machine. A deployment that
    cannot move its own ports is one an operator has to fight — but the defaults stay the
    specification's, so overriding nothing matches `05_DEPLOYMENT.md` §3 exactly.

    The Conduit's own port is covered by `test_the_conduit_is_not_published_by_default` below
    rather than here: since 25 September 2026 it is not published unless asked for, so "every
    published port" no longer includes it by default."""
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])
    env = rendered.artefacts["deployment.env"]

    assert compose["services"]["workspace"]["ports"] == ["${OSPREY_WORKSPACE_PORT:-8080}:8080"]
    assert "OSPREY_WORKSPACE_PORT=8080" in env
    assert "OSPREY_API_PORT=8000" in env


def test_the_conduit_is_not_published_by_default_and_is_when_asked_for() -> None:
    """`05_DEPLOYMENT.md` §2.6 item 1, the owner's decision of 25 September 2026.

    The workspace's own image proxies `/v1` and the delta WebSocket to the Conduit on the internal
    network, so publishing the Conduit's port buys the Glass nothing and widens the exposed surface
    by a whole tier. §7's "only the workspace and the Conduit are exposed" is now satisfied by one
    published port, not two.

    **Both directions asserted.** A test that only checked the default would pass against a
    renderer that had simply stopped publishing the port at all, and `network.expose_conduit` would
    then be a setting that does nothing — which is the shape `CLAUDE.md` rule 12 keeps naming.
    """
    from schemas.deployment import NetworkConfig

    closed = yaml.safe_load(render(OspreyConfig(), allow_unpinned=True).artefacts["compose.yaml"])
    assert "ports" not in closed["services"]["api"], (
        "the Conduit is published by default — the Glass does not need it and §7 does not want it"
    )
    assert closed["services"]["workspace"]["ports"], "the workspace must still be reachable"

    opened = yaml.safe_load(
        render(
            OspreyConfig(network=NetworkConfig(expose_conduit=True)), allow_unpinned=True
        ).artefacts["compose.yaml"]
    )
    assert opened["services"]["api"]["ports"] == ["${OSPREY_API_PORT:-8000}:8000"], (
        "network.expose_conduit: true did not publish the Conduit, so the option does nothing"
    )


def test_the_apply_profile_flag_is_validated_rather_than_assigned_raw() -> None:
    """`--profile` reached `model_copy(update=...)`, which does not validate, so a bare string was
    assigned to a field typed as an enum and failed several lines later on `.value` — with a
    message naming neither the flag nor the profile. Found running the exit test from a fresh
    clone. An unknown profile must fail at the flag, by name."""
    import harness.apply as apply_module

    from schemas.deployment import Profile

    assert Profile("local-lite") is Profile.LOCAL_LITE
    with pytest.raises(ValueError, match="not-a-profile"):
        Profile("not-a-profile")

    source = Path(apply_module.__file__).read_text(encoding="utf-8")
    assert "Profile(args.profile)" in source, (
        "the profile flag must be coerced through the enum, or an invalid one fails late and "
        "unhelpfully"
    )


def test_the_build_context_resolves_to_the_repository_root_from_the_output_directory(
    rendered: RenderResult, tmp_path: Path
) -> None:
    """A compose `build.context` is relative to the **compose file**, not to the working directory.
    Rendered output lives three levels down at `deploy/generated/<profile>/`, so a context of `.`
    points at the output directory — which has no `services/` — and the build fails with
    `lstat .../deploy/generated/local-lite/services: no such file or directory`, naming the symptom
    and not the cause. Found running the golden path from a fresh clone.
    """
    out = tmp_path / "deploy" / "generated" / "local-lite"
    write(rendered, out)
    compose = yaml.safe_load((out / "compose.yaml").read_text(encoding="utf-8"))

    for name, spec in compose["services"].items():
        if "build" not in spec:
            continue
        context = (out / spec["build"]["context"]).resolve()
        assert context == tmp_path.resolve(), (
            f"{name}'s build context resolves to {context}, not the repository root — compose "
            "resolves it relative to the compose file"
        )
        assert (context / spec["build"]["dockerfile"]).parent.name in {"api", "ingest", "workspace"}


def test_the_rendered_realm_carries_only_fields_keycloak_defines() -> None:
    """Keycloak's realm import refuses any unrecognised field outright — the whole import fails and
    the container never becomes healthy. A note-to-self left in the document
    (`ospreyRequiredServiceAccountRoles`) did exactly that, and the error named the field rather
    than the harness that wrote it. Anything this harness needs to remember lives in a module
    constant, not in the realm."""
    from harness.realm import REQUIRED_SERVICE_ACCOUNT_ROLES, render_realm

    realm = render_realm(OspreyConfig.model_validate({}))

    # `unmanagedAttributePolicy` is deliberately absent: it belongs to the user-profile
    # endpoint, and including it makes the whole realm import fail.
    known = {"realm", "enabled", "clients", "users"}
    assert set(realm) <= known, (
        f"unexpected top-level key(s) in the realm document: {sorted(set(realm) - known)}"
    )
    assert REQUIRED_SERVICE_ACCOUNT_ROLES == ("impersonation", "view-users")
    assert "unmanagedAttributePolicy" not in realm


def test_the_batch_loader_is_not_started_by_up(rendered: RenderResult) -> None:
    """`docker compose up --wait` reads any non-zero exit as a failed start, and the batch loader
    takes required arguments and exits 2 without them — so a job behaving exactly as designed
    failed the whole deploy. A compose profile keeps it out of `up` while leaving it runnable on
    demand, which is what a run-once job is."""
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])

    assert compose["services"]["ingest"]["profiles"] == ["batch"]
    assert compose["services"]["ingest"]["restart"] == "no"
    for always_on in ("api", "workspace", "arcadedb", "keycloak"):
        assert "profiles" not in compose["services"][always_on], (
            f"{always_on} must start with `up`; a profile would silently exclude it"
        )


def test_every_declared_volume_is_mounted_by_some_service(rendered: RenderResult) -> None:
    """A declared volume no service mounts is configuration that reads as correct and does nothing.

    **Found, not anticipated.** `osprey-data` and `osprey-staging` were emitted under the compose
    file's `volumes:` key from the first render and mounted by nothing, so the Conduit's analytics
    DuckDB lived in the container's own layer: every seeded event was discarded by `docker compose
    down`, and Stage 2 §4's backup would have found no file to copy. Nothing failed — the stack came
    up healthy, the deploy reported green, and the loss only appears the second time you look for
    data you put in.

    This is `CLAUDE.md` rule 12's question answered for the sentence "the deployment's storage roots
    are volumes": the test that would fail is this one. The planted violation is the real shape —
    a volume declared and left unmounted, exactly as it was.
    """
    document = yaml.safe_load(rendered.artefacts["compose.yaml"])
    declared = set(document["volumes"])
    mounted = {
        mount.split(":", 1)[0]
        for service in document["services"].values()
        for mount in service.get("volumes", [])
    }
    unmounted = declared - mounted
    assert not unmounted, (
        f"declared but mounted by no service: {sorted(unmounted)} — a named volume that nothing "
        "mounts stores nothing, and the data an operator believes is persisted is not"
    )


def test_keycloaks_own_database_survives_a_restart(rendered: RenderResult) -> None:
    """**Round 13cb.** Keycloak's only mount was the read-only realm import, so its database lived
    in the container layer and died with `docker compose down`.

    The realm and its users come back from that import; the `--demo-analyst` **password** does
    not, because `harness/apply.py` sets it afterwards through the admin API and nothing re-runs
    that on a restart. The symptom is a deployment that presents its login form and then refuses
    the operator's own credentials, with nothing naming the cause.

    **Found, not anticipated.** Round 13cb brought an earlier deployment back up to use as a
    red baseline and the *existing* over-the-wire suite failed at sign-in — a deployment that had
    passed 8/8 an hour before. Owner ruling R8's bar is that the product can be demonstrated on a
    rendered deployment; one that cannot be stopped and started does not clear it.

    Asserted as "some volume covers the data directory", not as a literal path, so moving the
    mount is allowed and *removing* it is not.
    """
    document = yaml.safe_load(rendered.artefacts["compose.yaml"])
    keycloak = document["services"]["keycloak"]

    named_mounts = [
        mount
        for mount in keycloak.get("volumes", [])
        if ":" in mount and not mount.startswith(".") and not mount.startswith("/")
    ]
    covering = [m for m in named_mounts if m.split(":")[1].startswith("/opt/keycloak/data")]
    assert covering, (
        "nothing persists Keycloak's data directory, so its database dies with the container and "
        "the demo analyst's password — set after the realm import — is lost on every restart. "
        f"keycloak volumes: {keycloak.get('volumes')}"
    )

    declared = set(document.get("volumes") or {})
    for mount in covering:
        assert mount.split(":")[0] in declared, (
            f"{mount} names a volume the compose file never declares"
        )

    # The realm import is a bind *inside* that directory; a volume over the parent would shadow
    # it and the realm would never import. This is why the mount is at `.../data/h2`.
    imports = [m for m in keycloak.get("volumes", []) if "import/realm.json" in m]
    assert imports, "the realm import mount has gone"
    for mount in covering:
        assert mount.split(":")[1] != "/opt/keycloak/data", (
            "a volume over /opt/keycloak/data shadows the realm.json bind mount inside it, so "
            "the realm would never import"
        )


def test_the_conduit_is_pointed_at_a_persistent_recipe_repository(
    rendered: RenderResult, config: OspreyConfig
) -> None:
    """**Round 13bf.** `09_INGEST_STUDIO.md` §6: "Publishing writes the recipe to version control,
    not only to the database. The studio is the editor; the repository is the record."

    The Conduit's own default repository root is `.parents[2]` of its own source file — correct on
    a developer's host, and inside the container `/app`, the image's code directory: not a git
    repository, and rebuilt on every deploy. So the record was written where nothing could read it
    back, if it could be written at all. Found walking Publish over the wire, where it surfaced as
    a bare 500.

    Rule 12, named: this is what fails if the variable is dropped. It asserts the path is *under*
    a mounted root rather than merely set, because a repository root outside every volume would
    satisfy "the variable is present" and still lose every published recipe on the next deploy —
    which is the same shape as this file's own
    `test_every_declared_volume_is_mounted_by_some_service`, and it is the same defect twice.
    """
    document = yaml.safe_load(rendered.artefacts["compose.yaml"])
    api = document["services"]["api"]

    root = api.get("environment", {}).get("OSPREY_RECIPE_REPO_ROOT")
    assert root, (
        "the Conduit is not told where to commit published recipes, so it falls back to /app "
        "inside the image — not a repository, and discarded on every rebuild"
    )

    mount_targets = {
        mount.split(":")[1] for mount in api.get("volumes", []) if mount.count(":") >= 1
    }
    assert any(root == target or root.startswith(f"{target}/") for target in mount_targets), (
        f"the recipe repository {root!r} is not under any path the api service mounts "
        f"({sorted(mount_targets)}), so every published recipe is lost on the next deploy"
    )


def test_arcadedb_gets_an_explicit_heap_rather_than_jvm_ergonomics(rendered: RenderResult) -> None:
    """The graph store's heap is a rendered value, not whatever the JVM infers from the container.

    **Found running the seeded golden path.** Unset, this image's heap is about a quarter of the
    memory Docker exposes — around 2GiB here — and the HMP fixture's graph side does not fit. The
    seed died on ArcadeDB error 500 "Error in execution in lock"; the `OutOfMemoryError` was only
    in the server's own log. `deploy/compose/dev.yaml` had already measured this and raised its
    heap in Phase 5, and the renderer did not carry the value across, so a rendered deployment was
    worse-configured than the dev stack it replaces on a number this repository had already paid
    for once.

    `CLAUDE.md` rule 12's question, answered: the invariant is "the rendered graph store gets an
    explicit heap", and this is the case that fails when it does not. The planted violation is the
    real shape — the key absent from the service's environment, as it was.
    """
    document = yaml.safe_load(rendered.artefacts["compose.yaml"])
    environment = document["services"]["arcadedb"]["environment"]

    assert "ARCADEDB_OPTS_MEMORY" in environment, (
        "ArcadeDB's heap is left to JVM container ergonomics — about a quarter of the VM, which "
        "the HMP fixture does not fit in, and which fails as a lock error rather than as an "
        "out-of-memory error"
    )
    assert "-Xmx" in environment["ARCADEDB_OPTS_MEMORY"], (
        "the heap setting names no maximum, so it caps nothing"
    )
    assert "OSPREY_ARCADEDB_HEAP=" in rendered.artefacts["deployment.env"], (
        "the heap is not tunable from the deployment's own environment file"
    )


def test_the_conduits_config_mount_is_relative_to_the_compose_file_not_the_repository(
    rendered: RenderResult,
) -> None:
    """`ADR-049` Stage 2 §5b's own real `--images` install-from-bundle exit test found this, not a
    fabricated fixture: `docker compose up --wait` failed with `IsADirectoryError: ... 'osprey.
    yaml'` because Docker silently creates an empty directory for a bind-mount source that does not
    exist, and the old mount (`../../../osprey.yaml`, `BUILD_CONTEXT_FROM_OUTPUT_DIR` reused from
    the *build* context) assumed every deployment is rendered exactly three directories below the
    checkout that renders it — true of this repository's own `deploy/generated/<profile>/`, false
    of a bundle recipient's own `--out-root`, which has no such tree at all.

    The planted violation is the real shape: the mount source is the string a bundle-install
    directory cannot satisfy, not a hand-picked example of "a relative path"."""
    document = yaml.safe_load(rendered.artefacts["compose.yaml"])
    volumes = document["services"]["api"]["volumes"]
    config_mount = next(v for v in volumes if v.endswith(":/app/osprey.yaml:ro"))

    assert config_mount == "./osprey.yaml:/app/osprey.yaml:ro", (
        f"got {config_mount!r} — a mount source rooted outside the rendered output directory "
        "cannot be satisfied by an install that has no repository checkout at all"
    )


def test_write_config_copy_places_a_readable_osprey_yaml_beside_the_rendered_compose_file(
    tmp_path: Path,
) -> None:
    """The other half of the same fix: `_render_compose`'s `./osprey.yaml` mount only resolves if
    something actually places a real `osprey.yaml` next to `compose.yaml`. Both CLI entry points
    (`harness.render`'s own `main`, `harness.apply`) call this — proven here directly, not only by
    inference from reading the source, since `CLAUDE.md` rule 12 asks for the test that would fail
    if this step were ever dropped from one of the two."""
    source = tmp_path / "source-dir" / "osprey.yaml"
    source.parent.mkdir()
    source.write_text(FIXTURE_CONFIG, encoding="utf-8")
    out_dir = tmp_path / "an-arbitrary-install-directory" / "local-lite"

    target = write_config_copy(source, out_dir)

    assert target == out_dir / "osprey.yaml"
    assert target.read_text(encoding="utf-8") == FIXTURE_CONFIG


def test_load_config_of_a_file_that_does_not_exist_is_schema_defaults_not_a_crash(
    tmp_path: Path,
) -> None:
    """Found 26 September 2026, Stage 2 §6 part C, running the real CLI against a fresh clone with
    no `osprey.yaml` written yet: `path.read_text()` raised `FileNotFoundError` uncaught, out of
    both `python -m harness.render` and `python -m harness.apply`. This function's own docstring
    already claimed "an empty file is an empty config, not a crash" — true, and narrower than a
    reader would assume: a missing file is the same case, not a different one."""
    missing = tmp_path / "does-not-exist" / "osprey.yaml"
    assert not missing.exists()
    assert load_config(missing) == OspreyConfig()


def test_write_config_copy_of_a_missing_source_writes_the_schema_defaults(tmp_path: Path) -> None:
    """The other half of the same finding: an operator (or the Preflight screen's own `Generate`)
    who has accepted every default and never explicitly saved anything has no `osprey.yaml` to
    copy — a real, valid state, not an error, and the copy `_render_compose`'s own mount needs
    present must still be real, parseable YAML, not absent."""
    source = tmp_path / "never-written" / "osprey.yaml"
    out_dir = tmp_path / "generated" / "local-lite"

    target = write_config_copy(source, out_dir)

    assert target.is_file()
    assert OspreyConfig.model_validate(yaml.safe_load(target.read_text())) == OspreyConfig()


# --- Owner ruling R6, 27 September 2026: the ingest root ------------------------------------------
#
# Round 13b's over-the-wire exit test found that a rendered deployment gives an analyst no route
# by which to supply a source file: `POST /v1/ingest/recipes` takes a `source_location` the
# Conduit's own container must be able to read, and nothing was mounted there. Eight acceptance
# rows were unreachable through the analyst's own door in consequence. These are the cases that
# fail if that regresses.


def test_the_ingest_root_is_mounted_read_only_into_the_conduit_for_every_rendered_profile() -> None:
    """**Read-only is the assertion, not an implementation detail.** The Conduit never writes to
    this root — an operator, or whatever moves evidence onto the host, owns its contents — and a
    writable mount would let a compromised Conduit modify the evidence it is reading. `:ro` is the
    only thing standing there, so it is asserted by name rather than inferred from "a volume
    exists".

    **"Every profile" means every profile this renderer emits compose for.** `cluster` is a
    different renderer (ADR-011, `ClusterRendererNotBuilt`) and is deliberately not asserted here
    rather than silently skipped — when that renderer is built, its own equivalent case is part of
    building it.
    """
    from schemas.deployment import ComponentsConfig, Profile, StorageRoots

    for profile in (Profile.LOCAL_LITE, Profile.SMALL):
        config = OspreyConfig(profile=profile)
        compose = yaml.safe_load(render(config, allow_unpinned=True).artefacts["compose.yaml"])
        api = compose["services"]["api"]
        assert f"{config.components.storage.ingest}:{INGEST_CONTAINER_PATH}:ro" in api["volumes"], (
            f"{profile.value}: the ingest root is not mounted read-only into the Conduit — "
            f"{api.get('volumes')}"
        )

    # A moved root moves the mount's host side and nothing else: the container path is fixed, which
    # is what lets the Conduit and this renderer agree on it without a second setting.
    moved = OspreyConfig(
        components=ComponentsConfig(storage=StorageRoots(ingest="/mnt/evidence/incoming"))
    )
    api = yaml.safe_load(render(moved, allow_unpinned=True).artefacts["compose.yaml"])["services"][
        "api"
    ]
    assert f"/mnt/evidence/incoming:{INGEST_CONTAINER_PATH}:ro" in api["volumes"], api["volumes"]


def test_the_conduit_is_told_where_the_ingest_root_is_mounted() -> None:
    """The container path is fixed, but the Conduit still has to be told it: the source-file route
    enumerates exactly this directory and refuses anything outside it, and a path hard-coded in
    two places is how those two drift apart."""
    env = render(OspreyConfig(), allow_unpinned=True).artefacts["deployment.env"]
    assert f"OSPREY_INGEST_ROOT={INGEST_CONTAINER_PATH}" in env, env
