"""No container reaches outside the deployment unless a configured feature needs it (04 §4: "egress
is default-denied"; ADR-114 Amendment 7, owner-directed 13 October 2026).

Measured on Docker Desktop before this was written: a container on an `internal` network cannot
reach the internet, but cannot publish a port either; a bridge with masquerading turned off still
reaches the internet there. So the layout is: every service on the internal `osprey` network; only a
service whose configured feature needs the outside world joins `egress`; the front proxy, the one
door in, joins `egress` too because a published port cannot be had without it. Model weights are
fetched by one-shot steps that exit, so the model servers that read case content never have a route
out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from harness.render import load_config, render
from tools.layout import CORE

from schemas.deployment import MailConfig, ModelProviderConfig, ModelsConfig, OspreyConfig
from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver


def _config(tmp_path: Path, **update: Any) -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return loaded.model_copy(
        update={
            "components": loaded.components.model_copy(update={"source_path": str(CORE)}),
            **update,
        }
    )


def _compose(config: OspreyConfig) -> dict[str, Any]:
    return yaml.safe_load(render(config, resolver=_fake_resolver).artefacts["compose.yaml"])


def _reaching_outside(compose: dict[str, Any]) -> set[str]:
    return {n for n, s in compose["services"].items() if "egress" in (s.get("networks") or [])}


def test_every_service_is_on_the_internal_network_and_it_has_no_route_out(tmp_path: Path) -> None:
    compose = _compose(_config(tmp_path))
    assert compose["networks"]["osprey"] == {"internal": True}
    assert "internal" not in compose["networks"]["egress"]
    for name, service in compose["services"].items():
        assert "osprey" in service["networks"], name


def test_by_default_only_the_door_and_the_model_downloads_reach_outside(tmp_path: Path) -> None:
    compose = _compose(_config(tmp_path))
    assert _reaching_outside(compose) == {"proxy", "ollama-models", "whisper-models"}


def test_only_the_proxy_publishes_a_port(tmp_path: Path) -> None:
    """A published port needs a route out (measured), so nothing else may publish one — the graph
    store's loopback port is gone."""
    compose = _compose(_config(tmp_path))
    assert {n for n, s in compose["services"].items() if s.get("ports")} == {"proxy"}


def test_the_graph_store_is_reached_from_this_machine_through_the_proxy_only(
    tmp_path: Path,
) -> None:
    """The owner's ruling of 29 September (seeds and the place-name load run on the host) kept,
    without giving the graph store a route out: the proxy, already the door, serves it on
    loopback."""
    config = _config(tmp_path)
    rendered = render(config, resolver=_fake_resolver)
    proxy = yaml.safe_load(rendered.artefacts["compose.yaml"])["services"]["proxy"]
    assert "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480" in proxy["ports"]
    from harness.site import render_caddyfile

    caddyfile = render_caddyfile(config)
    assert "http://:2480 {\n\treverse_proxy arcadedb:2480\n}" in caddyfile


def test_the_model_servers_read_downloaded_weights_and_never_reach_out(tmp_path: Path) -> None:
    services = _compose(_config(tmp_path))["services"]
    assert services["ollama"]["networks"] == ["osprey"]
    assert services["whisper"]["networks"] == ["osprey"]
    assert services["whisper"]["environment"]["HF_HUB_OFFLINE"] == "1"
    shared = services["whisper"]["volumes"][0].split(":")[0]
    assert shared == services["whisper-models"]["volumes"][0].split(":")[0]
    assert services["ollama-models"]["restart"] == "no"
    assert services["ollama"]["volumes"][0].split(":")[0] == (
        services["ollama-models"]["volumes"][0].split(":")[0]
    )


def test_a_client_provider_gives_the_model_gateway_a_route_out(tmp_path: Path) -> None:
    models = ModelsConfig(
        local_only=False,
        provider=ModelProviderConfig(name="openai", roles={"extraction": "gpt-4o-mini"}),
        sendable_handling_codes=["P"],
    )
    assert "litellm" in _reaching_outside(_compose(_config(tmp_path, models=models)))
    assert "litellm" not in _reaching_outside(_compose(_config(tmp_path)))


def test_mail_gives_the_identity_provider_a_route_out(tmp_path: Path) -> None:
    mail = MailConfig.model_validate(
        {"host": "smtp.example.org", "port": 587, "from_address": "osprey@example.org"}
    )
    assert "keycloak" in _reaching_outside(_compose(_config(tmp_path, mail=mail)))
    assert "keycloak" not in _reaching_outside(_compose(_config(tmp_path)))


def test_the_stores_and_case_readers_never_reach_outside_whatever_is_configured(
    tmp_path: Path,
) -> None:
    models = ModelsConfig(
        local_only=False,
        provider=ModelProviderConfig(name="openai", roles={"extraction": "gpt-4o-mini"}),
        sendable_handling_codes=["P"],
    )
    mail = MailConfig.model_validate(
        {"host": "smtp.example.org", "port": 587, "from_address": "osprey@example.org"}
    )
    outside = _reaching_outside(_compose(_config(tmp_path, models=models, mail=mail)))
    never = {"arcadedb", "postgres", "valkey", "minio", "opensearch", "ollama", "whisper", "ner",
             "ingest", "workspace", "superset", "report-sync"}  # fmt: skip
    assert outside.isdisjoint(never), outside & never


def test_the_weights_step_stays_running_after_its_pulls_and_stops_its_own_server(
    tmp_path: Path,
) -> None:
    """Found re-rendering the owner's deployment, 13 October 2026: `up --wait` counts a container
    that has exited as a failure unless a service waits on it, and nothing waits on
    `ollama-models` (the server must not wait for a 2 GB first pull). So after its pulls it stops
    the server it ran for them and idles; a failed pull still exits non-zero (`set -e`), which
    `up --wait` reports."""
    from harness.render import render_ollama_download_script

    config = _config(tmp_path)
    command = _compose(config)["services"]["ollama-models"]["command"][0]
    assert command == render_ollama_download_script(config)
    assert command.startswith("set -e\n")
    lines = command.splitlines()
    assert lines[1] == "ollama serve &" and lines[2] == "server=$$!"
    assert lines[-3:] == ['kill "$$server"', 'wait "$$server" || true', "exec sleep infinity"]
    assert "wait" not in lines
    assert lines.index('kill "$$server"') > max(
        i for i, line in enumerate(lines) if line.startswith("pull_and_verify ")
    )
