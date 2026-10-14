"""`harness/preflight/` — ADR-049's Stage 2 §2.

**Every planted failure below is the shape the check actually reads** (`CLAUDE.md` rule 15's second
clause). A real socket bound on a port taken out of a real rendered compose file; a real `file://`
tile URL in a real rendered config; a real system-Python interpreter path; a real second process
holding the DuckDB file. Not one stubbed return value among them.

**Where a seam exists, it is because the machine cannot be put into the state.** Total RAM and free
disk cannot be lowered by a test, so `PreflightContext` reaches both through a probe whose return
shape is exactly the real one's (an integer of bytes; `shutil.disk_usage`'s triple). `localhost`
resolving to IPv6 only would mean editing `/etc/hosts`, so that one case patches `getaddrinfo` —
which is still the shape the check reads, and the passing case runs against this machine's real
resolver. Each of those three is called out at its own test rather than left for a reader to notice.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from harness.preflight import (
    basemap,
    bind_address,
    cluster,
    disk,
    duckdb_lock,
    memory,
    oidc_audience,
    ports,
    runtime,
)
from harness.preflight import interpreter as interpreter_check
from harness.preflight.__main__ import main, run, run_streaming
from harness.preflight.context import PreflightContext
from harness.preflight.reduced import accept, offer_for
from harness.preflight.result import CheckResult, Status
from harness.realm import CONDUIT_CLIENT_ID
from harness.render import render, write

from schemas.deployment import OspreyConfig, SearchBackend

GIB = 1024**3

FIXTURE_CONFIG = """
profile: local-lite
components:
  storage:
    data: /srv/osprey/data
    staging: /srv/osprey/staging
    backups: /srv/osprey/backups
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


@pytest.fixture
def config() -> OspreyConfig:
    return OspreyConfig.model_validate(yaml.safe_load(FIXTURE_CONFIG))


@pytest.fixture
def rendered_dir(config: OspreyConfig, tmp_path: Path) -> Path:
    """A **real** render, written to disk. Every check that reads the rendered deployment reads
    this, so a planted failure lands in a file the renderer actually produced."""
    out = tmp_path / "generated" / config.profile.value
    write(render(config, resolver=lambda _i: "sha256:" + "0" * 64), out)
    return out


@pytest.fixture
def context(config: OspreyConfig, rendered_dir: Path) -> PreflightContext:
    """`memory_probe`/`disk_probe`/`host_memory_probe`/`host_disk_probe` default to fast,
    deterministic, above-every-floor fakes here — round 10's own real defaults shell out to a real
    `docker`, and a test with no reason to care about memory or disk specifically (the CLI/gate
    mechanics tests below, e.g.) should not silently gain a real, slow, external dependency just by
    using this fixture. Every memory/disk-specific test below overrides one or more explicitly, the
    same seam this module's own docstring already names."""
    return PreflightContext(
        config=config,
        out_dir=rendered_dir,
        memory_probe=lambda: 32 * GIB,
        disk_probe=lambda _path: (100 * GIB, 0, 100 * GIB),
        host_memory_probe=lambda: 32 * GIB,
        host_disk_probe=lambda _path: (100 * GIB, 0, 100 * GIB),
    )


# --- (a) memory ---------------------------------------------------------------
# Seam, named: this machine's RAM cannot be lowered by a test. The probe returns an integer of
# bytes, which is exactly what the real one returns.


def test_memory_below_the_floor_fails_and_says_what_to_do(context: PreflightContext) -> None:
    context.memory_probe = lambda: 8 * GIB
    result = memory.check(context)

    assert result.status is Status.FAIL
    assert "8.0GiB" in result.what_is_wrong and "16.0GiB" in result.what_is_wrong
    assert "reduced variant" in result.what_to_do
    assert result.what_to_do, "05 §2.1 requires a remedy, not only a diagnosis"


def test_memory_at_the_floor_passes(context: PreflightContext) -> None:
    context.memory_probe = lambda: 16 * GIB
    assert memory.check(context).status is Status.PASS


def test_memory_is_skipped_not_passed_when_it_cannot_be_read(context: PreflightContext) -> None:
    """A platform without the sysconf keys must not report `pass`. A check that could not run is
    not evidence the thing it checks is fine."""

    def unreadable() -> int:
        raise ValueError("SC_PHYS_PAGES unavailable")

    context.memory_probe = unreadable
    result = memory.check(context)
    assert result.status is Status.SKIP
    assert "not checked" in (result.what_is_wrong + result.what_to_do).lower()


# --- (b) disk -----------------------------------------------------------------


def test_disk_below_the_projection_fails(context: PreflightContext, tmp_path: Path) -> None:
    """Planted for real on the free-space side: a real path, a real `shutil.disk_usage` reading,
    and a projection set above it. `disk_probe` is pointed at the real reader explicitly — round
    10's own default probes the container runtime, not `tmp_path`, which is exactly the point of
    that change, so a test of *this check's own logic* (the projection comparison, the message)
    needs a probe that actually reads `tmp_path` for real, the same way `host_disk_probe` does."""
    context.disk_probe = shutil.disk_usage
    context.config.components.storage.staging = str(tmp_path)
    context.projected_staging_bytes = 1000 * GIB
    result = disk.check(context)

    assert result.status is Status.FAIL
    assert str(tmp_path) in " ".join(result.detail)
    assert "Staged Parquet" in result.what_is_wrong


def test_disk_above_the_projection_passes(context: PreflightContext, tmp_path: Path) -> None:
    context.disk_probe = shutil.disk_usage
    context.config.components.storage.staging = str(tmp_path)
    context.projected_staging_bytes = 1
    assert disk.check(context).status is Status.PASS


def test_disk_measures_the_nearest_existing_parent_of_an_uncreated_staging_root(
    context: PreflightContext, tmp_path: Path
) -> None:
    """A staging root that does not exist yet is normal at Preflight time and must not be reported
    as a disk fault."""
    context.disk_probe = shutil.disk_usage
    context.config.components.storage.staging = str(tmp_path / "not" / "created" / "yet")
    context.projected_staging_bytes = 1
    result = disk.check(context)
    assert result.status is Status.PASS
    assert str(tmp_path) in " ".join(result.detail)


# --- (b.1) round 10 — verdicts on the container runtime, never the host --------


def test_memory_verdicts_on_the_daemon_even_when_the_host_would_fail(
    context: PreflightContext,
) -> None:
    """The bug this round fixes, reproduced directly: before it, `memory_probe` read the host, and
    a host with plenty of RAM masked a daemon that did not. Now the host figure cannot make the
    check pass by itself — this asserts the inverse of the historical bug, not merely that the two
    probes are both read."""
    context.memory_probe = lambda: 32 * GIB
    context.host_memory_probe = lambda: 1 * GIB  # would fail the floor on its own
    result = memory.check(context)
    assert result.status is Status.PASS
    assert "1.0GiB" in " ".join(result.detail), "the host figure must still be reported, as context"


def test_memory_verdicts_on_the_daemon_even_when_the_host_would_pass(
    context: PreflightContext,
) -> None:
    """The exact false pass `05_DEPLOYMENT.md` §2.1 forbids, reproduced directly: a host with ample
    RAM (this sandbox's own real 36GiB) must not make this check pass when the daemon it will
    actually run containers inside cannot hold the profile (this sandbox's own real 9.7GiB)."""
    context.memory_probe = lambda: int(9.7 * GIB)
    context.host_memory_probe = lambda: 36 * GIB
    result = memory.check(context)
    assert result.status is Status.FAIL
    assert "36.0GiB" in " ".join(result.detail), (
        "the host figure must still be reported, as context"
    )


def test_memory_is_skipped_when_the_daemon_cannot_be_reached() -> None:
    """`subprocess.CalledProcessError`/`FileNotFoundError`/`TimeoutExpired` — every real failure
    shape `docker info` can produce — must skip, never pass, matching `05_DEPLOYMENT.md` §2.1's
    "a check that cannot run reports that it did not run."""
    for error in (
        subprocess.CalledProcessError(1, ["docker", "info"]),
        FileNotFoundError("no such file: docker"),
        subprocess.TimeoutExpired(["docker", "info"], 10),
    ):

        def _raise() -> int:
            raise error

        ctx = PreflightContext(
            config=OspreyConfig.model_validate(yaml.safe_load(FIXTURE_CONFIG)),
            out_dir=Path("/unused"),
            memory_probe=_raise,
        )
        result = memory.check(ctx)
        assert result.status is Status.SKIP, f"{error!r} must skip, not silently pass"


def test_disk_verdicts_on_the_daemon_even_when_the_host_would_pass(
    context: PreflightContext,
) -> None:
    context.disk_probe = lambda _path: (100 * GIB, 99 * GIB, 1 * GIB)
    context.host_disk_probe = lambda _path: (500 * GIB, 0, 500 * GIB)
    context.projected_staging_bytes = 20 * GIB
    result = disk.check(context)
    assert result.status is Status.FAIL
    assert "500.0GiB" in " ".join(result.detail), (
        "the host figure must still be reported, as context"
    )


def test_disk_is_skipped_when_the_runtime_cannot_be_reached(context: PreflightContext) -> None:
    def _raise(_path: Path) -> tuple[int, int, int]:
        raise subprocess.CalledProcessError(1, ["docker", "run", "--rm", "alpine", "df"])

    context.disk_probe = _raise
    result = disk.check(context)
    assert result.status is Status.SKIP


# --- (c) GPU ------------------------------------------------------------------


def test_gpu_is_skipped_with_a_reason_rather_than_passed(context: PreflightContext) -> None:
    """On macOS the driver version cannot be read headlessly, so this is `skip`. The brief's own
    instruction: record it as skip-with-reason, not pass."""
    from harness.preflight import gpu

    result = gpu.check(context)
    assert result.status in {Status.SKIP, Status.PASS, Status.FAIL}
    if sys.platform == "darwin":
        assert result.status is Status.SKIP
        assert "macOS" in result.what_is_wrong
        assert "not a statement" in result.what_is_wrong


# --- (d) ports ----------------------------------------------------------------


def test_a_port_from_the_real_rendered_compose_file_bound_by_a_real_socket_fails(
    context: PreflightContext, rendered_dir: Path
) -> None:
    """The planted failure in its real shape: read a port out of the rendered compose file, bind it
    with a real socket, and assert the check names that port and its service."""
    compose = yaml.safe_load((rendered_dir / "compose.yaml").read_text(encoding="utf-8"))
    declared = ports.declared_ports(compose)
    assert declared, "the rendered compose file must publish at least one port for this test"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        taken_port = holder.getsockname()[1]
        holder.listen(1)

        # Re-render with a service published on the port we are actually holding, so the check
        # reads a real file naming a real, really-bound port.
        compose["services"]["api"]["ports"] = [f"{taken_port}:8000"]
        (rendered_dir / "compose.yaml").write_text(yaml.safe_dump(compose), encoding="utf-8")

        result = ports.check(context)

    assert result.status is Status.FAIL
    assert str(taken_port) in result.what_is_wrong
    assert "api" in result.what_is_wrong
    assert "ospreyflow stop" in result.what_to_do


def test_free_ports_pass(context: PreflightContext, rendered_dir: Path) -> None:
    compose = yaml.safe_load((rendered_dir / "compose.yaml").read_text(encoding="utf-8"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    compose["services"] = {"api": {"image": "x", "ports": [f"{free_port}:8000"]}}
    (rendered_dir / "compose.yaml").write_text(yaml.safe_dump(compose), encoding="utf-8")

    assert ports.check(context).status is Status.PASS


def test_ports_fails_clearly_when_nothing_has_been_rendered(
    config: OspreyConfig, tmp_path: Path
) -> None:
    result = ports.check(PreflightContext(config=config, out_dir=tmp_path / "nothing-here"))
    assert result.status is Status.FAIL
    assert "harness.render" in result.what_to_do


# --- (e) container runtime ----------------------------------------------------


def test_a_missing_container_runtime_fails_and_names_the_remedy(
    context: PreflightContext,
) -> None:
    context.container_runtime = "definitely-not-a-real-container-runtime"
    result = runtime.check(context)
    assert result.status is Status.FAIL
    assert "not on PATH" in result.what_is_wrong
    assert "Docker Desktop" in result.what_to_do


# --- (f) cluster connectivity --------------------------------------------------


def test_cluster_connectivity_is_skipped_for_local_lite(context: PreflightContext) -> None:
    result = cluster.check(context)
    assert result.status is Status.SKIP
    assert "local-lite" in result.what_is_wrong


def test_an_unreachable_declared_host_fails_and_names_it() -> None:
    """A real TCP connect to a real address in the documentation-only range (TEST-NET-1,
    192.0.2.0/24, reserved by RFC 5737 precisely so it routes nowhere)."""
    config = OspreyConfig.model_validate(
        {
            "profile": "cluster",
            "cluster": {"hosts": [{"name": "node-a", "address": "192.0.2.1"}],
                        "shared_storage_class": "efs-sc"},
            "external": {"postgres": {"host": "db.example.org"}, "valkey": {"host": "cache.example.org"}, "object_store": {"endpoint": "s3.example.org", "region": "eu-west-2"}},
        }
    )
    context = PreflightContext(config=config, out_dir=Path("/nonexistent"))
    cluster._TIMEOUT_SECONDS = 1.0  # keep the suite quick; the connect is still real

    result = cluster.check(context)
    assert result.status is Status.FAIL
    assert "node-a" in result.what_is_wrong and "192.0.2.1" in result.what_is_wrong


# --- (g1) interpreter ----------------------------------------------------------


def test_a_real_system_python_interpreter_path_fails(context: PreflightContext) -> None:
    """The planted failure is a real interpreter that really is outside the project venv."""
    system_python = Path("/usr/bin/python3")
    if not system_python.exists():
        pytest.skip("no /usr/bin/python3 on this machine to plant as the wrong interpreter")
    context.interpreter = system_python

    result = interpreter_check.check(context)
    assert result.status is Status.FAIL
    assert "/usr/bin/python3" in result.what_is_wrong
    assert ".venv/bin/python" in result.what_to_do


def test_the_project_venv_interpreter_passes(context: PreflightContext) -> None:
    """The case that caught a real bug in this check before it had a test: `.venv/bin/python` is a
    symlink to the base interpreter that created the venv, so resolving the *file* walks out of the
    venv and reports a correct setup as broken. This asserts the interpreter actually running this
    suite is accepted."""
    context.interpreter = Path(sys.executable)
    result = interpreter_check.check(context)
    if not Path(sys.executable).parent.resolve().is_relative_to(
        interpreter_check.PROJECT_VENV.resolve()
    ):
        pytest.skip("not running under the project venv, so there is nothing to prove")
    assert result.status is Status.PASS


# --- (g2) bind address ---------------------------------------------------------


def test_bind_address_passes_against_this_machine_s_real_resolver(
    context: PreflightContext,
) -> None:
    result = bind_address.check(context)
    assert result.status is Status.PASS
    assert any("localhost" in line for line in result.detail), (
        "05 §2.1 needs this check to print what it saw, not only judge it"
    )


def test_localhost_resolving_to_ipv6_only_fails_with_the_rehearsal_s_own_diagnosis(
    context: PreflightContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seam, named: putting this machine into the IPv6-only state would mean editing `/etc/hosts`.
    What is patched is `getaddrinfo`, whose return shape is exactly what the check reads."""

    def ipv6_only(*_args: object, **_kwargs: object) -> list[tuple]:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0))]

    monkeypatch.setattr(bind_address.socket, "getaddrinfo", ipv6_only)
    result = bind_address.check(context)

    assert result.status is Status.FAIL
    assert "::1" in result.what_is_wrong
    assert "127.0.0.1" in result.what_to_do


# --- (g3) basemap --------------------------------------------------------------


def test_tiles_that_do_not_exist_yet_warn_rather_than_block(context: PreflightContext) -> None:
    """The two outcomes are different faults. Unbuilt tiles are a post-install step: the stack
    comes up, everything else works, and the map is blank until one command is run. Blocking Launch
    on it means a fresh clone can never reach a running system at all — a worse failure than a
    blank map the operator can fix afterwards."""
    result = basemap.check(context)

    assert result.status is Status.WARN
    assert result.ok, "a warning must not block Launch"
    assert "does not exist yet" in result.what_is_wrong
    assert "scripts.build_local_basemap" in result.what_to_do


def test_the_gate_passes_on_a_warning_and_still_fails_on_a_failure(
    context: PreflightContext,
) -> None:
    """The property the split exists for, asserted through `ok` rather than by reading the status
    name — a fourth status that everything still treated as blocking would pass the case above and
    change nothing. The blocking case is a real one: a default provider that is not in the list,
    which is what an empty `map.default` in `osprey.yaml` produces and leaves no layer selected."""
    unbuilt = basemap.check(context)
    assert unbuilt.ok

    context.config.map.default = ""
    no_default = basemap.check(context)
    assert not no_default.ok, "a default that names no provider must block"


def test_removing_the_split_makes_both_cases_wrong(context: PreflightContext) -> None:
    """Rule 15's own lever for this change. The two cases must reach **different** statuses; a
    check that collapsed them — whichever way — would satisfy one of the two assertions above and
    fail this one. Without it, a regression that made both `fail` again (or both `warn`) would be
    caught by exactly one test and might be read as that test being wrong."""
    unbuilt = basemap.check(context)

    context.config.map.default = ""
    no_default = basemap.check(context)

    assert unbuilt.status is not no_default.status, (
        "tiles not built yet and no default provider are different faults with different "
        "urgencies; a check that gives them the same status has lost the distinction the split "
        "was made for"
    )
    assert (unbuilt.ok, no_default.ok) == (True, False)


def test_tiles_that_exist_behind_a_file_url_pass_because_the_conduit_serves_them(
    context: PreflightContext, tmp_path: Path
) -> None:
    """**This case used to assert FAIL, and that was the defect.** The Conduit serves a `file://`
    provider over `/v1/map/local-source/<id>` and `mapconfig_loader.public_view` rewrites the URI
    for the Glass, so a `file://` entry with the tiles present is the correct, working
    configuration.
    The old check failed on it, which meant a successfully built basemap blocked Launch. The
    planted fault is the real shape: a real file on disk and a real `file://` URI pointing at it."""
    tiles = tmp_path / "osm-local.pmtiles"
    tiles.write_bytes(b"PMTiles")
    context.config.map.providers[0].source = f"file://{tiles}"

    result = basemap.check(context)

    assert result.status is Status.PASS
    assert result.ok


def test_tiles_in_the_mounted_folder_are_found_where_the_conduit_will_see_them(
    context: PreflightContext, tmp_path: Path
) -> None:
    """The provider's source is the path *inside the Conduit's container* (`/data/tiles/...`); the
    file lives in the host folder `components.storage.tiles`. A check that looked for the container
    path on the host would say "does not exist yet" for ever, however often the build succeeded."""
    host_tiles = tmp_path / "tiles"
    host_tiles.mkdir()
    (host_tiles / "great-britain.pmtiles").write_bytes(b"PMTiles")
    context.config.components.storage.tiles = str(host_tiles)
    context.config.map.providers[0].source = "file:///data/tiles/great-britain.pmtiles"

    result = basemap.check(context)

    assert result.status is Status.PASS


def test_a_missing_tile_file_in_the_mounted_folder_names_the_host_folder(
    context: PreflightContext, tmp_path: Path
) -> None:
    context.config.components.storage.tiles = str(tmp_path / "tiles")
    context.config.map.providers[0].source = "file:///data/tiles/great-britain.pmtiles"

    result = basemap.check(context)

    assert result.status is Status.WARN
    assert str(tmp_path / "tiles" / "great-britain.pmtiles") in result.what_is_wrong


def test_a_provider_already_served_over_http_passes(context: PreflightContext) -> None:
    context.config.map.providers[0].source = "https://tiles.example.org/osm/{z}/{x}/{y}.pbf"
    assert basemap.check(context).status is Status.PASS


# --- (g4) DuckDB lock ----------------------------------------------------------


def test_a_real_process_holding_the_duckdb_file_fails_when_seeding(
    context: PreflightContext, tmp_path: Path
) -> None:
    """The planted failure is a real second process with a real exclusive lock — not a patched
    exception. `DEMO_GUIDE.md`'s own fault: "seeding needs the Conduit stopped"."""
    db = tmp_path / "analytics.duckdb"
    context.analytics_db_path = db
    context.seeding = True

    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            # The connection must be *held*: an unassigned `duckdb.connect(...)` is collected
            # immediately and releases the lock, which is how the first version of this test
            # planted no failure at all and the check correctly passed.
            f"import duckdb, time; _c = duckdb.connect({str(db)!r}); time.sleep(60)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not db.exists():
            time.sleep(0.1)
        time.sleep(1.0)  # let the holder actually take the lock, not merely create the file
        result = duckdb_lock.check(context)
    finally:
        holder.terminate()
        holder.wait(timeout=20)

    assert result.status is Status.FAIL, "a live lock holder must block a seed"
    assert "Stop the Conduit before seeding" in result.what_to_do


def test_the_duckdb_lock_is_skipped_when_seeding_was_not_requested(
    context: PreflightContext,
) -> None:
    context.seeding = False
    result = duckdb_lock.check(context)
    assert result.status is Status.SKIP
    assert "--seeding" in result.what_is_wrong


def test_an_unlocked_store_passes_when_seeding(context: PreflightContext, tmp_path: Path) -> None:
    db = tmp_path / "analytics.duckdb"
    context.analytics_db_path = db
    context.seeding = True
    assert duckdb_lock.check(context).status is Status.PASS


# --- (h) the reduced variant: offered, never applied silently ------------------


def test_below_floor_memory_produces_the_offer_and_changes_nothing_on_disk(
    context: PreflightContext, rendered_dir: Path
) -> None:
    """§3's own last clause, as a test: "It is offered, not applied silently." The rendered output
    is compared byte for byte before and after, so an offer that quietly re-rendered would fail
    here rather than be noticed later."""
    before = {p.name: p.read_bytes() for p in sorted(rendered_dir.iterdir())}
    context.memory_probe = lambda: 8 * GIB

    results = run(context)
    offer = offer_for(results, context.config)

    assert offer is not None
    text = offer.render_text()
    assert "opensearch" in text, "the offer must name the component it drops"
    assert "PostgreSQL full-text" in text
    assert "semantic search is unavailable" in text, "the trade-off must be stated, not implied"
    assert "--accept-reduced" in text

    after = {p.name: p.read_bytes() for p in sorted(rendered_dir.iterdir())}
    assert after == before, "the offer must not change deploy/generated/ — §3 forbids it"


def test_memory_at_or_above_the_floor_produces_no_offer(context: PreflightContext) -> None:
    context.memory_probe = lambda: 32 * GIB
    assert offer_for(run(context), context.config) is None


def test_no_offer_when_the_reduced_variant_is_already_in_force(
    context: PreflightContext,
) -> None:
    """Otherwise Preflight offers, every run, something already accepted."""
    context.memory_probe = lambda: 8 * GIB
    context.config.components.search = SearchBackend.POSTGRES_FULLTEXT
    assert offer_for(run(context), context.config) is None


def test_accepting_re_renders_through_the_stage_2_1_renderer(
    context: PreflightContext, rendered_dir: Path
) -> None:
    """Accepting must regenerate rather than edit — §2.1: "never hand-edit a generated artefact"."""
    reduced, written = accept(context.config, rendered_dir)

    assert reduced.components.search is SearchBackend.POSTGRES_FULLTEXT
    assert {p.name for p in written} == {
        "compose.yaml",
        "deployment.env",
        "versions.lock",
        "RUNBOOK.md",
        "Caddyfile",
        "glass.json",
    }
    compose = yaml.safe_load((rendered_dir / "compose.yaml").read_text(encoding="utf-8"))
    assert "opensearch" not in compose["services"]
    assert "reduced variant" in (rendered_dir / "RUNBOOK.md").read_text(encoding="utf-8")


# --- --gate --------------------------------------------------------------------


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "osprey.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_gate_exits_non_zero_with_one_failing_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red. The failing check is the real bind-address one, failing for its real reason (`localhost`
    resolving to IPv6 only). It used to be a basemap case, a `file://` provider whose tiles existed;
    that is the correct, working configuration and no longer fails, and a gate test whose "failure"
    stops being one silently starts proving nothing. The one remaining basemap failure, a default
    that names no provider, is now refused by the schema before any check runs."""

    def ipv6_only(*_args: object, **_kwargs: object) -> list[tuple]:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0))]

    monkeypatch.setattr(bind_address.socket, "getaddrinfo", ipv6_only)
    config_path = _write_config(tmp_path, FIXTURE_CONFIG)
    out_root = tmp_path / "generated"
    write(
        render(OspreyConfig.model_validate(yaml.safe_load(FIXTURE_CONFIG)), allow_unpinned=True),
        out_root / "local-lite",
    )

    code = main(
        [
            "--config", str(config_path), "--out-root", str(out_root),
            "--gate", "--only", "bind-address",
        ]
    )

    assert code == 1
    assert "Launch is blocked" in capsys.readouterr().out


def test_gate_exits_zero_with_no_failing_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Green, through the same CLI path — otherwise the red case above proves only that the gate
    can return 1, not that it distinguishes."""
    body = FIXTURE_CONFIG.replace(
        "source: file:///data/tiles/osm-local.pmtiles",
        "source: https://tiles.example.org/osm/{z}/{x}/{y}.pbf",
    )
    config_path = _write_config(tmp_path, body)
    out_root = tmp_path / "generated"
    write(
        render(OspreyConfig.model_validate(yaml.safe_load(body)), allow_unpinned=True),
        out_root / "local-lite",
    )

    code = main(
        ["--config", str(config_path), "--out-root", str(out_root), "--gate", "--only", "basemap"]
    )

    assert code == 0
    assert "Launch may proceed" in capsys.readouterr().out


def test_only_runs_exactly_one_check(context: PreflightContext) -> None:
    """Re-check is one check, not a filtered full run — the difference an operator waiting on a
    thirty-second cluster probe would notice."""
    results = run(context, only="memory")
    assert [r.check for r in results] == ["memory"]


def test_run_streaming_yields_the_first_result_before_calling_any_later_check(
    context: PreflightContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`harness/webapp.py`'s own Preflight screen (Stage 2 §6 part B) depends on `run_streaming`
    genuinely yielding as each check completes, not merely returning a generator that happens to
    produce the same list `run()` already did — a caller consuming only the first item must not
    have triggered any later check yet. Proven by patching `disk` (the second of eleven) to record
    whether it was ever called, then taking exactly one item from the generator."""
    disk_was_called = False
    real_disk_check = disk.check

    def _tracking_disk_check(ctx: PreflightContext) -> CheckResult:
        nonlocal disk_was_called
        disk_was_called = True
        return real_disk_check(ctx)

    monkeypatch.setattr(disk, "check", _tracking_disk_check)

    first = next(run_streaming(context))

    assert first.check == "memory"
    assert disk_was_called is False


def test_a_crashing_check_is_reported_as_that_check_failing(context: PreflightContext) -> None:
    """The other nine results are still worth having, and a traceback is not a remedy."""
    context.config = None  # type: ignore[assignment]
    results = run(context, only="memory")
    assert results[0].status is Status.FAIL
    assert "the check itself raised" in results[0].what_is_wrong


def test_every_check_result_carries_a_recheck_timestamp(context: PreflightContext) -> None:
    for result in run(context):
        assert result.rechecked_at.endswith("Z")
        assert result.check


def test_the_cli_itself_does_not_apply_the_reduced_variant_without_the_flag(
    context: PreflightContext, rendered_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§3's "offered, not applied silently", exercised through the real CLI rather than through
    `offer_for()` alone.

    This case exists because of a mutation that got away: a planted silent-apply was caught by
    nothing, since `offer_for()` has no access to the output directory and so structurally cannot
    apply anything. The risk was never in that function — it was in this one, where the offer is
    printed next to the code that could act on it.
    """
    context.memory_probe = lambda: 8 * GIB
    before = {p.name: p.read_bytes() for p in sorted(rendered_dir.iterdir())}

    code = main(["--config", "unused", "--out-root", "unused"], context=context)

    out = capsys.readouterr().out
    assert "OFFERED" in out
    assert "--accept-reduced" in out
    assert code == 1, "the failing memory check must still block"
    assert {p.name: p.read_bytes() for p in sorted(rendered_dir.iterdir())} == before


def test_the_cli_applies_the_reduced_variant_only_with_the_flag(
    context: PreflightContext, rendered_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half: without this, the case above is satisfiable by a CLI that can never apply
    the variant at all."""
    context.memory_probe = lambda: 8 * GIB
    before = (rendered_dir / "compose.yaml").read_text(encoding="utf-8")
    assert "opensearch" in before

    main(["--config", "unused", "--out-root", "unused", "--accept-reduced"], context=context)

    out = capsys.readouterr().out
    assert "ACCEPTED" in out
    assert "opensearch" not in (rendered_dir / "compose.yaml").read_text(encoding="utf-8")


def test_accept_reduced_without_an_offer_changes_nothing_and_says_so(
    context: PreflightContext, rendered_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Passing the flag on a machine that is above the floor must not quietly degrade a deployment
    that had no reason to be degraded."""
    context.memory_probe = lambda: 32 * GIB
    before = {p.name: p.read_bytes() for p in sorted(rendered_dir.iterdir())}

    code = main(["--config", "unused", "--out-root", "unused", "--accept-reduced"], context=context)

    assert code == 1
    assert "not on offer" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in sorted(rendered_dir.iterdir())} == before


# --- Interpolated host ports (Stage 2 §5a made every published port overridable) ---


def test_an_interpolated_host_port_resolves_to_its_compose_default() -> None:
    """The bug this exists for, found the moment the renderer gained port overrides: the host side
    of a `ports` entry stopped being a bare number, `split(":")` did not even tokenise
    `${VAR:-8000}:8000` correctly, and `declared_ports` silently returned nothing — so the whole
    port check passed vacuously on every deployment."""
    compose = {"services": {"api": {"ports": ["${OSPREY_API_PORT:-8000}:8000"]}}}
    assert ports.declared_ports(compose, {}) == [("api", 8000)]


def test_an_interpolated_host_port_prefers_the_environment_over_the_default() -> None:
    """Checking the default when the environment overrides it would check a port the deployment is
    not going to use."""
    compose = {"services": {"api": {"ports": ["${OSPREY_API_PORT:-8000}:8000"]}}}
    assert ports.declared_ports(compose, {"OSPREY_API_PORT": "18000"}) == [("api", 18000)]


def test_a_plain_and_an_ip_qualified_host_port_both_parse() -> None:
    compose = {
        "services": {
            "plain": {"ports": ["9000:9000"]},
            "bound": {"ports": ["127.0.0.1:9001:9001"]},
        }
    }
    assert sorted(ports.declared_ports(compose, {})) == [("bound", 9001), ("plain", 9000)]


def test_an_unresolvable_port_is_skipped_rather_than_guessed() -> None:
    """A variable with no default and nothing in the environment names no port. Guessing one would
    check something arbitrary and report it as this deployment's."""
    compose = {"services": {"api": {"ports": ["${OSPREY_API_PORT}:8000"]}}}
    assert ports.declared_ports(compose, {}) == []


# --- (k) oidc-audience — 06_DECISIONS.md ADR-050 objection 1's resolution ------------------------


def test_a_real_render_writes_oidc_audience_and_the_check_passes(context: PreflightContext) -> None:
    """The positive case first: a plain, unmodified render (`rendered_dir`'s own fixture) already
    satisfies this check, because `harness/render.py`'s `_render_env` writes the variable
    unconditionally. Nothing here should need a hand-edited fixture to pass."""
    result = oidc_audience.check(context)
    assert result.status is Status.PASS
    assert f"OIDC_AUDIENCE={CONDUIT_CLIENT_ID}" in result.detail


def test_a_missing_oidc_audience_fails_and_names_the_remedy(
    context: PreflightContext, rendered_dir: Path
) -> None:
    """`CLAUDE.md` rule 15: the planted violation is the real shape a regression would take — a
    rendered environment file with the line simply absent, not a hand-constructed stand-in."""
    env_path = rendered_dir / "deployment.env"
    lines = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("OIDC_AUDIENCE=")
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = oidc_audience.check(context)
    assert result.status is Status.FAIL
    assert "OIDC_AUDIENCE is not set" in result.what_is_wrong
    assert result.what_to_do


def test_an_oidc_audience_naming_the_wrong_client_fails(
    context: PreflightContext, rendered_dir: Path
) -> None:
    """Removing the audience mapper's own effect — a real Keycloak would then mint a token whose
    `aud` never matches this value at all, and a token the realm signs for a different client is
    the exact hole objection 1 names. This is the check-side half: the value itself must be the
    Conduit's own client id, not merely present."""
    env_path = rendered_dir / "deployment.env"
    text = env_path.read_text(encoding="utf-8")
    text = "\n".join(
        line if not line.startswith("OIDC_AUDIENCE=") else "OIDC_AUDIENCE=some-other-client"
        for line in text.splitlines()
    )
    env_path.write_text(text + "\n", encoding="utf-8")

    result = oidc_audience.check(context)
    assert result.status is Status.FAIL
    assert "some-other-client" in result.what_is_wrong


def test_the_check_fails_when_nothing_has_been_rendered_yet(
    config: OspreyConfig, tmp_path: Path
) -> None:
    context = PreflightContext(config=config, out_dir=tmp_path / "never-rendered")
    result = oidc_audience.check(context)
    assert result.status is Status.FAIL


class _MacLoopback:
    """A socket as macOS gives an ordinary user (measured 12 October 2026, ADR-114 Amendment 4's
    live proof): binding `127.0.0.1` below port 1024 is refused `EACCES` whether or not anything
    holds the port, and Docker Desktop publishes it anyway. `listening` is what really holds it."""

    listening: set[int] = set()

    def __init__(self, *args: object) -> None:
        pass

    def bind(self, address: tuple[str, int]) -> None:
        import errno

        if address[1] in self.listening:
            raise OSError(errno.EADDRINUSE, "Address already in use")
        if address[1] < 1024:
            raise OSError(errno.EACCES, "Permission denied")

    def connect_ex(self, address: tuple[str, int]) -> int:
        import errno

        return 0 if address[1] in self.listening else errno.ECONNREFUSED

    def settimeout(self, _seconds: float) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> _MacLoopback:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_a_low_port_refused_for_permission_is_not_reported_in_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The front proxy publishes port 80. A refusal to bind it is not the same as its being held:
    only something answering on it is."""
    monkeypatch.setattr(ports.socket, "socket", _MacLoopback)
    monkeypatch.setattr(_MacLoopback, "listening", set())
    assert ports._is_bindable(80)
    monkeypatch.setattr(_MacLoopback, "listening", {80, 8080})
    assert not ports._is_bindable(80), "something answers on it: it is held"
    assert not ports._is_bindable(8080), "an ordinary port in use is still reported"
