"""A deployment's own PostgreSQL allows what its services may hold (ADR-114 Amendment 43): render.

Rule 12, each invariant and the test that fails without it:

- **Every profile with a PostgreSQL of its own renders the number** (Lite and Small, sized or not),
  and the gateway's and Keycloak's pools are rendered as the number counts them.
- **A deployed Small picks it up**: `apply` restarts PostgreSQL, Keycloak and the gateway, and
  `update`/`start --build` bring an existing compose file to the number.

That the number holds what it counts, against a real PostgreSQL and two real Conduits, is
`test_postgres_connections_live.py`'s (docker; its own CI job).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.profiles import (
    GATEWAY_POOL_MAX,
    KEYCLOAK_POOL_MAX,
    POSTGRES_MAX_CONNECTIONS,
)
from harness.render import POSTGRES_IMAGE, render, render_litellm_config

from schemas.deployment import OspreyConfig

SMALL = {"profile": "small", "network": {"public_origin": "https://demo.example.org"}}


def _rendered(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    config = OspreyConfig.model_validate(raw)
    artefacts = render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts
    return (
        yaml.safe_load(artefacts["compose.yaml"])["services"],
        yaml.safe_load(render_litellm_config(config)),
    )


@pytest.mark.parametrize(
    "raw",
    [{"profile": "local-lite"}, SMALL, {**SMALL, "resources": {"memory_gib": 64}}],
    ids=["lite", "small", "small-sized"],
)
def test_every_owned_postgres_is_rendered_with_the_products_number(raw: dict[str, Any]) -> None:
    command = _rendered(raw)[0]["postgres"]["command"]
    assert command[:3] == ["postgres", "-c", f"max_connections={POSTGRES_MAX_CONNECTIONS}"]


def test_the_gateway_and_keycloak_are_rendered_with_the_pools_the_number_counts() -> None:
    services, gateway = _rendered(SMALL)
    assert services["keycloak"]["environment"]["KC_DB_POOL_MAX_SIZE"] == str(KEYCLOAK_POOL_MAX)
    assert gateway["general_settings"]["database_connection_pool_limit"] == GATEWAY_POOL_MAX
    # One gateway worker: the render gives LiteLLM no `--num_workers`.
    assert "--num_workers" not in json.dumps(services["litellm"].get("command", []))


def test_an_existing_deployment_restarts_postgres_keycloak_and_the_gateway_on_apply(
    tmp_path: Path,
) -> None:
    """A deployed Small picks the number up on `ospreyflow apply` of a release that carries it: the
    definitions of PostgreSQL (its command), Keycloak (its pool) and the gateway (its pool) differ
    from those rendered before, so apply restarts those three and nothing else (ADR-137's
    `services_to_restart`)."""
    from harness.apply import services_to_restart
    from harness.render import write

    config = OspreyConfig.model_validate(SMALL)
    resolver = lambda _image: "sha256:" + "0" * 64  # noqa: E731
    write(render(config, resolver=resolver), tmp_path / "after")
    # `litellm.yaml` is written beside the render by apply itself (`harness/apply.py`).
    (tmp_path / "after" / "litellm.yaml").write_text(
        render_litellm_config(config), encoding="utf-8"
    )
    old = render(config, resolver=resolver)
    compose = yaml.safe_load(old.artefacts["compose.yaml"])
    del compose["services"]["postgres"]["command"]
    del compose["services"]["keycloak"]["environment"]["KC_DB_POOL_MAX_SIZE"]
    old.artefacts["compose.yaml"] = yaml.safe_dump(compose)
    write(old, tmp_path / "before")
    gateway = yaml.safe_load(render_litellm_config(config))
    del gateway["general_settings"]["database_connection_pool_limit"]
    (tmp_path / "before" / "litellm.yaml").write_text(
        yaml.safe_dump(gateway, sort_keys=False), encoding="utf-8"
    )
    assert services_to_restart(tmp_path / "before", tmp_path / "after") == {
        "postgres", "keycloak", "litellm",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("before", "after"),
    [
        # Rendered before Amendment 43: the image's own command.
        (None, ["postgres", "-c", "max_connections={n}"]),
        # Sized (Amendment 33): the memory settings kept, after the number.
        (
            ["postgres", "-c", "shared_buffers=2048MB", "-c", "effective_cache_size=6144MB"],
            ["postgres", "-c", "max_connections={n}", "-c", "shared_buffers=2048MB",
             "-c", "effective_cache_size=6144MB"],
        ),
        # A number set by hand on the command: the product's, as `apply` would render it.
        (
            ["postgres", "-c", "max_connections=400", "-c", "shared_buffers=1024MB"],
            ["postgres", "-c", "max_connections={n}", "-c", "shared_buffers=1024MB"],
        ),
    ],
    ids=["unsized", "sized", "hand-set"],
)  # fmt: skip
def test_update_brings_an_existing_compose_file_to_the_number(
    before: list[str] | None, after: list[str]
) -> None:
    """`ospreyflow update` and `start --build` keep an existing compose file (`scripts/refresh.py`,
    through `process/lanes/admin/platform-pg.diff`): this is what they apply to it."""
    from harness.profiles import postgres_connections_up_to_date

    services: dict[str, Any] = {
        "postgres": {"image": POSTGRES_IMAGE, **({"command": before} if before else {})},
        "keycloak": {"environment": {"KC_DB": "postgres"}},
    }
    assert postgres_connections_up_to_date(services) is True
    wanted = [part.format(n=POSTGRES_MAX_CONNECTIONS) for part in after]
    assert services["postgres"]["command"] == wanted
    assert services["keycloak"]["environment"]["KC_DB_POOL_MAX_SIZE"] == str(KEYCLOAK_POOL_MAX)
    # Safe to repeat, and what it writes is what the render writes for an unsized Small.
    assert postgres_connections_up_to_date(services) is False
    if before is None:
        assert services["postgres"]["command"] == _rendered(SMALL)[0]["postgres"]["command"]
