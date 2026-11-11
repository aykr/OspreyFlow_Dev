"""Laurium's service in a rendered deployment (`spec/06_DECISIONS.md` ADR-135 Amendments 5 and 6,
P12 part 2): rendered only when `models.extraction_engine` is `laurium`, which the schema allows on
the `cloud-platform` profile alone (`schemas.deployment.OspreyConfig`).

What it holds to:

- **its own image**, `services/laurium/Dockerfile`, built from that folder alone (the Conduit's
  build context leaves it out) or, as a release publishes it, beside the Conduit's image (the same
  registry and commit), so `ospreyflow images push` copies it with ours;
- **the master key never in its container** (decision 8): no `env_file`, so on a cluster no
  `envFrom` of the deployment's Secret, which holds the gateway's master key and every store's
  password. Its environment is its gateway's address alone, the gateway inside the deployment by
  its service name; the adapter sends a scoped key with each call;
- **the gateway rendered with it** (every call Laurium makes goes through the gateway). On compose
  it starts after the gateway is healthy; a cluster translation drops `depends_on`, so on the
  cloud-platform profile the Conduit's own wait for Laurium's key covers it
  (`services.api.laurium_start`).

**Where it may reach is not yet held here:** today the namespace's `allow-egress` admits every pod
to everything it allows. Its row in P7b's per-workload egress (`laurium: [litellm]`, platform's,
ADR-148 Amendment 5) will hold it to the gateway and DNS;
`tests/harness/test_laurium_network_policy.py` is strict-xfailed until then.
"""

from __future__ import annotations

from pathlib import Path

from schemas.deployment import OspreyConfig

#: The service, its port and its gateway, as the cluster's Service names them.
SERVICE = "laurium"
PORT = 8000
GATEWAY_SERVICE = "litellm"
GATEWAY_PORT = 4000
#: The OpenAI-compatible `/v1` the gateway serves, which Laurium's settings accept.
GATEWAY_URL = f"http://{GATEWAY_SERVICE}:{GATEWAY_PORT}/v1"
#: Laurium's own folder, relative to the checkout: its image is built from it alone.
FOLDER = Path("services") / "laurium"


def chosen(config: OspreyConfig) -> bool:
    return config.extraction_engine == "laurium"


def laurium_image(api_image: str) -> str:
    """Laurium's image as a release publishes it, beside the Conduit's `api_image` (the same
    registry and commit)."""
    repository, _, tag = api_image.rpartition(":")
    return f"{repository.rpartition('/')[0]}/{SERVICE}:{tag}"


def laurium_services(
    config: OspreyConfig, *, api_image: str, building: bool, build_context: str | None = None
) -> dict[str, object]:
    """Laurium's compose stanza when it is chosen; nothing otherwise."""
    if not chosen(config):
        return {}
    stanza: dict[str, object] = {
        "restart": "unless-stopped",
        "image": f"osprey/{SERVICE}:local" if building else laurium_image(api_image),
        # Decision 8: no env_file. Its one setting, and nothing that could carry a key.
        "environment": {"OSPREY_LAURIUM_GATEWAY_URL": GATEWAY_URL},
        "depends_on": {GATEWAY_SERVICE: {"condition": "service_healthy"}},
        "healthcheck": {
            "test": ["CMD", "python", "-c",
                     "import urllib.request as u; "
                     f"u.urlopen('http://127.0.0.1:{PORT}/healthz', timeout=5)"],
            "interval": "15s", "timeout": "10s", "retries": 20, "start_period": "60s",
        },
    }  # fmt: skip
    if building:
        root = Path(build_context) if build_context is not None else Path("../../..")
        stanza["build"] = {"context": str(root / FOLDER), "dockerfile": "Dockerfile"}
    return {SERVICE: stanza}


def laurium_env(config: OspreyConfig) -> list[str]:
    """The Conduit's settings for Laurium (`adapters.extract_laurium.composed`), when it is chosen:
    the engine and Laurium's address inside the deployment. No key: the Conduit derives Laurium's
    own from the master key it already reads."""
    if not chosen(config):
        return []
    return [
        "",
        "# ADR-135 Amendment 6: Laurium extracts (its own service); every other model call is",
        "# the gateway's, as before.",
        "OSPREY_EXTRACTION_ENGINE=laurium",
        f"OSPREY_LAURIUM_URL=http://{SERVICE}:{PORT}",
    ]
