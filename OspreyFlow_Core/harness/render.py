"""`python -m harness.render` — `osprey.yaml` in, the deployment's own files out.

`06_DECISIONS.md` ADR-049's **Stage 2 §1**, accepted 24 September 2026. `05_DEPLOYMENT.md` §2.1
names four generated artefacts and this module produces all four, for `local-lite` and `small`:

    "compose or Kubernetes manifests, environment files, `versions.lock` with every image digest
     pinned, and `RUNBOOK.md` written for *this* deployment with the real hostnames, ports and
     paths filled in."

**The `cluster` profile is a different renderer, not a flag** — ADR-011: "Compose for `local-lite`
and `small`; generated Kubernetes manifests for `cluster`." A cluster renders the chart's values
(`harness/cluster.py`, 05 §3b), translated from the same services this module writes compose
from.

**`deploy/compose/dev.yaml` is neither read nor written by this module.** Its own header already
says what it is — "a dev convenience, not the harness… This file exists only to run the test suite
locally" — and generating over it would take a hand-maintained, deliberately-minimal file and
replace it with a twelve-container deployment nobody asked for.

## Two of §2.4's five guards live here; the other three are named so they are not assumed

- **Drift detection — `--check`, below.** §2.4: "the harness compares the running deployment
  against `osprey.yaml` and shows any divergence." This is the *file* half of that: generated
  output against what is on disk. The running-deployment half needs a running deployment and
  belongs with Stage 2 §3.
- **Change preview — `--diff`, below.** §2.4: "Every switch shows what will be created, changed
  and destroyed before it runs, as a diff against the current state, not only at first generate."
- **Target confirmation — not here.** Stage 2 §3, where an orchestrator is actually invoked.
- **Ordering enforcement (backup before a profile switch) — not here.** Stage 2 §4, where a backup
  exists to check for.
- **Capacity check on downgrade — not here.** Stage 2 §4, same reason.

## Where the output goes, and the open question about it

Rendered output is written under `deploy/generated/<profile>/`. `05_DEPLOYMENT.md` names
`deploy/versions.lock` (§5, §7) and `deploy/compose/dev.yaml` (§2.4) as single, fixed
paths, which is right for a deployment — a deployment is one profile — but wrong for a repository
that can render three. Rendering per-profile keeps two renders from overwriting each other; whether
a real deployment's own artefacts then live at the §5/§7 paths is a genuine gap in the
specification, raised as **Proposed** in `05_DEPLOYMENT.md` §2.1 rather than decided here
(`CLAUDE.md` rule 11).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from harness.images import (
    DigestResolver,
    ServiceImage,
    daemon_then_registry_digest_resolver,
    unresolved_digest_resolver,
)
from harness.laurium import laurium_env, laurium_services
from harness.profiles import (
    GATEWAY_POOL_MAX,
    KEYCLOAK_POOL_MAX,
    arcadedb_java_memory_opts,
    postgres_command,
    store_memory,
)
from harness.realm import CONDUIT_CLIENT_ID
from harness.reporting import reporting_env, reporting_services
from harness.site import (
    PROXY_IMAGE,
    highest_marking,
    proxy_service,
    render_caddyfile,
    render_glass_settings,
    sites,
)
from schemas.deployment import (
    EXTRACTION_CONTEXT_TOKENS,
    EXTRACTION_MODELS,
    TILES_CONTAINER_PATH,
    OspreyConfig,
    Profile,
    SearchBackend,
    compose_project,
    generated_folder,
    host_folder_source,
)

#: Where the workspace's nginx serves the basemap's glyph files from
#: (`apps/workspace/nginx.conf.template`).
GLYPHS_CONTAINER_PATH = "/usr/share/nginx/fonts"

#: **Where the ingest root is mounted inside the Conduit — fixed, not configurable** (owner ruling
#: R6, 27 September 2026). The *host* side is `components.storage.ingest` and an operator moves it
#: freely; the container side is a constant so that the Conduit's own source-file route and this
#: renderer cannot drift apart. `OSPREY_INGEST_ROOT` carries it into the container rather than the
#: Conduit hard-coding a second copy — `tests/harness/test_render.py` has the case that fails if
#: the two stop agreeing.
INGEST_CONTAINER_PATH = "/var/lib/osprey/ingest"

#: The one sub-folder of the ingest root the Conduit may write to (ADR-067, which amends ruling R6):
#: files an analyst uploads from the browser land here. It must equal
#: `services.api.ingest_sources.UPLOAD_SUBDIR`; `tests/harness/test_render.py` fails if it drifts.
INGEST_UPLOAD_SUBDIR = "uploaded"

#: Where the Conduit commits published recipes (`09_INGEST_STUDIO.md` §6). Round 13bf: this sits
#: *under* the data root deliberately, so it rides the already-persistent `osprey-data` volume
#: rather than needing a mount of its own — the image's `/app` default is rebuilt on every deploy
#: and is not a repository, which is why Publish 500ed in every rendered deployment until now.
RECIPE_REPO_DIRNAME = "recipes"

#: **The model pull, ported verbatim from `deploy/compose/dev.yaml` — round 13cda.**
#: ADR-020 pins these weights by manifest digest and this script verifies them at startup: a tag
#: that moved upstream fails the container loudly rather than silently changing which model a
#: deployment runs. Kept byte-identical to the developer stack's own copy so the two cannot drift
#: into running different weights — `test_the_rendered_model_pull_matches_the_developer_stacks`
#: compares them and is what fails if they do.
#:
#: Assembled from three pieces rather than written as one literal only because the `FATAL` line
#: is 191 characters and must not be wrapped: wrapping it would change the script's bytes, and
#: byte-identity with `dev.yaml` is the property the test above checks.
_OLLAMA_PULL_SCRIPT = (
    "set -e\n"
    "ollama serve &\n"
    "until ollama list >/dev/null 2>&1; do sleep 1; done\n"
    "pull_and_verify() {\n"
    '  model="$$1"; expected="$$2"\n'
    '  ollama pull "$$model"\n'
    '  actual="$$(ollama list | awk -v m="$$model" \'$$1 == m {print $$2}\')"\n'
    '  if [ "$$actual" != "$$expected" ]; then\n'
    '    echo "FATAL: $$model resolved to manifest $$actual, expected $$expected '
    "(spec/06_DECISIONS.md ADR-020) \u2014 the tag moved upstream; update the ADR "
    'deliberately, do not proceed silently." >&2\n'
    "    exit 1\n"
    "  fi\n"
    "}\n"
    "pull_and_verify qwen2.5:0.5b-instruct a8b0c5157701\n"
    "pull_and_verify all-minilm:22m-l6-v2-fp16 1b226e2802db\n"
    "pull_and_verify moondream:1.8b-v2-q4_K_M c865c80afc38\n"
    "wait\n"
)


def render_ollama_pull_script(config: OspreyConfig) -> str:
    """The developer stack's pull script plus one line: the deployment's own extraction model,
    pulled and digest-verified the same way (`06_DECISIONS.md` ADR-095 decision 1). The developer
    stack and CI keep pulling the small pinned models only; `test_deployment_models.py` holds the
    rendered script to exactly that."""
    model = config.extraction_model
    line = f"pull_and_verify {model} {EXTRACTION_MODELS[model]}\n"
    return _OLLAMA_PULL_SCRIPT.replace("wait\n", line + "wait\n")


def render_ollama_download_script(config: OspreyConfig) -> str:
    """ADR-114 Amendment 7: `ollama-models`' script — the same pulls, then the server it ran for
    them stopped and the step left idle rather than exited, because `up --wait` counts a container
    that has exited as a failure unless a service waits on it, and the model server must not wait
    for a first pull of gigabytes. A failed pull still exits non-zero (`set -e`)."""
    script = render_ollama_pull_script(config)
    script = script.replace("ollama serve &\n", "ollama serve &\nserver=$$!\n", 1)
    # Reaped, so no zombie is left behind; its exit status is the kill's, not a failure.
    return script.replace(
        "wait\n", 'kill "$$server"\nwait "$$server" || true\nexec sleep infinity\n'
    )


#: **Healthy once the two models the Conduit actually serves with are present — not all three.**
#:
#: `deploy/compose/dev.yaml` waits for all three, which is right for a developer stack about to
#: run the whole test suite. It is wrong for a deployment, and measured: on a 673 KB/s link the
#: vision model (`moondream`, 918MB) had 16 minutes left when the other two were already in, and
#: `harness.apply` failed at `up` with ollama unhealthy. A deployment that cannot start because a
#: model *nothing in the demo path uses* is still downloading is a worse failure than a
#: `describe_image` that is briefly unavailable.
#:
#: `CONFORMANCE_MODEL` (chat) and `CONFORMANCE_EMBED_MODEL` (embed) are what
#: `adapters/model_litellm` extracts and embeds with — checked, not assumed. `moondream` backs
#: `describe_image` alone; the pull script still fetches and digest-verifies it, so it arrives
#: shortly after the deployment reports ready, and that window is the disclosed cost of this
#: choice.
_OLLAMA_HEALTHCHECK = [
    "CMD-SHELL",
    "ollama list | grep -q qwen2.5:0.5b-instruct "
    "&& ollama list | grep -q all-minilm:22m-l6-v2-fp16",
]

#: **One statement of the model proxy's key — round 13cda.**
#:
#: Three places have to agree or the Conduit gets a 401 from its own proxy: the `litellm`
#: service's `LITELLM_MASTER_KEY`, the `master_key` inside the rendered `litellm.yaml`, and the
#: Conduit's `LITELLM_API_KEY` (`adapters/model_litellm/client.py`'s `LiteLLMConfig.from_env`).
#:
#: A first attempt wrote `${OSPREY_LITELLM_KEY:-sk-ospreyflow-dev}` into all three. Compose
#: expands that in a *service environment*; it does not expand it inside a config file it merely
#: mounts, so litellm's own key became the eleven-character string `${OSPREY_LITELLM...}` while
#: the Conduit sent the default — measured, `401 Unauthorized for url
#: http://litellm:4000/chat/completions`, and confirmed by reading the file inside the container.
#:
#: The value is a fixed dev-tier credential, the same posture as `dev.yaml`'s: the proxy publishes
#: no port and is reachable only on the deployment's internal network (`05_DEPLOYMENT.md` §7), so
#: this is not a secret an operator supplies. `test_the_model_proxy_and_the_conduit_agree_on_one
#: _key` is what fails if the three drift apart again.
LITELLM_KEY = "sk-ospreyflow-dev"

#: ADR-135 Amendment 2 decision 3: the gateway keeps engines and keys in its own database, so its
#: master key is no longer a fixed development value but minted per deployment, like the database's
#: password and the encryption key ("salt") the stored keys are sealed with. Each name ends in
#: SECRET or PASSWORD so `harness.apply.keep_existing_secrets` keeps it across every `apply`: a
#: different salt silently drops every stored engine (measured), so it is minted once and never
#: again. `LITELLM_KEY` above stays for the developer stack (`deploy/compose/dev.yaml`).
GATEWAY_MASTER = "OSPREY_LITELLM_MASTER_SECRET"
GATEWAY_SALT = "OSPREY_LITELLM_SALT_SECRET"
GATEWAY_DB_PASSWORD = "OSPREY_LITELLM_DB_PASSWORD"
#: Where the Conduit keeps the models file (decision 2): a named volume, which takes the image's own
#: folder (made by `services/api/Dockerfile`, owned by its user) on first mount, so it is writable
#: by the Conduit's user on any host.
MODEL_SETTINGS_PATH = "/run/osprey/model-settings"
#: ADR-147 decision 1: where the Conduit keeps the maps file and the map key file, a named volume of
#: its own made the same way (`services/api/Dockerfile` makes the folder, owned by its user).
MAP_SETTINGS_PATH = "/run/osprey/map-settings"
#: ADR-147 decision 3: the one writable folder inside the read-only tiles folder, where a basemap
#: built in the Conduit is written (`services/api/map_admin.BUILT_FOLDER`).
TILES_BUILT_SUBDIR = "built"

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CONFIG_PATH = REPO_ROOT / "osprey.yaml"
DEFAULT_OUT_ROOT = REPO_ROOT / "deploy" / "generated"

#: Written into every generated file. `05_DEPLOYMENT.md` §2.1: "never hand-edit a generated
#: artefact — regenerate instead." The banner is what makes `--check`'s drift report land on
#: someone who has already been told not to do this.
_BANNER = (
    "GENERATED by `python -m harness.render` from osprey.yaml. Do not hand-edit —\n"
    "regenerate instead (spec/05_DEPLOYMENT.md §2.1). A hand edit is reported by\n"
    "`python -m harness.render --check` as drift, naming this path."
)


class MissingDockerfileError(RuntimeError):
    """Names every OspreyFlow-owned service whose Dockerfile is not at the declared
    `components.source_path`.

    Only raised when `source_path` is declared at all (round 07: pull mode, the default, never
    looks for a local Dockerfile in the first place — nothing to be missing). A `build:` stanza
    pointing at a Dockerfile that does not exist renders a compose file that fails at
    `docker compose build` with Docker's own error, several steps and one confusing message later.
    Refusing here, by name, is the same "named refusal, not a silent partial" shape
    `tools/osprey_bundle.py` already uses for a non-redistributable provider.
    """

    def __init__(self, services: Sequence[str], *, source_path: str) -> None:
        self.services = tuple(services)
        self.source_path = source_path
        super().__init__(
            "refusing to render: components.source_path "
            + repr(source_path)
            + " declares a build from source, but it has no Dockerfile for owned service(s) "
            + ", ".join(services)
        )


def render_litellm_config(config: OspreyConfig) -> str:
    """The model routing table, written beside the compose file — round 13cda.

    **Not one of `05_DEPLOYMENT.md` §2.1's four artefacts**, and deliberately so: like
    `realm.json`, this is a *service's own config file* that happens to be generated, not one of
    the four things §2.1 promises an operator. `harness/apply.py` writes both, from pure
    functions here and in `harness/realm.py`, so `render`'s contract — and the byte-stability
    test that rests on it — is unchanged.

    `04_VAULT_BACKEND.md` §4: LiteLLM "presents one OpenAI-compatible endpoint" and changing a
    model "is a YAML edit and a restart of one container". This is that YAML for a rendered
    deployment; `deploy/compose/litellm_config.yaml` is the developer stack's own hand-written
    copy and stays as it is.

    **The backend hostnames are this deployment's own service names, and that is the part worth
    checking.** The developer stack calls its transcription service `speaches`; the renderer
    calls it `whisper`. Copying dev's file verbatim would route transcription at a host that does
    not exist here, and it would fail only when someone transcribed something — long after the
    deployment reported healthy.

    ADR-020 pins the model weights themselves, verified at the `ollama` service's own startup.
    This file only wires names to backends, so the pin stays in one place.
    """
    extraction = config.extraction_model
    table = yaml.safe_load(_local_model_table(config, extraction))
    # ADR-135 Amendment 2 decision 3: hosted engines live only in the gateway's database, made
    # there by the Conduit, so no `model_name` is both rendered and stored.
    return yaml.safe_dump(table, sort_keys=False)


def provider_model_entries(config: OspreyConfig) -> list[dict[str, object]]:
    """**No longer rendered** (ADR-135 Amendment 2 decision 3: the gateway's database holds each
    engine's entries, made by the Conduit). Kept as the description the routing tests' stand-in
    gateway builds its table from. ADR-114 Amendment 6 point 4, ADR-135 decision 2: each enabled
    provider's models, routed through the gateway as `provider/model`, each reading its own
    provider's key from the gateway's own environment (`os.environ/OSPREY_MODEL_KEY_<NAME>`, or
    `OSPREY_MODEL_PROVIDER_KEY` for the single `models.provider`) — never written into this
    file."""
    entries: list[dict[str, object]] = []
    for provider in config.models.enabled_providers:
        key = config.models.key_variable(provider.name)
        for model in dict.fromkeys(provider.roles.values()):
            name = f"{provider.name}/{model}"
            params: dict[str, object] = {"model": provider.route(model)}
            if not provider.keyless:  # ADR-135 Amendment 4: an IAM-role engine names no key
                params["api_key"] = f"os.environ/{key}"
            if provider.region:
                params["aws_region_name"] = provider.region
            if provider.api_base:
                params["api_base"] = provider.api_base
            entries.append({"model_name": name, "litellm_params": params})
    return entries


def model_key_variables(config: OspreyConfig) -> dict[str, str]:
    """Each enabled provider's name and the `deployment.env` variable its key is kept in."""
    # An engine signed in by the gateway's own IAM role has none (ADR-135 Amendment 4).
    return {p.name: config.models.key_variable(p.name) for p in config.models.keyed_providers}


def keyless_model_key_variables(config: OspreyConfig) -> dict[str, str]:
    """The variable each IAM-role engine's key **would** be kept in (ADR-135 Amendment 4). It keeps
    none, but one held under its name (an earlier engine of that name) stays in the deployment's
    Secret until a move removes it, so the cluster's translation, which the `cloud-platform` render
    reuses, blanks it in every workload that reads the Secret whole; the gateway reads none whole
    and is never given it by name. Empty on every other profile, which takes no IAM-role engine
    (Amendment 7 decision 1)."""
    models = config.models
    return {p.name: models.key_variable(p.name) for p in models.enabled_providers if p.keyless}


def model_engines_env(config: OspreyConfig) -> list[str]:
    """ADR-135: what the Conduit is told of the engines, as `deployment.env` lines — each enabled
    provider's name, label, model per role and privacy-contract mark (ADR-136), each role's
    default engine, and the sendable codes.
    Never a key, and not whether one is present: that is resolved by Compose from the env file when
    the Conduit starts (`OSPREY_MODEL_KEY_PRESENT_<NAME>`, `_keys_for_the_gateway_alone`), so
    setting or removing a key needs no render."""
    models = config.models
    if not models.enabled_providers:
        return []
    engines = [
        {
            "name": p.name,
            "label": p.label,
            "roles": {role: f"{p.name}/{model}" for role, model in p.roles.items()},
            # ADR-136 decision 1: the contract mark and its reference (words, never a secret).
            "privacy_contract": p.privacy_contract,
            "contract_reference": p.contract_reference,
            # ADR-135 Amendment 2: the Conduit makes the gateway's entries, so it needs the base.
            "api_base": p.api_base,
            # ADR-135 Amendment 4: what the engine is, how it signs in, and Bedrock's region;
            # not written for a plain provider, so every other profile's line is as before.
            **({} if p.plain else {"kind": p.kind, "auth": p.auth, "region": p.region}),
        }
        for p in models.enabled_providers
    ]
    compact = {"separators": (",", ":"), "ensure_ascii": True}
    return [
        "OSPREY_MODEL_ENGINES=" + json.dumps(engines, **compact),  # type: ignore[arg-type]
        "OSPREY_MODEL_DEFAULTS=" + json.dumps(models.role_defaults, **compact),  # type: ignore[arg-type]
        "OSPREY_SENDABLE_HANDLING_CODES=" + ",".join(models.sendable_handling_codes),
    ]


def _keys_for_the_gateway_alone(config: OspreyConfig, services: dict[str, Any]) -> None:
    """ADR-135 decision 2: a provider's key is read by the LiteLLM gateway alone. The keys live in
    `deployment.env`, which every owned service reads whole (`env_file`), so each such service's own
    environment — which Compose, and the chart's `env` over `envFrom`, put above the file — blanks
    every key. The Conduit is told instead whether each key is present, by Compose from the same
    file (`${KEY:+yes}`: "yes" or empty), so it offers analysts only an engine that has one."""
    keys = model_key_variables(config)
    if not keys:
        return
    for name, service in services.items():
        if name == "litellm":
            service["environment"] = {
                **dict(service.get("environment") or {}),
                **{key: f"${{{key}:-}}" for key in keys.values()},
            }
            continue
        if "env_file" not in service:
            continue
        environment = dict(service.get("environment") or {})
        environment.update({key: "" for key in keys.values()})
        if name == "api":
            for provider, key in keys.items():
                environment[f"OSPREY_MODEL_KEY_PRESENT_{provider.upper()}"] = f"${{{key}:+yes}}"
        service["environment"] = environment


def connection_secret_variables(config: OspreyConfig) -> list[str]:
    """Each declared connection secret's `deployment.env` variable (ADR-140 Amendment 15)."""
    return [f"OSPREY_CONNECTION_SECRET_{name}" for name in config.connectors.secrets]


def _connection_secrets_for_the_conduit_alone(
    config: OspreyConfig, services: dict[str, Any]
) -> None:
    """A SQL or API connection's secret is read by the Conduit alone (the orchestrator's review of
    ADR-140 Amendment 15, item 9, as ADR-135 decision 2 keeps a model key to the gateway): every
    other owned service reads `deployment.env` whole, so its own environment, which Compose puts
    above the file, blanks each declared secret."""
    variables = connection_secret_variables(config)
    for name, service in services.items():
        if name == "api" or "env_file" not in service:
            continue
        environment = dict(service.get("environment") or {})
        environment.update({variable: "" for variable in variables})
        service["environment"] = environment


def _local_model_table(config: OspreyConfig, extraction: str) -> str:
    return yaml.safe_dump(
        {
            "model_list": [
                {
                    # ADR-095: the deployment's own extraction model, with room for a long email
                    # whole: Ollama's own default context is a few thousand tokens and it cuts a
                    # longer prompt without saying so.
                    "model_name": extraction,
                    "litellm_params": {
                        "model": f"ollama_chat/{extraction}",
                        "api_base": "http://ollama:11434",
                        "num_ctx": EXTRACTION_CONTEXT_TOKENS,
                    },
                },
                {
                    "model_name": "qwen2.5:0.5b-instruct",
                    "litellm_params": {
                        "model": "ollama_chat/qwen2.5:0.5b-instruct",
                        "api_base": "http://ollama:11434",
                    },
                },
                {
                    # `ollama/`, not `ollama_chat/`: an embeddings call is not a chat completion
                    # and LiteLLM routes the two prefixes to different Ollama endpoints.
                    "model_name": "all-minilm:22m-l6-v2-fp16",
                    "litellm_params": {
                        "model": "ollama/all-minilm:22m-l6-v2-fp16",
                        "api_base": "http://ollama:11434",
                    },
                },
                {
                    "model_name": "moondream:1.8b-v2-q4_K_M",
                    "litellm_params": {
                        "model": "ollama_chat/moondream:1.8b-v2-q4_K_M",
                        "api_base": "http://ollama:11434",
                    },
                },
                {
                    "model_name": "Systran/faster-whisper-tiny.en",
                    "litellm_params": {
                        "model": "openai/Systran/faster-whisper-tiny.en",
                        # `whisper`, this deployment's own name for it — see the docstring.
                        "api_base": "http://whisper:8000/v1",
                        "api_key": "not-needed",
                    },
                },
            ],
            "general_settings": {
                "master_key": "os.environ/LITELLM_MASTER_KEY",
                "store_model_in_db": True,
                # ADR-114 Amendment 43: the gateway's share of PostgreSQL, the product's number.
                "database_connection_pool_limit": GATEWAY_POOL_MAX,
            },
        },
        sort_keys=False,
    )


def git_sha(repo_root: Path = REPO_ROOT) -> str:
    """The commit a local build was made from. `unknown` rather than a raise when git is absent or
    this is not a checkout: a lock file that says `unknown` is honest, and one that fails the whole
    render because `git` is missing would make the renderer depend on a tool it does not need.

    **Falls back to `OSPREY_BUILT_FROM_SHA`, round 11.** A real checkout (a developer's own tree,
    the build stage of `.github/workflows/release.yml`) always has `.git`, and `git rev-parse`
    above answers correctly for it. `harness/Dockerfile`'s own header says the harness image itself
    carries none — so a pull-mode render running *inside the released harness image* (this
    function's default `repo_root=REPO_ROOT` case, `service_images`'s own pull-mode branch) used to
    read `unknown` here even on a real release, computing an owned-image tag
    (`ghcr.io/ospreyflow/<service>:unknown`) that could never match what the release pipeline
    actually pushed. The release workflow bakes the exact commit it built every other image from
    into the harness image as `OSPREY_BUILT_FROM_SHA` (`--build-arg`/`ENV`); this is read only when
    `git` itself could not answer, so a real checkout's own `.git` still wins."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    sha = result.stdout.strip() if result is not None else ""
    if result is not None and result.returncode == 0 and sha:
        return sha
    baked = os.environ.get("OSPREY_BUILT_FROM_SHA", "").strip()
    return baked if baked else "unknown"


#: `05_DEPLOYMENT.md` §3/§5/§7's own reference for where a customer checks for a published
#: release once the digest resolvers above have failed to find one — named here so
#: `UnpinnedImagesError`'s own message and those sections stay one string apart, not two to drift.
#: The user repository: `aykr/OspreyFlow` (ADR-114 Amendment 21; Amendment 31 withdrew
#: Amendment 30's move to `Solirius/ospreyflow`). A checkout cloned from it accepts only a release
#: signed by that repository's own `release.yml` (`harness.signatures`).
RELEASES_URL = "https://github.com/aykr/OspreyFlow/releases"


class UnpinnedImagesError(RuntimeError):
    """Names every image whose digest could not be resolved, rather than writing a `versions.lock`
    that claims a pin it does not have.

    **Round 11 — points at the release page, not just at `--allow-unpinned`.** Before this round
    nothing published `ghcr.io/ospreyflow/<service>`, so an unresolved owned image meant "there is
    nothing to find yet" and the only honest advice was the escape hatch. Now that
    `.github/workflows/release.yml` publishes real digests on a tagged release,
    `--allow-unpinned` is a developer flag (`05_DEPLOYMENT.md` §5/§7 say so explicitly) and the
    real remedy for a customer is checking whether a release has actually been cut — this message
    names both, rather than only the flag that silences the check."""

    def __init__(self, images: Sequence[str]) -> None:
        self.images = tuple(images)
        super().__init__(
            "refusing to write versions.lock without a digest for: "
            + ", ".join(images)
            + " — pull them yourself, check "
            + RELEASES_URL
            + " for a published release with a matching digest, or pass --allow-unpinned (a "
            "developer flag, never the customer remedy) to mark them 'unresolved' explicitly"
        )


#: Where an owned service's image is pulled from when `components.source_path` is not declared
#: (the default, round 07) — extending `spec/05_DEPLOYMENT.md` §2's own bootstrap reference
#: convention (`ghcr.io/ospreyflow/harness:latest`) to the three services the harness image
#: cannot build without a mounted checkout. **Published, round 11:** `.github/workflows/
#: release.yml` builds, scans and pushes all four owned images here on a version tag, tagged by
#: the exact commit `git_sha()` above computes — `daemon_then_registry_digest_resolver` (this
#: module's own default resolver) then finds a real digest for them with no local pull needed.
#: `tests/harness/test_render.py`'s own pull-mode test still passes an explicit fake resolver
#: rather than reaching the real registry, the same way every other test in that file avoids
#: a live network call.
OWNED_IMAGE_REGISTRY = "ghcr.io/ospreyflow"


def service_images(config: OspreyConfig, *, build_context: str = "../../..") -> list[ServiceImage]:
    """Every container the rendered stack runs, in a deterministic order.

    `05_DEPLOYMENT.md` §3's own `local-lite` list is the reference: "the workspace, one Conduit,
    three workers, ArcadeDB, DuckDB in-process, Valkey, MinIO, OpenSearch single-node, PostgreSQL,
    Keycloak, Ollama, and a faster-whisper container." DuckDB is in-process and so has no container
    of its own; the three workers have no images in this tree yet (Stage 2 §5's own enumeration
    settles that against §3's count, and is the owner's directed finding before any image is built),
    so they are not invented here.

    **Round 07 — build vs pull is decided once, here, from `config.components.source_path`.** Not
    declared (the default): each owned service's own `image` is a pull-mode registry reference
    (`OWNED_IMAGE_REGISTRY`), and `build_context` is left `None` — `ServiceImage.building` is then
    false, and `_render_compose` emits no `build:` stanza. Declared: the existing local-tag,
    build-from-source shape, unchanged.
    """
    source_path = config.components.source_path
    building = source_path is not None
    sha = git_sha(Path(source_path)) if source_path is not None else git_sha()

    def _owned(service: str, dockerfile: str) -> ServiceImage:
        if building:
            return ServiceImage(
                service,
                f"osprey/{service}:local",
                build_context=build_context,
                dockerfile=dockerfile,
            )
        # ADR-114 Amendment 8: a user repository's release pushes to its own owner's registry.
        registry = os.environ.get("OSPREY_IMAGE_REGISTRY") or OWNED_IMAGE_REGISTRY
        return ServiceImage(service, f"{registry}/{service}:{sha}", dockerfile=dockerfile)

    # **These third-party references are verified to resolve, and that is not a given.** Two of the
    # eight written for Stage 2 §5a did not exist at all — `minio/minio:RELEASE.2024-10-13…` and
    # `ghcr.io/speaches-ai/speaches:0.6.2` — and were only found when a real `docker compose up`
    # aborted the whole pull with `manifest unknown`. They were written from memory rather than
    # checked. Where this repository already knows a working reference, it is taken from
    # `deploy/compose/dev.yaml` rather than invented a second time.
    # `tests/harness/test_image_references.py` now resolves every one of them.
    images: list[ServiceImage] = [
        _owned("workspace", "apps/workspace/Dockerfile"),
        _owned("api", "services/api/Dockerfile"),
        _owned("ingest", "services/ingest/Dockerfile"),
        # ADR-098 decision 2: the fast recogniser (Stanza), its model inside the image.
        _owned("ner", "services/ner/Dockerfile"),
    ]
    if config.components.graph_store.value == "arcadedb":
        # ADR-101: 26.10.1, where an update no longer drops other records from an index key.
        images.append(ServiceImage("arcadedb", "arcadedata/arcadedb:26.10.1"))
    else:
        images.append(ServiceImage("janusgraph", "janusgraph/janusgraph:1.0.0"))
    images.extend(
        [
            ServiceImage("valkey", "valkey/valkey:8.0"),
            # ADR-114 Amendment 9: MinIO's public images were withdrawn; SeaweedFS (Apache-2.0).
            ServiceImage("objectstore", "chrislusf/seaweedfs:4.48"),
            ServiceImage("postgres", POSTGRES_IMAGE),
            ServiceImage("keycloak", "quay.io/keycloak/keycloak:26.0"),
            # ADR-114 Amendment 4: the front proxy, the deployment's one door.
            ServiceImage("proxy", PROXY_IMAGE),
            ServiceImage(
                "ollama",
                "ollama/ollama@sha256:5a5d014aa774f78ebe1340c0d4afc2e35afc12a2c3b34c84e71f78ea20af4ba3",
            ),
            # **The model proxy the Conduit actually talks to — round 13cda.**
            # `04_VAULT_BACKEND.md` §4: "Conduit ──► LiteLLM proxy ──┬──► Ollama (local-lite:
            # LLM + VLM, quantised)". It was specified from the first architecture pass and
            # never rendered: the deployment brought up `ollama` and the Conduit dialled
            # `localhost:4000` inside its own container, so every extraction returned a bare 500
            # (`httpx.ConnectError: All connection attempts failed`, measured over the wire).
            # **The same image the developer stack pins, by digest — corrected in round 13cdd.**
            # Round 13cda pinned a tag chosen here instead, so a deployment ran a *different*
            # LiteLLM from `make dev-up`. That is the exact "two copies that drift" defect the
            # ollama pull beside it was made byte-identical to avoid, reintroduced one line away
            # from it. Measured against the same ollama, the same config and the request shape the
            # route actually emits: the developer stack's proxy returns `{"Endpoint": []}`, while
            # the tag returns *prose* ("I'm sorry, but I cannot…"), because `main-v1.55.8` does not
            # translate `response_format: json_schema` into Ollama's own constrained decoding. That
            # is the `Expecting value: line 1 column 1` `08_ACCEPTANCE_SCENARIOS.md` records as
            # A6/B6's blocker — not an empty body, which is what it was read as before it was
            # measured.
            #
            # `test_the_rendered_model_proxy_is_the_developer_stacks` is what fails if they part.
            ServiceImage(
                "litellm",
                "ghcr.io/berriai/litellm@sha256:d295634e09c648dcdb72c4cc2dd226f5fb87823a73e88cbbed6f205e4deb044b",
            ),
            ServiceImage(
                "whisper",
                "ghcr.io/speaches-ai/speaches@sha256:21e3df06d842fb7802ab470dd77c25f0e8c0d22950e8d8c6ae886e851af53ef8",
            ),
        ]
    )
    # 05 §3a: what a cloud runs for the deployment is not a container of it.
    managed = {
        *(("postgres",) if config.external.postgres is not None else ()),
        *(("objectstore",) if config.external.object_store is not None else ()),
    }
    images = [image for image in images if image.service not in managed]
    if config.components.search is SearchBackend.OPENSEARCH:
        images.append(ServiceImage("opensearch", "opensearchproject/opensearch:2.17.1"))
    if config.components.analytics_engine.value == "clickhouse":
        # The version the ClickHouse adapter was proved against (ADR-114 decision 9).
        images.append(ServiceImage("clickhouse", "clickhouse/clickhouse-server:25.8.33.6"))
    return images


#: A compose `build.context` is resolved **relative to the compose file**, not to the working
#: directory the command was run from. Rendered output lives at `deploy/generated/<profile>/`, so
#: the repository root — which is what the Python images copy `packages/` and `services/` from — is
#: three levels up. Found by running the golden path from a fresh clone: `.` resolved to the output
#: directory itself and the build failed with `lstat .../deploy/generated/local-lite/services: no
#: such file or directory`, which names the symptom and not the cause.
BUILD_CONTEXT_FROM_OUTPUT_DIR = "../../.."


def build_context_for(out_dir: Path, source_path: str | None) -> str:
    """The `build.context` a deployment rendered into `out_dir` names: `../../..` when `out_dir` is
    `<source>/deploy/generated/<name>/`, as every checkout-rooted deployment is (so its files are
    byte for byte what they were); the checkout's own absolute path otherwise — a deployment kept
    under `~/.ospreyflow/deployments/<name>/` (ADR-138 decision 2), where three levels up is the
    home folder, not the checkout."""
    if source_path is None:
        return BUILD_CONTEXT_FROM_OUTPUT_DIR
    source = Path(source_path).resolve()
    if (out_dir / BUILD_CONTEXT_FROM_OUTPUT_DIR).resolve() == source:
        return BUILD_CONTEXT_FROM_OUTPUT_DIR
    return str(source)


#: Published host ports, as `service -> (env var, default)`. Every one is overridable, because
#: Preflight found 8000 already held by an unrelated container on a real machine and a deployment
#: that cannot move its own ports is one an operator has to fight. The defaults are the
#: specification's (`05_DEPLOYMENT.md` §3: the workspace at 8080, the Conduit at 8000), so a
#: deployment that overrides nothing matches the documentation exactly.
#:
#: **ADR-114 Amendment 4: the front proxy is the only door.** The Glass, Keycloak and Superset are
#: reached through it by name and publish nothing; the proxy publishes `network.public_origin`'s
#: own port (`harness/site.py`). What is left here is opt-in or loopback-only.
PORT_OVERRIDES: dict[str, tuple[str, int]] = {
    # Published only when `network.expose_conduit` is on — see `render_compose`. The entry stays
    # here because the port number and its override variable are the same either way.
    "api": ("OSPREY_API_PORT", 8000),
    # Published to this machine only (`LOOPBACK_ONLY`): the place-name load and the dataset seeds
    # run on the host and need the database (owner's ruling of 29 September 2026).
    "arcadedb": ("OSPREY_ARCADEDB_PORT", 2480),
}


def _published_port(config: OspreyConfig, service: str, default: int) -> int:
    """The host port a service is published at: ArcadeDB's is `deployment.graph_port` when set
    (ADR-138 decision 2: a deployment beside another shares no port), every other its default."""
    if service == "arcadedb" and config.deployment.graph_port is not None:
        return config.deployment.graph_port
    return default


_CONTAINER_PORTS: dict[str, int] = {
    "api": 8000,
    "arcadedb": 2480,
}

#: Services whose published port is bound to 127.0.0.1, not every interface.
LOOPBACK_ONLY = frozenset({"arcadedb"})

#: Per-service compose stanzas that are not derivable from the image alone. Keycloak is the only
#: entry today and every line of it is load-bearing — `05_DEPLOYMENT.md` §2.1.1 records why each
#: matters and that each fails silently when missing.
_SERVICE_EXTRAS: dict[str, dict[str, object]] = {
    # Each of these is a variable the image refuses to start without. None was here until the
    # golden path was actually run and postgres, minio and the Conduit all sat in `Restarting`.
    "postgres": {
        "environment": {
            "POSTGRES_USER": "${OSPREY_POSTGRES_USER:-osprey}",
            "POSTGRES_PASSWORD": "${OSPREY_POSTGRES_PASSWORD:?set in the deployment env file}",
            "POSTGRES_DB": "${OSPREY_POSTGRES_DB:-osprey}",
        },
        "healthcheck": {
            "test": ["CMD-SHELL", "pg_isready -U ${OSPREY_POSTGRES_USER:-osprey}"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 12,
        },
    },
    # ADR-114 Amendment 9 point 3a: SeaweedFS in one process, its S3 face on 8333. Its defaults
    # (8 volumes, 30 GiB each, seven grown per bucket) ran out of volumes by the third bucket when
    # probed; these settings are the ones the object-store suites pass with. The `MINIO_*` names
    # the services read are kept (`harness/apply.py`'s `object_store_lines`).
    "objectstore": {
        "command": [
            "server",
            "-s3",
            "-dir=/data",
            "-s3.port=8333",
            "-volume.max=1000",
            "-master.volumeSizeLimitMB=1024",
            "-master.volumePreallocate=false",
        ],
        "environment": {
            "AWS_ACCESS_KEY_ID": "${OSPREY_MINIO_USER:-ospreyflow}",
            "AWS_SECRET_ACCESS_KEY": "${OSPREY_MINIO_PASSWORD:?set in the deployment env file}",
            "WEED_MASTER_VOLUME_GROWTH_COPY_1": "1",
        },
        # A named volume: MinIO's data was on an anonymous one, emptied by a `down` and `up`.
        "volumes": ["objectstore-data:/data"],
        "healthcheck": {
            "test": ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8333/healthz"],
            "interval": "5s",
            "timeout": "5s",
            "retries": 30,
        },
    },
    # ADR-114 decision 9: the analytics store a cluster of Conduits shares. Its password is minted
    # at apply time (`harness/apply.py`'s `analytics_secret_lines`), never written here.
    "clickhouse": {
        "environment": {
            "CLICKHOUSE_USER": "osprey",
            "CLICKHOUSE_PASSWORD": "${OSPREY_CLICKHOUSE_PASSWORD:?set in the deployment env file}",
        },
        "volumes": ["clickhouse-data:/var/lib/clickhouse"],
        # ClickHouse's own recommendation; it warns at start with the default limit.
        "ulimits": {"nofile": {"soft": 262144, "hard": 262144}},
        "healthcheck": {
            "test": ["CMD", "wget", "-q", "-O", "/dev/null", "http://localhost:8123/ping"],
            "interval": "5s",
            "timeout": "5s",
            "retries": 20,
        },
    },
    "opensearch": {
        "environment": {
            "discovery.type": "single-node",
            "DISABLE_SECURITY_PLUGIN": "true",
            # OpenSearch's own default heap is a quarter of the host's memory, which on a 10GiB VM
            # is 2.5GiB for a single-node search index nothing has written to yet.
            "OPENSEARCH_JAVA_OPTS": "-Xms512m -Xmx512m",
        },
    },
    "arcadedb": {
        "environment": {
            # ADR-101: the adapter's Gremlin is Groovy (bound variables, closures); 26.10.1's
            # default grammar parser refuses it, and runs Groovy only for `root`, as we connect.
            "JAVA_OPTS": "-Darcadedb.server.rootPassword=${OSPREY_ARCADEDB_PASSWORD:?} "
            "-Darcadedb.gremlin.engine=groovy",
            # **An explicit heap, not JVM ergonomics.** Unset, this image's heap is ~25% of the
            # memory Docker exposes to the container — about 2GiB on a 10GiB VM — and the HMP
            # fixture's graph side does not fit in it: the seeded golden path died on
            # `java.lang.OutOfMemoryError: Java heap space`, surfacing to the seed as ArcadeDB
            # error 500 "Error in execution in lock", which names neither memory nor the heap.
            #
            # `deploy/compose/dev.yaml` had already measured this and raised its own heap to
            # `-Xms1G -Xmx6G` in Phase 5 for exactly this fixture. The renderer did not carry it
            # over, so a rendered deployment was strictly worse-configured than the dev stack it
            # replaces, on a value this repository had already paid to learn. Overridable, like
            # every other tunable in the generated env file.
            # Round 13bb: the value itself now comes from `harness/profiles.py`, derived from
            # the profile's own memory floor, because this literal and `deploy/compose/dev.yaml`'s
            # had drifted apart and both were a 10GiB-VM-era 6G that a full `make test-all`
            # OOM'd — that module's docstring has the server's own log line.
            "ARCADEDB_OPTS_MEMORY": (
                "${OSPREY_ARCADEDB_HEAP:-" + arcadedb_java_memory_opts() + "}"
            ),
        },
        "healthcheck": {
            # Not `/dev/tcp`: that is a bash builtin and `CMD-SHELL` runs `/bin/sh`, where the check
            # failed every time with "cannot create /dev/tcp/...: Directory nonexistent". And not
            # `curl` since ADR-101: 26.10.1's image has none (`curl: not found`, so the store never
            # reported healthy); it has busybox `wget`.
            "test": [
                "CMD-SHELL",
                "wget -q -O /dev/null http://127.0.0.1:2480/api/v1/ready || exit 1",
            ],
            "interval": "10s",
            "timeout": "5s",
            "retries": 18,
            "start_period": "20s",
        },
    },
    "valkey": {
        # ADR-124 Amendment 4: the working set's access index is a few keys beside the bodies, and
        # what a reader is shown is computed from them, so no key may be evicted on its own under
        # memory pressure; a full Valkey refuses a write instead, which an operator can see.
        "command": ["valkey-server", "--maxmemory-policy", "noeviction"],
        "healthcheck": {
            "test": ["CMD", "valkey-cli", "ping"],
            "interval": "10s",
            "timeout": "3s",
            "retries": 10,
        },
    },
    # **The model tier, made real — round 13cda.** This service was rendered as a bare
    # `ollama/ollama` container: no model pull, no healthcheck, no volume. So a rendered
    # deployment had an Ollama with nothing in it, and `04_VAULT_BACKEND.md` §4's "local-lite:
    # LLM + VLM, quantised" was true of the image and of nothing else. Extraction failed before
    # reaching it (no proxy at all — see `litellm` below), which is why the empty model store went
    # unnoticed underneath that.
    #
    # The command, healthcheck and volume are `deploy/compose/dev.yaml`'s own, which have pulled
    # and digest-verified these three models on every developer machine for weeks. ADR-020's
    # manifest check travels with them: a moved upstream tag fails the container loudly rather
    # than silently changing which weights a deployment runs.
    "ollama": {
        "entrypoint": ["/bin/sh", "-c"],
        "command": [_OLLAMA_PULL_SCRIPT],
        "volumes": ["ollama-models:/root/.ollama"],
        # **No healthcheck, deliberately — and this is a correction to my own first attempt.**
        #
        # Gating readiness on the pull made `apply` wait for it. Measured: Floor A went from
        # 9m40s to **1h43m**, because `tests/harness/test_apply_env.py` applies ten deployments
        # and its teardown destroys the model volume each time, so every apply re-downloaded
        # ~2.2GB at this link's 673 KB/s while `--wait` blocked. A CI gate cannot cost that, and
        # the cost is not the product's — it is an artefact of waiting.
        #
        # So the models are still pulled and still digest-verified (ADR-020), on a volume that
        # persists for any deployment not deliberately torn down; the deployment simply does not
        # *wait* for them. **The disclosed cost:** `apply` reports ready while the first pull is
        # still running, and extraction fails until it completes — `05_DEPLOYMENT.md` §2.1.1
        # says so and tells an operator how to watch it.
    },
    # `04_VAULT_BACKEND.md` §4's own diagram: the Conduit reaches every model through this one
    # OpenAI-compatible endpoint, never Ollama directly, so swapping a model is a config edit
    # rather than a code change. `litellm.yaml` is rendered beside this compose file.
    "litellm": {
        "command": ["--config", "/app/config.yaml", "--port", "4000"],
        "volumes": ["./litellm.yaml:/app/config.yaml:ro"],
        "environment": {
            "LITELLM_MASTER_KEY": "${" + GATEWAY_MASTER + ":?set in the deployment env file}",
            "LITELLM_SALT_KEY": "${" + GATEWAY_SALT + ":?set in the deployment env file}",
            # ADR-114 Amendment 7: the price list is read from the image, not GitHub (measured: it
            # tried at every start).
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        },
        # **`service_started`, not `service_healthy`** — `ollama` has no healthcheck by design
        # (see its own comment: waiting for the model pull cost Floor A ten times its runtime).
        # The proxy only needs the server process reachable; a request for a model still being
        # pulled fails at that request, which is the disclosed window, rather than blocking the
        # whole deployment from starting.
        "depends_on": {"ollama": {"condition": "service_started"}},
        "healthcheck": {
            "test": [
                "CMD",
                "python3",
                "-c",
                "import urllib.request; "
                "urllib.request.urlopen('http://localhost:4000/health/liveliness')",
            ],
            "interval": "5s",
            "timeout": "5s",
            "retries": 20,
            # The proxy starts fast, but `depends_on: ollama healthy` already absorbed the model
            # pull, so this only covers its own boot.
            "start_period": "30s",
        },
    },
    "keycloak": {
        # **Production mode, its data in the deployment's Postgres** (ADR-114 decision 12,
        # Amendment 5): an account survives a restart. Measured on Keycloak 26.0.8 before it was
        # written: `start` imports the realm once ("already exists. Import skipped" afterwards),
        # keeps a user created later across a recreated container, and keeps the bootstrap admin of
        # its first start — a new bootstrap password on a later start is refused. So the admin
        # password, like Postgres's own, is never minted again while the database exists:
        # `ospreyflow uninstall` removes both, and moving a deployment's data forward is `update`'s
        # (stage B5). `--features=token-exchange` is not optional: without it the exchange grant
        # does not exist and every principal resolution for a watch owner fails.
        "command": ["start", "--import-realm", "--features=token-exchange"],
        "volumes": [
            "./realm.json:/opt/keycloak/data/import/realm.json:ro",
            # The sign-in page's look (`harness/keycloak_theme.py`), written beside this file by
            # `apply`. Mounted **beside** Keycloak's own themes: a mount onto `/opt/keycloak/themes`
            # itself would hide them and leave the realm with no sign-in page at all.
            "./keycloak-theme/osprey:/opt/keycloak/themes/osprey:ro",
        ],
        "depends_on": {
            "postgres": {"condition": "service_healthy"},
            "keycloak-db": {"condition": "service_completed_successfully"},
        },
        "environment": {
            "KC_BOOTSTRAP_ADMIN_USERNAME": "${OSPREY_KEYCLOAK_ADMIN:-admin}",
            "KC_BOOTSTRAP_ADMIN_PASSWORD": "${OSPREY_KEYCLOAK_ADMIN_PASSWORD:?set in the "
            "deployment env file}",
            # Keycloak 26 serves health on a separate management port and only when asked.
            "KC_HEALTH_ENABLED": "true",
            "KC_DB": "postgres",
            "KC_DB_URL": "jdbc:postgresql://postgres:5432/keycloak",
            # ADR-114 Amendment 43: Keycloak's share of PostgreSQL, the product's number.
            "KC_DB_POOL_MAX_SIZE": str(KEYCLOAK_POOL_MAX),
            "KC_DB_USERNAME": "keycloak",
            "KC_DB_PASSWORD": "${OSPREY_KEYCLOAK_DB_PASSWORD:?set in the deployment env file}",
        },
        "healthcheck": {
            # Keycloak's image carries no shell utilities to curl with; its own bundled JRE does.
            "test": [
                "CMD-SHELL",
                "exec 3<>/dev/tcp/127.0.0.1/9000 && echo -e 'GET /health/ready HTTP/1.1\r\n"
                "Host: localhost\r\nConnection: close\r\n\r\n' >&3 && cat <&3 | grep -q UP",
            ],
            "interval": "10s",
            "timeout": "5s",
            "retries": 30,
            "start_period": "30s",
        },
    },
}


_SERVICE_EXTRAS["ner"] = {
    # The image is Python and nothing else; its own interpreter asks the recogniser it is ready,
    # which loads the model, so a healthy `ner` answers at once.
    "healthcheck": {
        "test": [
            "CMD",
            "python",
            "-c",
            "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=5)",
        ],
        "interval": "15s",
        "timeout": "10s",
        "retries": 20,
        "start_period": "60s",
    },
}


def compose_services(config: OspreyConfig, images: Sequence[ServiceImage]) -> dict[str, Any]:
    """Every service the deployment runs, as compose stanzas: what the compose file is written from,
    and what the cluster's chart values are translated from (`harness/cluster.py`), so a laptop and
    a cluster cannot disagree about what a service is."""
    services: dict[str, Any] = {}
    for entry in images:
        # A run-once batch job that exits is not a crash. `unless-stopped` restarts it forever,
        # which looks exactly like a crash loop in `docker ps` and never becomes healthy — found
        # running the golden path, where `ingest` sat in `Restarting (2)`.
        restart = "no" if entry.service == "ingest" else "unless-stopped"
        service: dict[str, object] = {"restart": restart}
        if entry.service == "ingest":
            # A compose profile, so `up` does not start it at all. The batch loader takes required
            # arguments and exits 2 without them, and `up --wait` reads any non-zero exit as a
            # failed start — so a job behaving exactly as designed failed the whole deploy. It is
            # run on demand (`--profile batch`, or `compose run`), which is what a run-once job is.
            service["profiles"] = ["batch"]
        service["image"] = entry.image
        if entry.building:
            # This render builds from source rather than pulling — `image:` is still set, so the
            # built image has a stable local tag that `versions.lock` can name and that a later
            # `docker compose up` resolves without rebuilding. `dockerfile` is relative to
            # `context`, which is the repository root, so it stays repo-root-relative.
            service["build"] = {"context": entry.build_context, "dockerfile": entry.dockerfile}
        if entry.owned:
            # Without this the deployment's own generated environment file is written and then
            # never reaches a container: the Conduit fail-fasts on a missing `OIDC_JWKS_URL` and
            # restarts forever. Found running the golden path. Needed whether this owned service
            # is built or pulled — an identity property, not a build-mode one.
            service["env_file"] = ["deployment.env"]

        # The Conduit reaches its IdP's JWKS endpoint and its three stores *during startup* and
        # fail-fasts if any is unreachable — deliberately, per `services/api/config.py`. So it must
        # start after they are healthy, not merely after they are created. Found running the golden
        # path: with no ordering it died on `httpx.ConnectError` reaching a Keycloak that was still
        # importing its realm, and then restarted forever.
        if entry.service == "workspace":
            # The map's place names: glyph files kept with the basemap, in the tiles folder's
            # `fonts/` (`scripts.fetch_basemap_glyphs`), served by the workspace's nginx at
            # `/fonts/`, the bundled style's `glyphs` URL. Read-only. An empty folder is fine: the
            # Glass probes for the glyphs and draws the map unlabelled without them.
            service["volumes"] = [
                f"{host_folder_source(config.components.storage.tiles)}/fonts:{GLYPHS_CONTAINER_PATH}:ro",
                # ADR-114 Amendment 4 decision 5: where the identity provider is, read by the Glass
                # at start — so the one bundle serves every deployment.
                "./glass.json:/usr/share/nginx/html/deployment.json:ro",
            ]
        if entry.service == "api":
            # **Round 13bf — the recipe repository, on the persistent volume.** Publishing writes
            # the recipe to version control (`09_INGEST_STUDIO.md` §6); without this the Conduit
            # falls back to `/app`, which is the image's own code directory, is not a git
            # repository, and is rebuilt on every deploy. Set here rather than defaulted in the
            # Conduit because only the renderer knows where this deployment's data root is.
            existing_environment = service.get("environment")
            api_environment: dict[str, object] = (
                dict(existing_environment) if isinstance(existing_environment, dict) else {}
            )
            api_environment["OSPREY_RECIPE_REPO_ROOT"] = (
                f"{config.components.storage.data}/{RECIPE_REPO_DIRNAME}"
            )
            # ADR-147 decision 1: the maps file and the map key file, on their own volume.
            api_environment["OSPREY_MAP_SETTINGS_DIR"] = MAP_SETTINGS_PATH
            # **Round 13cda — the Conduit could not reach a model at all.**
            # `adapters/model_litellm/client.py`'s `LiteLLMConfig.from_env` defaults to
            # `localhost:4000`, which inside the Conduit's own container is the Conduit. Every
            # extraction therefore returned a bare 500 in every rendered deployment, measured:
            # `httpx.ConnectError: All connection attempts failed`. With no `litellm` service
            # rendered either, `09_INGEST_STUDIO.md` §4's whole review queue was unreachable.
            api_environment["LITELLM_HOST"] = "litellm"
            api_environment["LITELLM_PORT"] = "4000"
            api_environment["LITELLM_API_KEY"] = "${" + GATEWAY_MASTER + ":?set in the env file}"
            # ADR-135 Amendment 2 decision 2: the models file, on its own volume.
            api_environment["OSPREY_MODEL_SETTINGS_DIR"] = MODEL_SETTINGS_PATH
            # ADR-095 Amendment 2: where to ask whether the models have arrived (`/v1/readiness`).
            api_environment["OSPREY_OLLAMA_URL"] = "http://ollama:11434"
            # ADR-098 decision 2: the fast recogniser. Not in `depends_on` below: without it the
            # rest of the Glass still works, and Extract entities says so and offers the model.
            api_environment["OSPREY_RECOGNISER_URL"] = "http://ner:8000"
            service["environment"] = api_environment
            # The Conduit reads `osprey.yaml` at startup for its map-provider registry, and the
            # image does not contain it — the Dockerfile copies `packages/` and `services/` only,
            # deliberately, because a deployment's configuration is not part of its image.
            #
            # **Mounted from beside the compose file itself, not "the repository root, three
            # levels up".** That was this line's own reading until a real `--images`
            # install-from-bundle exit test found it: `BUILD_CONTEXT_FROM_OUTPUT_DIR` encodes
            # this *repository's own* convention — `deploy/generated/<profile>/` sits exactly
            # three directories below the checkout that renders it — and reusing it here
            # silently assumed every deployment is rendered from inside that same checkout, at
            # that same depth. A bundle recipient's own `--out-root` has no such tree at all:
            # `docker compose up` failed with `IsADirectoryError: ... 'osprey.yaml'` because
            # Docker creates an empty directory for a bind-mount source that does not exist, and
            # nothing upstream of it does. `harness.apply` now copies the real config beside the
            # rendered `compose.yaml` (`out_dir / "osprey.yaml"`), so this mount needs nothing
            # about where that config file originally lived.
            service["volumes"] = [
                "./osprey.yaml:/app/osprey.yaml:ro",
                # Amendment 8: the update notice, written on the host by `update --check`.
                f"./state:{STATE_CONTAINER_PATH}:ro",
                # **The declared volumes were mounted by nothing.** `osprey-data` and
                # `osprey-staging` were emitted under `volumes:` from the first render and no
                # service ever used them, so the Conduit's analytics DuckDB lived in the container
                # layer and died with the container: `docker compose down` discarded every seeded
                # event, and Stage 2 §4's backup would have had nothing to copy. Found doing the
                # seeded run, which needs the seed container and the Conduit to reach *the same*
                # file. A declared-but-unmounted volume is the shape rule 12 names — configuration
                # that reads as correct and is exercised by nothing; `test_render.py`'s
                # `test_every_declared_volume_is_mounted_by_some_service` is the case that fails
                # if it recurs.
                f"osprey-data:{config.components.storage.data}",
                # **Owner ruling R6 — read-only, and read-only is the point.** The Conduit reads
                # evidence here and never writes it: whatever puts files on the host owns the
                # contents, and a writable mount would let a compromised Conduit alter the source
                # material it is reading from. Rendered for every profile, so an analyst always
                # has a door; `05_DEPLOYMENT.md` §3 and `DEMO_GUIDE.md` name the folder.
                f"{host_folder_source(config.components.storage.ingest)}:{INGEST_CONTAINER_PATH}:ro",
                # **ADR-067 — the one writable door, laid over the read-only root.** Browser upload
                # needs the Conduit to write somewhere; only this sub-folder is writable, so the
                # evidence an operator put in the root above is still not. Docker lets a nested
                # bind mount be writable inside a read-only parent. Not run against Docker from the
                # session that wrote it: on Linux the host folder's owner must let the container's
                # user write (ADR-067 names this).
                f"{host_folder_source(config.components.storage.ingest)}/{INGEST_UPLOAD_SUBDIR}:"
                f"{INGEST_CONTAINER_PATH}/{INGEST_UPLOAD_SUBDIR}",
                # The built basemap, read-only, at the path a map provider's `source` names. See
                # `StorageRoots.tiles`.
                f"{host_folder_source(config.components.storage.tiles)}:{TILES_CONTAINER_PATH}:ro",
                # ADR-147 decision 3: a basemap built in the Conduit is written here alone, a
                # writable door laid over the read-only root as ADR-067's upload door is.
                f"{host_folder_source(config.components.storage.tiles)}/{TILES_BUILT_SUBDIR}:"
                f"{TILES_CONTAINER_PATH}/{TILES_BUILT_SUBDIR}",
                # ADR-147 decision 1: the maps file and the map key file, the Conduit's alone.
                f"map-settings:{MAP_SETTINGS_PATH}",
            ]
            service["depends_on"] = {
                dependency: {"condition": "service_healthy"}
                for dependency in (
                    "keycloak",
                    "arcadedb",
                    "valkey",
                    "postgres",
                    "litellm",
                    *(("clickhouse",) if _uses_clickhouse(config) else ()),
                )
            }
        # **Nothing but the proxy publishes a port** (ADR-114 Amendment 7): a published port needs a
        # network with a route out (measured on Docker Desktop), so the graph store's loopback door
        # and the Conduit's opt-in one (`network.expose_conduit`, the owner's decision of 25
        # September 2026) are served through the proxy (`harness/site.py`'s `loopback_doors`).
        if entry.service == "ingest":
            service["volumes"] = [f"osprey-staging:{config.components.storage.staging}"]
        service.update(_SERVICE_EXTRAS.get(entry.service, {}))
        if entry.service == "proxy":
            service.update(proxy_service(config))
        if config.resources.any and entry.service in ("arcadedb", "opensearch", "postgres"):
            # ADR-114 Amendment 33 decision 6: the stores sized to the server, in each store's own
            # definition — never in `deployment.env`, which every owned service reads whole, so a
            # resize restarts the three stores alone.
            sized = store_memory(config.resources)
            if entry.service == "arcadedb":
                service["environment"] = {
                    **cast(dict[str, str], service["environment"]),
                    "ARCADEDB_OPTS_MEMORY": (
                        "${OSPREY_ARCADEDB_HEAP:-" + sized.graph_java_opts + "}"
                    ),
                }
            elif entry.service == "opensearch":
                service["environment"] = {
                    **cast(dict[str, str], service["environment"]),
                    "OPENSEARCH_JAVA_OPTS": sized.search_java_opts,
                }
            else:
                service["command"] = postgres_command(sized)
        elif entry.service == "postgres":
            # ADR-114 Amendment 43: the connections the product's services may hold, every profile.
            service["command"] = postgres_command()
        if entry.service == "keycloak":
            # ADR-114 Amendment 4 decision 4: one issuer, whichever door a token came through —
            # the browser's, by name through the proxy, or the services' inside the network.
            service["environment"] = {
                **_SERVICE_EXTRAS["keycloak"]["environment"],  # type: ignore[dict-item]
                "KC_HOSTNAME": sites(config).identity,
                "KC_HOSTNAME_BACKCHANNEL_DYNAMIC": "true",
                "KC_PROXY_HEADERS": "xforwarded",
                "KC_HTTP_ENABLED": "true",
            }
            tls = config.network.tls
            if config.profile is Profile.SMALL and tls is not None and tls.ca:
                # ADR-114 Amendment 33 decision 4: the organisation's CA in Keycloak's truststore,
                # so an identity provider on the organisation's own CA is trusted on the back
                # channel (its discovery, keys and token endpoint). Keycloak keeps the JVM's own
                # trusted roots beside it, which a provider on the internet (Entra ID) needs.
                environment = dict(cast(dict[str, str], service["environment"]))
                environment["KC_TRUSTSTORE_PATHS"] = KEYCLOAK_TRUSTSTORE_PATH
                service["environment"] = environment
                service["volumes"] = [
                    *cast(list[str], service["volumes"]),
                    f"{tls.ca}:{KEYCLOAK_TRUSTSTORE_PATH}:ro",
                ]
        if entry.service == "ollama":
            # ADR-114 Amendment 7: the server that reads case content has no route out; the
            # weights are fetched by `ollama-models` below, into the volume it reads.
            service["entrypoint"] = ["/bin/ollama"]
            service["command"] = ["serve"]
            # Two servers share the model volume: this one, and `ollama-models`' while it pulls. A
            # server prunes unreferenced blobs when it starts, a download's `-partial` file among
            # them, so this one starting or restarting mid-pull failed the pull ("rename
            # ...-partial ...: no such file or directory", a user's install, 15 October 2026). It
            # never pulls, so it never needs to prune.
            service["environment"] = {"OLLAMA_NOPRUNE": "1"}
            if config.resources.gpu == "nvidia":
                # ADR-135 Amendment 1 decision 2: this server alone reserves every NVIDIA GPU; the
                # same pinned image carries CUDA. `ollama-models` only downloads, so it has none.
                service["deploy"] = {"resources": {"reservations": {"devices": [
                    {"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}
                ]}}}  # fmt: skip
                # As measured, 4 November 2026 (Amendment 1): the 14b at its 32k context held the
                # KV cache at full precision and ran 15%/85% CPU/GPU (18 GB, 9-11 s an answer);
                # with the cache at q8_0, which needs flash attention, it ran 100% on a 16 GB card
                # (14 GB, 3.3-3.6 s). An idle model was unloaded after five minutes, and the next
                # question waited 56 s for it to load again: on a GPU it stays loaded (the owner,
                # 4 November). Without a GPU nothing changes.
                service["environment"] = {
                    **cast(dict[str, str], service["environment"]),
                    "OLLAMA_FLASH_ATTENTION": "1",
                    "OLLAMA_KV_CACHE_TYPE": "q8_0",
                    "OLLAMA_KEEP_ALIVE": "-1",
                }
            services["ollama-models"] = _model_download_step(
                str(service["image"]),
                volume="ollama-models:/root/.ollama",
                entrypoint=["/bin/sh", "-c"],
                command=[render_ollama_download_script(config)],
            )
        if entry.service == "whisper":
            # The same for speech: its model downloaded once, read offline.
            service["volumes"] = [f"whisper-models:{_HF_CACHE}"]
            service["environment"] = {"HF_HUB_OFFLINE": "1"}
            service["depends_on"] = {
                "whisper-models": {"condition": "service_completed_successfully"}
            }
            services["whisper-models"] = _model_download_step(
                str(service["image"]),
                volume=f"whisper-models:{_HF_CACHE}",
                entrypoint=["/bin/sh", "-c"],
                command=[
                    f"huggingface-cli download {config.models.transcription} "
                    f"&& chown -R 1000:1000 {_HF_CACHE}"
                ],
                user="0",
            )
        services[entry.service] = service
    # ADR-111 Amendment 2: report-sync (the Conduit's own image) and Superset, when switched on.
    api = next(entry for entry in images if entry.service == "api")
    services.update(
        reporting_services(
            config, api_image=api.image, building=api.building, build_context=api.build_context
        )
    )
    # ADR-135 Amendment 6 (P12 part 2): Laurium's service, when it is the extraction engine.
    services.update(
        laurium_services(
            config, api_image=api.image, building=api.building, build_context=api.build_context
        )
    )
    _keys_for_the_gateway_alone(config, services)
    _connection_secrets_for_the_conduit_alone(config, services)
    _gateway_database(config, services)
    if "keycloak" in services and ("postgres" in services or config.external.postgres is not None):
        services["keycloak-db"] = _keycloak_database_step(config)
    if config.external.postgres is not None and "keycloak" in services:
        # Not rendered on the cloud-platform profile, whose people sign in with Entra ID.
        services["keycloak"]["environment"]["KC_DB_URL"] = _keycloak_jdbc_url(config)
    _drop_absent_dependencies(services)
    _place_on_networks(config, services)
    return services


def _render_compose(config: OspreyConfig, images: Sequence[ServiceImage]) -> str:
    services = compose_services(config, images)
    stores = name_the_stores(services)
    document = {
        # ADR-132 Amendment 1: `deployment.name`, else `osprey-<profile>` as before.
        "name": compose_project(config),
        "services": services,
        "volumes": {
            "osprey-data": {"driver": "local"},
            "osprey-staging": {"driver": "local"},
            # Round 13cda: without this the ~2.2GB model pull repeats on every `up`.
            "ollama-models": {"driver": "local"},
            # ADR-147 decision 1: the maps file and the map key file, the Conduit's alone.
            **({"map-settings": {"driver": "local"}} if "api" in services else {}),
            **({"whisper-models": {"driver": "local"}} if "whisper" in services else {}),
            # ADR-135 Amendment 2 decision 2: the models file, the Conduit's alone.
            **({"model-settings": {"driver": "local"}} if "litellm-db" in services else {}),
            **({"objectstore-data": {"driver": "local"}} if "objectstore" in services else {}),
            # ADR-114 Amendment 33 decision 3: with the organisation's certificate nothing is
            # obtained, so there is nothing for Caddy to keep.
            **(
                {"proxy-data": {"driver": "local"}}
                if sites(config).scheme == "https" and config.network.tls is None
                else {}
            ),
            **({"clickhouse-data": {"driver": "local"}} if _uses_clickhouse(config) else {}),
            # ADR-114 Amendment 35: each store's own.
            **stores,
        },
        # ADR-114 Amendment 7: `osprey` has no route out; `egress` only for what needs one.
        "networks": {"osprey": {"internal": True}, "egress": {}},
    }
    body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
    return _comment_block(_BANNER, "#") + body


@dataclass(frozen=True)
class StoreVolume:
    """A store's data path, kept in a named volume of its own (ADR-114 Amendment 35)."""

    service: str
    volume: str
    path: str


#: **The stores' named volumes** (ADR-114 Amendment 35; build order step 26). Before them
#: PostgreSQL, ArcadeDB and Valkey kept their data in the anonymous volumes their images' `VOLUME`
#: lines make, and OpenSearch in its container (as found on the first server, 4 November 2026):
#: kept when Compose recreates a container, but a new container gets new, empty ones. ArcadeDB's
#: `backups/`, `log/` and `replication/` stay on the image's anonymous volumes: nothing a restart
#: needs.
#: `tests/harness/test_store_volumes.py::test_every_store_has_its_named_volume_on_lite_and_small` is
#: what fails if a row goes. An existing deployment's data is moved by `harness/store_volumes.py`.
STORE_VOLUMES: tuple[StoreVolume, ...] = (
    StoreVolume("postgres", "postgres-data", "/var/lib/postgresql/data"),
    StoreVolume("arcadedb", "arcadedb-databases", "/home/arcadedb/databases"),
    StoreVolume("arcadedb", "arcadedb-config", "/home/arcadedb/config"),
    StoreVolume("valkey", "valkey-data", "/data"),
    StoreVolume("opensearch", "opensearch-data", "/usr/share/opensearch/data"),
)


def name_the_stores(services: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Each store the deployment runs given its named volumes (compose only: a cluster's stores
    keep their claims, `harness/cluster.py`), and the top-level `volumes:` entries they need."""
    declared: dict[str, dict[str, str]] = {}
    for row in STORE_VOLUMES:
        service = services.get(row.service)
        if not isinstance(service, dict):
            continue
        service["volumes"] = [*(service.get("volumes") or []), f"{row.volume}:{row.path}"]
        declared[row.volume] = {"driver": "local"}
    return declared


#: The Postgres image: the deployment's own server, and the client its Keycloak step runs.
POSTGRES_IMAGE = "postgres:16.4"

#: Where the speech server keeps its downloaded models (measured: speaches runs as uid 1000).
_HF_CACHE = "/home/ubuntu/.cache/huggingface"


def _model_download_step(
    image: str, *, volume: str, entrypoint: list[str], command: list[str], user: str | None = None
) -> dict[str, Any]:
    """A one-shot step that fetches model weights into a volume and exits (ADR-114 Amendment 7):
    the only part of model serving with a route out, and it never sees case content."""
    step: dict[str, Any] = {
        "image": image,
        "entrypoint": entrypoint,
        "command": command,
        "volumes": [volume],
        "restart": "no",
    }
    if user is not None:
        step["user"] = user
    return step


#: Where Keycloak reads the organisation's CA (`network.tls.ca`), mounted read-only.
KEYCLOAK_TRUSTSTORE_PATH = "/opt/keycloak/conf/truststores/organisation-ca.pem"


def egress_needs(config: OspreyConfig) -> set[str]:
    """The services that reach outside the deployment, each because a configured feature needs it
    (ADR-114 Amendment 7; 04 §4). Everything else is on the internal network alone."""
    needs = {"proxy", "ollama-models", "whisper-models"}
    external = config.external
    if external.postgres is not None:
        # 05 §3a: everything that reads Postgres reaches the managed server.
        needs |= {"api", "keycloak", "keycloak-db", "report-sync", "superset"}
    if external.object_store is not None:
        needs |= {"api", "ingest"}  # staging, site images, the tile cache, media: the cloud's S3
    if external.media is not None:
        needs.add("api")  # media on Blob
    if config.models.enabled_providers:
        needs.add("litellm")  # the client's own model providers (ADR-135)
    if config.mail is not None or config.governance.organisation_sign_in:
        needs.add("keycloak")  # mail for invitations; an organisation's sign-in
    if any(
        p.proxy != "none" and (p.source or "").startswith(("http://", "https://"))
        for p in (config.map.providers if config.map is not None else [])
    ):
        needs.add("api")  # map tiles fetched through the Conduit's tile proxy
    return needs


def _place_on_networks(config: OspreyConfig, services: dict[str, Any]) -> None:
    reaching_out = egress_needs(config)
    for name, service in services.items():
        service["networks"] = ["osprey", "egress"] if name in reaching_out else ["osprey"]


#: Keycloak's role and database on the deployment's Postgres, made before Keycloak starts and run at
#: every `up`: created when missing, and the role's password set from the env file each time, so a
#: password the file changes reaches the role (ADR-114 Amendment 5). psql's own `:'pw'` quoting, so
#: no password is ever spliced into SQL by the shell.
_KEYCLOAK_DATABASE_SQL = (
    "SELECT 'CREATE ROLE keycloak LOGIN' "
    "WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak')\\gexec\n"
    "ALTER ROLE keycloak WITH LOGIN PASSWORD :'pw';\n"
    "SELECT 'CREATE DATABASE keycloak OWNER keycloak' "
    "WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\\gexec\n"
)


def _keycloak_database_step(config: OspreyConfig) -> dict[str, object]:
    # A quoted heredoc: the SQL reaches psql exactly as written, quotes and `\\gexec` included.
    # `$$` is compose's escape for a `$` the container's own shell expands. On a managed server
    # (05 §3a) the same step runs against its host, over TLS; its login needs CREATEROLE/CREATEDB.
    managed = config.external.postgres
    host, port = (managed.host, managed.port) if managed is not None else ("postgres", 5432)
    script = (
        f'psql -h {host} -p {port} -U "$$OSPREY_POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 '
        "-v pw=\"$$OSPREY_KEYCLOAK_DB_PASSWORD\" <<'SQL'\n" + _KEYCLOAK_DATABASE_SQL + "SQL\n"
    )
    step: dict[str, object] = {
        "restart": "no",
        "image": POSTGRES_IMAGE,
        "entrypoint": ["sh", "-c"],
        "command": [script],
        "environment": {
            "OSPREY_POSTGRES_USER": "${OSPREY_POSTGRES_USER:-osprey}",
            "PGPASSWORD": "${OSPREY_POSTGRES_PASSWORD:?set in the deployment env file}",
            "OSPREY_KEYCLOAK_DB_PASSWORD": "${OSPREY_KEYCLOAK_DB_PASSWORD:?set in the env file}",
            **({"PGSSLMODE": managed.sslmode} if managed is not None else {}),
        },
        "depends_on": {"postgres": {"condition": "service_healthy"}},
    }
    return step


#: The gateway's role and database (ADR-135 Amendment 2 decision 3), made as Keycloak's are: its
#: own, so its start-up schema diff (measured) can touch nothing of the Conduit's, and the
#: Conduit's login cannot read the sealed keys.
_GATEWAY_DATABASE_SQL = (
    "SELECT 'CREATE ROLE litellm LOGIN' "
    "WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'litellm')\\gexec\n"
    "ALTER ROLE litellm WITH LOGIN PASSWORD :'pw';\n"
    "SELECT 'CREATE DATABASE litellm OWNER litellm' "
    "WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')\\gexec\n"
)


def _gateway_database(config: OspreyConfig, services: dict[str, Any]) -> None:
    """The gateway's database, its encryption key and master key (ADR-135 Amendment 2 decision 3),
    each secret blanked in every other service that reads the env file whole; the master key
    reaches the Conduit alone besides, which calls the admin API with it."""
    if "litellm" not in services or (
        "postgres" not in services and config.external.postgres is None
    ):
        return
    managed = config.external.postgres
    host, port = (managed.host, managed.port) if managed is not None else ("postgres", 5432)
    query = f"?sslmode={managed.sslmode}" if managed is not None else ""
    gateway = services["litellm"]
    gateway["environment"] = {
        **dict(gateway.get("environment") or {}),
        "DATABASE_URL": (
            "postgresql://litellm:${" + GATEWAY_DB_PASSWORD + ":?set in the deployment env file}"
            f"@{host}:{port}/litellm{query}"
        ),
        "STORE_MODEL_IN_DB": "True",
    }
    gateway["depends_on"] = {
        **dict(gateway.get("depends_on") or {}),
        "litellm-db": {"condition": "service_completed_successfully"},
    }
    script = (
        f'psql -h {host} -p {port} -U "$$OSPREY_POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 '
        + '-v pw="$$'
        + GATEWAY_DB_PASSWORD
        + '" <<'
        + "'SQL'\n"
        + _GATEWAY_DATABASE_SQL
        + "SQL\n"
    )
    services["litellm-db"] = {
        "restart": "no",
        "image": POSTGRES_IMAGE,
        "entrypoint": ["sh", "-c"],
        "command": [script],
        "environment": {
            "OSPREY_POSTGRES_USER": "${OSPREY_POSTGRES_USER:-osprey}",
            "PGPASSWORD": "${OSPREY_POSTGRES_PASSWORD:?set in the deployment env file}",
            GATEWAY_DB_PASSWORD: "${" + GATEWAY_DB_PASSWORD + ":?set in the env file}",
            **({"PGSSLMODE": managed.sslmode} if managed is not None else {}),
        },
        "depends_on": {"postgres": {"condition": "service_healthy"}},
    }
    if "api" in services:
        api = services["api"]
        api["volumes"] = [*api.get("volumes", []), f"model-settings:{MODEL_SETTINGS_PATH}"]
    if config.profile.value == "cluster":
        return  # the chart blanks them for every workload, its own workers too (`harness.cluster`)
    for name, service in services.items():
        if name in ("litellm", "litellm-db") or "env_file" not in service:
            continue
        environment = dict(service.get("environment") or {})
        environment.update({GATEWAY_SALT: "", GATEWAY_DB_PASSWORD: ""})
        if name != "api":
            environment[GATEWAY_MASTER] = ""
        service["environment"] = environment


def _keycloak_jdbc_url(config: OspreyConfig) -> str:
    managed = config.external.postgres
    assert managed is not None
    return f"jdbc:postgresql://{managed.host}:{managed.port}/keycloak?sslmode={managed.sslmode}"


def _drop_absent_dependencies(services: dict[str, Any]) -> None:
    """A dependency on what the deployment does not run as a container — a cloud's managed
    Postgres or object store (05 §3a) — is no dependency: compose would refuse the file."""
    for service in services.values():
        depends = service.get("depends_on")
        if isinstance(depends, dict):
            kept = {name: rule for name, rule in depends.items() if name in services}
            if kept:
                service["depends_on"] = kept
            else:
                service.pop("depends_on")


def _uses_clickhouse(config: OspreyConfig) -> bool:
    return config.components.analytics_engine.value == "clickhouse"


#: ADR-114 Amendment 8: where the Conduit reads the deployment's `state/` folder (read-only), in
#: which `ospreyflow update --check` writes the update notice.
STATE_CONTAINER_PATH = "/var/lib/osprey/state"


def release_version(config: OspreyConfig) -> str:
    """The deployment's version (Amendment 8 point 1): the release its checkout sits on, else
    `dev-<short commit>`."""
    from harness.release import checkout_version

    source = config.components.source_path
    return checkout_version(Path(source) if source is not None else REPO_ROOT)


def _grading_env(config: OspreyConfig) -> list[str]:
    scheme = config.grading.resolved()
    lines = [f"OSPREY_GRADING_SCHEME={scheme.scheme}"]
    if config.grading.names_a_file:
        lines.append(f"OSPREY_GRADING_GRADES={scheme.model_dump_json()}")
    return lines


def _render_env(config: OspreyConfig) -> str:
    lines = [
        f"OSPREY_PROFILE={config.profile.value}",
        f"OSPREY_RELEASE_VERSION={release_version(config)}",
        f"OSPREY_STATE_DIR={STATE_CONTAINER_PATH}",
        f"OSPREY_GRAPH_STORE={config.components.graph_store.value}",
        f"OSPREY_ANALYTICS_ENGINE={config.components.analytics_engine.value}",
        # ADR-127 Amendment 33: whether a load queues entity resolution afterwards.
        "OSPREY_POST_INGEST_RESOLUTION="
        + ("on" if config.components.post_ingest_resolution else "off"),
        f"OSPREY_SEARCH_BACKEND={config.components.search.value}",
        f"OSPREY_DATA_ROOT={config.components.storage.data}",
        f"OSPREY_STAGING_ROOT={config.components.storage.staging}",
        f"OSPREY_BACKUP_ROOT={config.components.storage.backups}",
        # The *container* path, not `components.storage.ingest`'s host path — the Conduit only
        # ever sees the mount. See `INGEST_CONTAINER_PATH` for why this is carried rather than
        # hard-coded on the other side.
        f"OSPREY_INGEST_ROOT={INGEST_CONTAINER_PATH}",
        # See the `arcadedb` stanza in `_SERVICE_EXTRAS` for why this is explicit rather than left
        # to the JVM's own container ergonomics.
        # A deployment sized to its server (ADR-114 Amendment 33 decision 6) carries its heap in
        # the graph store's own definition instead, so a resize restarts the stores alone.
        *(
            []
            if config.resources.any
            else [f"OSPREY_ARCADEDB_HEAP={arcadedb_java_memory_opts('local-lite')}"]
        ),
        # The analytics DuckDB file, placed *inside* the mounted data root rather than left on
        # `services/api/config.py`'s relative `data/analytics.duckdb` default — which resolves to
        # the container's own working directory, i.e. nowhere that survives the container.
        f"ANALYTICS_DB_PATH={config.components.storage.data}/analytics.duckdb",
        # ADR-114 decision 9: where the Conduit finds ClickHouse. Its password is minted at apply.
        *(
            ["CLICKHOUSE_HOST=clickhouse", "CLICKHOUSE_HTTP_PORT=8123", "CLICKHOUSE_USER=osprey"]
            if _uses_clickhouse(config)
            else []
        ),
        f"OSPREY_IDENTITY_PROVIDER={config.governance.identity_provider}",
        f"OSPREY_HANDLING_SCHEME={config.governance.handling_scheme}",
        # ADR-148 decision 10: the deployment's marking ceiling, the scheme's highest when unset.
        f"OSPREY_HIGHEST_MARKING={highest_marking(config)}",
        f"OSPREY_ONTOLOGY={config.governance.ontology}",
        f"OSPREY_REAL_DATA_EXCEPTIONS={config.governance.real_data_exceptions}",
        f"OSPREY_MODELS_LOCAL_ONLY={'true' if config.models.local_only else 'false'}",
        # ADR-095: the models the Conduit uses for analysts' work, chosen on the Models screen.
        f"OSPREY_EXTRACTION_MODEL={config.extraction_model}",
        f"OSPREY_VISION_MODEL={config.models.vision}",
        f"OSPREY_TRANSCRIPTION_MODEL={config.models.transcription}",
        f"OSPREY_EMBEDDING_MODEL={config.models.embedding}",
        # `06_DECISIONS.md` ADR-050 objection 1's resolution: every rendered deployment verifies
        # audience, not only the two confidential clients this codebase controls. Not a secret —
        # the Conduit's own client id, which `harness/realm.py`'s audience mapper on the Glass
        # client already names — so it belongs in the deterministic render, not apply-time
        # secret-writing. `harness/preflight/oidc_audience.py` fails Launch if this is ever missing.
        f"OIDC_AUDIENCE={CONDUIT_CLIENT_ID}",
        # **The deployment's own origin, and only that** (round 13b). Round 13's closing pass
        # found a rendered deployment carrying no `CORS_ALLOWED_ORIGINS` at all, so the Conduit
        # fell back to its own development default, `http://localhost:5173` — the origin a
        # developer's Vite server uses. Harmless in practice, because the deployed Glass reaches
        # the Conduit same-origin through the workspace's nginx proxy and CORS never applies to
        # it, which is exactly why nothing had noticed; still not something a shipped artefact
        # should carry. `network.public_origin` is the field ADR-050 objection 2 already added
        # for the OIDC redirect: the origin a browser genuinely uses to reach this deployment.
        f"CORS_ALLOWED_ORIGINS={sites(config).glass}",
        # ADR-114 Amendment 4: the addresses, for the tools on the host (not secrets).
        f"OSPREY_GLASS_ORIGIN={sites(config).glass}",
        f"OSPREY_IDENTITY_ORIGIN={sites(config).identity}",
        f"OSPREY_DASHBOARDS_ORIGIN={sites(config).dashboards}",
        # ADR-114 Amendment 5: invitations and resets by the identity provider's emailed link.
        *(["OSPREY_SIGN_IN_EMAIL=true"] if config.mail is not None else []),
        # ADR-112 Amendment 3 (b): the organisation's sign-in, whose refused arrivals Admin ->
        # People can join to an account. Not a secret: its alias, in the address it registers.
        *(
            [f"OSPREY_ORGANISATION_SIGN_IN={config.governance.organisation_sign_in}"]
            if config.governance.organisation_sign_in
            and config.governance.organisation_provider is not None
            else []
        ),
        # ADR-133 ruling 3: a new hotlist's audience in the alert queue, and whether its owner may
        # change it.
        f"OSPREY_HOTLIST_AUDIENCE={config.monitoring.hotlist_audience}",
        "OSPREY_HOTLIST_AUDIENCE_EDITABLE="
        + ("true" if config.monitoring.hotlist_audience_editable else "false"),
        # ADR-140 Amendment 15: the private hosts and networks the operator admits the Studio's
        # connectors to (names and networks, never a secret).
        *(
            ["OSPREY_CONNECTOR_PRIVATE=" + ",".join(config.connectors.private_hosts)]
            if config.connectors.private_hosts
            else []
        ),
        # The connection secrets the operator declares, by name only (never a value): only the
        # Conduit is given them, and it reads no other.
        *(
            ["OSPREY_CONNECTOR_SECRETS=" + ",".join(config.connectors.secrets)]
            if config.connectors.secrets
            else []
        ),
        # ADR-143 decision 11 and Amendment 6: the scheme drawn items are graded in, by name, and a
        # scheme file's grades beside it (the Conduit never reads the file itself).
        *_grading_env(config),
        "",
        "# Ports published besides the front proxy's: the Conduit only when network.expose_conduit",
        "# asks, ArcadeDB on loopback only (ADR-114 Amendment 4 decision 3). Each is overridable.",
        *[
            f"{variable}={_published_port(config, service, default)}"
            for service, (variable, default) in PORT_OVERRIDES.items()
        ],
    ]
    if config.models.hosted_fallback is not None:
        lines.append(f"OSPREY_HOSTED_FALLBACK={config.models.hosted_fallback}")
    # ADR-135 (ADR-114 Amendment 6): the engines, each role's default, and what may be sent. No
    # key is here: only the gateway reads one, from the secrets apply writes.
    lines += model_engines_env(config)
    lines += reporting_env(config)
    lines += laurium_env(config)
    # §2.5: "It never sees a secret. Credentials are entered as references." Nothing above is a
    # value; every one of these is a name, a path or a choice already written in osprey.yaml.
    return _comment_block(_BANNER, "#") + "\n".join(lines) + "\n"


def _repository_and_tag(image: str) -> tuple[str, str]:
    """`ghcr.io/acme/api:abc` is (`ghcr.io/acme/api`, `abc`); `ollama/ollama@sha256:…`, pinned by
    digest alone, is (`ollama/ollama`, ``); a registry's port (`localhost:5000/…`) is not a tag.
    Splitting at the first colon wrote `ollama/ollama@sha256` as a repository (v0.4.4 and v0.4.5's
    locks), which `update --make-bundle` could not pull."""
    name = image.partition("@")[0]
    head, slash, last = name.rpartition("/")
    base, _, tag = last.partition(":")
    return f"{head}{slash}{base}", tag


def _render_versions_lock(
    images: Sequence[ServiceImage],
    resolver: DigestResolver,
    *,
    allow_unpinned: bool,
    resolved_source_label: str = "local-docker-daemon",
) -> str:
    entries = []
    unresolved = []
    sha = git_sha()
    for entry in images:
        # `source` is recorded per entry, not once per file, because the two can differ within one
        # render: a machine that has pulled some of these images and not others produces a lock
        # file that is partly a real pin and partly a gap, and a reader needs to know which line is
        # which. `local-docker-daemon` (the default, `harness.apply`'s own usage) means "this is
        # the digest this machine happened to have", a snapshot, not an authority —
        # `resolved_source_label` is how `tools.osprey_bundle.build_bundle` writes `"registry"`
        # here instead, matching what `harness.images.registry_digest_resolver` actually resolved
        # against, once the bundle's own Stage 2 §5b landed.
        source = resolved_source_label
        if entry.building:
            # `dockerfile` is resolved relative to `context`, which is the repository root, so it
            # stays a repo-root-relative path rather than becoming relative to the output dir too.
            # This render builds from this checkout and pushes nowhere, so there is no registry
            # digest to record. What identifies it is the commit it was built from. Recording
            # `local-build` plus that SHA is the honest answer; recording whatever digest the
            # local daemon happens to hold for a tag anyone can overwrite would look like a pin
            # and be worth nothing.
            entries.append(
                {
                    "service": entry.service,
                    "repository": _repository_and_tag(entry.image)[0],
                    "tag": _repository_and_tag(entry.image)[1],
                    "digest": "local-build",
                    "source": "local-build",
                    "built_from_git_sha": sha,
                    "build_context": entry.build_context,
                    "dockerfile": entry.dockerfile,
                }
            )
            continue
        # A reference pinned by digest (`ghcr.io/berriai/litellm@sha256:…`) already names the one
        # image it can ever be, so its digest is read from the reference and no registry is asked:
        # asking added only a way to fail. CI run 43413711132 (13 November 2026) refused to render
        # because ghcr.io did not answer in time for two such references.
        # `source: reference` says where the digest came from, as every other row's `source` does.
        _, at, pinned = entry.image.partition("@")
        if at and pinned.startswith("sha256:"):
            repository, tag = _repository_and_tag(entry.image)
            entries.append(
                {
                    "service": entry.service,
                    "repository": repository,
                    "tag": tag,
                    "digest": pinned,
                    "source": "reference",
                }
            )
            continue
        # Round 07: a pull-mode owned image is locked exactly like a third-party one — resolved
        # by digest, refused by name (below) if it cannot be. `owned` no longer exempts it; only
        # `building` does, above.
        digest = resolver(entry.image)
        if digest is None:
            unresolved.append(entry.image)
            digest = "unresolved"
            source = "unresolved"
        repository, tag = _repository_and_tag(entry.image)
        entries.append(
            {
                "service": entry.service,
                "repository": repository,
                "tag": tag,
                "digest": digest,
                "source": source,
            }
        )
    if unresolved and not allow_unpinned:
        raise UnpinnedImagesError(unresolved)
    body = yaml.safe_dump({"images": entries}, sort_keys=False, default_flow_style=False)
    return _comment_block(_BANNER, "#") + body


def _render_runbook(config: OspreyConfig, images: Sequence[ServiceImage]) -> str:
    """§2.1's own generated runbook: "written for *this* deployment with the real hostnames, ports
    and paths filled in."

    Distinct from `deploy/RUNBOOK.md`, which §6 requires to state the recovery time for each backup
    path and which Stage 2 §4 writes by hand — that one is a measurement, not a render.
    """
    rows = "\n".join(f"| `{i.service}` | `{i.image}` |" for i in images)
    # ADR-114 Amendment 38 decision 9: where `harness.backup` writes this deployment's sets, not
    # the setting verbatim (the schema's placeholder is no folder named off a server). Imported
    # here, as `harness.backup` imports this module.
    from harness.backup import FALLBACK_SPELLING, named_backups_folder

    named = named_backups_folder(config)
    sets = generated_folder(config)
    backups = (
        f"`{named.rstrip('/')}/{sets}/`"
        if named is not None
        else f"`{FALLBACK_SPELLING}/{sets}/` (`osprey.yaml` names no folder)"
    )
    hosts = (
        "\n".join(f"- `{h.name}` — `{h.address}`" for h in config.cluster.hosts)
        if config.cluster.hosts
        else "- Single host (this machine)."
    )
    return f"""{_comment_block(_BANNER, "<!--", "-->")}
# Runbook — `{config.profile.value}`

Generated for this deployment. Regenerate rather than edit.

## What runs

| Service | Image |
| --- | --- |
{rows}

Search backend: `{config.components.search.value}`{
        " — the reduced variant (spec/05_DEPLOYMENT.md §3): OpenSearch is dropped and full-text "
        "falls back to PostgreSQL. Search quality degrades and semantic search is unavailable."
        if config.components.search is SearchBackend.POSTGRES_FULLTEXT
        else "."
    }

## Hosts

{hosts}

## Paths

| What | Where |
| --- | --- |
| Data | `{config.components.storage.data}` |
| Staging | `{config.components.storage.staging}` |
| Backups | {backups} |
| Ingest (read-only into the Conduit) | `{config.components.storage.ingest}` |

## Addresses

Every app is reached by name through the front proxy (ADR-114 Amendment 4); nothing else is
published but what is listed here.

| Service | URL |
| --- | --- |
| Workspace | `{sites(config).glass}` |
| Identity provider | `{sites(config).identity}` |
{f"| Dashboards | `{sites(config).dashboards}` |" + chr(10) if config.reporting.superset else ""}{
        "| Conduit (network.expose_conduit) | `http://localhost:8000` |" + chr(10)
        if config.network.expose_conduit
        else ""
    }| Graph store (this machine only) | `http://127.0.0.1:2480` |
| Admin area | `{sites(config).glass}` — *Admin* on Start, for an administration right |

## Governance

| What | Value |
| --- | --- |
| Identity provider | `{config.governance.identity_provider}` |
| Handling scheme | `{config.governance.handling_scheme}` |
| Ontology | `{config.governance.ontology}` |
| Real-data exceptions list | `{config.governance.real_data_exceptions}` |

## Recovery

Recovery times per backup path are **not** here — `deploy/RUNBOOK.md` carries them
(spec/05_DEPLOYMENT.md §6), measured rather than generated.
"""


def _comment_block(text: str, opener: str, closer: str | None = None) -> str:
    if closer is not None:
        return f"{opener}\n{text}\n{closer}\n\n"
    return "".join(f"{opener} {line}\n" for line in text.splitlines()) + "\n"


@dataclass(frozen=True)
class RenderResult:
    """What a render produced, keyed by path relative to the output root, so `--check` and `--diff`
    can compare without writing anything."""

    profile: Profile
    artefacts: dict[str, str]


def render(
    config: OspreyConfig,
    *,
    resolver: DigestResolver | None = None,
    allow_unpinned: bool = False,
    resolved_source_label: str = "local-docker-daemon",
    build_context: str | None = None,
) -> RenderResult:
    """Produces all four of §2.1's artefacts in memory. Pure apart from the digest resolver, which
    is why byte-stability across runs is a property this can be tested for at all.

    `resolved_source_label` names, in `versions.lock`, *how* a resolved digest was obtained — it
    does not change what gets resolved, only how the lock file describes it. Left at its default
    for every caller except `tools.osprey_bundle.build_bundle`, which passes a resolver AND a
    label that actually agree with each other (`harness.images.registry_digest_resolver` /
    `"registry"`) rather than this function silently mislabelling a registry-resolved digest as a
    local-daemon one.
    """
    if resolver is None:
        resolver = (
            unresolved_digest_resolver if allow_unpinned else daemon_then_registry_digest_resolver
        )
    images = (
        service_images(config)
        if build_context is None
        else service_images(config, build_context=build_context)
    )
    if config.profile is Profile.CLOUD_PLATFORM:
        # ADR-148: the chart's values into a namespace on a shared platform, and its Terraform,
        # translated from the cluster's (`harness/cloud_platform/`).
        from harness.cloud_platform import render_cloud_platform

        return RenderResult(
            profile=config.profile,
            artefacts=render_cloud_platform(
                config,
                images,
                resolver=resolver,
                allow_unpinned=allow_unpinned,
                resolved_source_label=resolved_source_label,
            ),
        )
    if config.profile is Profile.CLUSTER:
        # 05 §3b: the chart's values, translated from the same services (`harness/cluster.py`).
        from harness.cluster import render_cluster

        return RenderResult(
            profile=config.profile,
            artefacts=render_cluster(
                config,
                images,
                resolver=resolver,
                allow_unpinned=allow_unpinned,
                resolved_source_label=resolved_source_label,
            ),
        )
    source_path = config.components.source_path
    # Round 07: only checked when a source tree is actually declared. The pull path (the
    # default) never looks at the local filesystem for a Dockerfile at all — the whole point,
    # since the harness image itself carries none.
    if source_path is not None:
        missing = [
            entry.service
            for entry in images
            if entry.owned and not (Path(source_path) / str(entry.dockerfile)).is_file()
        ]
        if missing:
            raise MissingDockerfileError(missing, source_path=source_path)
    return RenderResult(
        profile=config.profile,
        artefacts={
            "compose.yaml": _render_compose(config, images),
            "deployment.env": _render_env(config),
            "versions.lock": _render_versions_lock(
                images,
                resolver,
                allow_unpinned=allow_unpinned,
                resolved_source_label=resolved_source_label,
            ),
            "RUNBOOK.md": _render_runbook(config, images),
            "Caddyfile": _comment_block(_BANNER, "#") + render_caddyfile(config),
            "glass.json": render_glass_settings(config),
        },
    )


def load_config(path: Path) -> OspreyConfig:
    """`yaml.safe_load` + `model_validate`, the same shape `services/api/mapconfig_loader.py` and
    `services/ingest/recipe_loader.py` already use. An empty file is an empty config, not a crash:
    every section of `osprey.yaml` has a default. **A missing file is the same case, not a
    different one** — found 26 September 2026, Stage 2 §6 part C: this function's own docstring
    already claimed the empty-file case was handled, which read as covering "nothing configured
    yet" in general, but `path.read_text()` on a file that does not exist at all raised
    `FileNotFoundError` uncaught, all the way out of `python -m harness.render` and `python -m
    harness.apply` both — the exact CLI a fresh clone's own first run reaches for.
    `harness/webapp.py`'s own `_read_config` already drew this distinction correctly; this
    function had not."""
    if not path.exists():
        return OspreyConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = OspreyConfig.model_validate(raw)
    # ADR-143 Amendment 6: a scheme file named by `grading.scheme` is read beside this file.
    config.grading.read_file(path.parent)
    return config


def find_drift(result: RenderResult, out_dir: Path) -> list[str]:
    """Paths whose on-disk content differs from what a render produces, or that are missing
    entirely. Missing counts as drift: a deleted generated file is exactly as much a divergence
    between `osprey.yaml` and the deployment as an edited one."""
    drifted = []
    for name, content in sorted(result.artefacts.items()):
        target = out_dir / name
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            drifted.append(name)
    return drifted


def diff_for(result: RenderResult, out_dir: Path) -> dict[str, str]:
    """A unified diff per changed path — §2.4's change preview. Only changed paths appear, so an
    empty result means "nothing would change", which is the answer the preview exists to give."""
    diffs: dict[str, str] = {}
    for name, content in sorted(result.artefacts.items()):
        target = out_dir / name
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current == content:
            continue
        diffs[name] = "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            )
        )
    return diffs


#: The rendered file that holds, once `apply` has written them, the deployment's secrets.
SECRETS_FILE = "deployment.env"


def write_private(path: Path, text: str) -> None:
    """`text` into `path`, readable and writable by its owner alone (`600`), whether the file is new
    or was looser before (ADR-137 decision 2: `deployment.env` had been written `644`, readable by
    every account on the machine). The mode is set on the open file, before anything is written.

    Whole or not at all (CARRIES, 10 November 2026): written to a `600` file beside `path`, flushed
    to disk, given the old file's owner (so a run under sudo leaves it the operator's), and renamed
    over it; a failure part way leaves the old file as it was and nothing beside it. Only for a file
    a container reads when it is made (`deployment.env`, an `env_file`), never one it mounts: a
    rename gives the file a new inode. A symlink stays a link, its target replaced
    (`harness.atomic.replace_whole`, which every writer of `deployment.env` shares)."""
    from harness.atomic import replace_whole

    replace_whole(path, text.encode("utf-8"), mode=0o600)


#: What a rendered file that holds no secret is written as, and a folder of them, whatever the
#: installer's umask: readable by every account, because a container that does not run as the
#: installer reads it through a bind mount (Keycloak as uid 1000, the workspace and the Conduit
#: as 10001, ADR-148 decision 3). Found on the first server, 4 November 2026 (ADR-114 Amendment
#: 33): an install under `umask 077` wrote `realm.json` 600 and Keycloak could not import it.
SHARED_FILE_MODE = 0o644
SHARED_FOLDER_MODE = 0o755


def write_shared(path: Path, text: str) -> None:
    """`text` into `path`, readable by every account (`644`) whatever the umask, whether the file is
    new or was tighter before. Only for a file that holds no secret: `write_private` is the other
    half, for `deployment.env`."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, SHARED_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), SHARED_FILE_MODE)
        handle.write(text)


def make_shared_folder(path: Path, *, under: Path) -> None:
    """`path` and every folder between `under` and it made, each `755` whatever the umask, so a
    container mounting any of them can walk it. `under` itself keeps its own mode: a named
    deployment's folder is `700` (ADR-138), which a file's bind mount never walks."""
    path.mkdir(parents=True, exist_ok=True)
    for folder in (path, *path.parents):
        if folder == under or under not in folder.parents:
            break
        folder.chmod(SHARED_FOLDER_MODE)


#: What `write` wrote last into a deployment's folder, one path a line, so the next render removes
#: what it no longer makes (a standard shape's `terraform/opensearch.tf` after a poc render), and
#: never a file of anyone else's.
RENDERED_MANIFEST = ".rendered"


def _remove_what_is_no_longer_rendered(result: RenderResult, out_dir: Path) -> None:
    manifest = out_dir / RENDERED_MANIFEST
    if not manifest.is_file():
        return
    root = out_dir.resolve()
    for name in manifest.read_text(encoding="utf-8").splitlines():
        if not name or name in result.artefacts:
            continue
        stale = (out_dir / name).resolve()
        if root in stale.parents and stale.is_file():
            stale.unlink()
            # Its folder too, once nothing is left in it (never the deployment's own folder).
            folder = stale.parent
            while folder != root and folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent


def write(result: RenderResult, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    _remove_what_is_no_longer_rendered(result, out_dir)
    written = []
    for name, content in sorted(result.artefacts.items()):
        target = out_dir / name
        # An artefact in a folder of its own (the cloud-platform profile's `terraform/`): the
        # folder made, readable as the rest, before the file (a first render stopped without it).
        make_shared_folder(target.parent, under=out_dir)
        if name == SECRETS_FILE:
            write_private(target, content)
        else:
            write_shared(target, content)
        written.append(target)
    write_shared(
        out_dir / RENDERED_MANIFEST, "".join(f"{name}\n" for name in sorted(result.artefacts))
    )
    return written


def write_config_copy(config_path: Path, out_dir: Path) -> Path:
    """Copies the real `osprey.yaml` beside the rendered `compose.yaml` — not one of §2.1's four
    rendered artefacts (it is source, not derived), but what `_render_compose`'s own
    `./osprey.yaml:/app/osprey.yaml:ro` mount needs actually present at that relative path. Both
    CLI entry points (`harness.render`'s own `main`, `harness.apply`) call this once, right after
    `write`, so the two can never drift on whether it happens.

    **A missing `config_path` writes the schema defaults' own serialised form, not a crash** —
    found alongside `load_config`'s own identical gap: an operator (or the Preflight screen's own
    `Generate`) who has accepted every default and never explicitly saved anything yet has no
    `osprey.yaml` to copy, and that is a real, valid state (`load_config`'s own contract), not an
    error."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "osprey.yaml"
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
    else:
        content = yaml.safe_dump(
            OspreyConfig().model_dump(mode="json", exclude_none=True), sort_keys=False
        )
    # The Conduit mounts it, and it holds no secret (05_DEPLOYMENT.md §7: never in osprey.yaml).
    write_shared(target, content)
    # ADR-143 Amendment 6: a scheme file it names beside it goes with it, so the copy reads as the
    # original does (every later `load_config` of the copy, `harness.apply`'s among them).
    scheme = (yaml.safe_load(content) or {}).get("grading", {}) if content else {}
    named = scheme.get("scheme") if isinstance(scheme, dict) else None
    if (
        isinstance(named, str)
        and named.endswith((".yaml", ".yml"))
        and not Path(named).is_absolute()
    ):
        source = config_path.parent / named
        if source.is_file():
            kept = out_dir / named
            kept.parent.mkdir(parents=True, exist_ok=True)
            write_shared(kept, source.read_text(encoding="utf-8"))
    return target


def _display(path: Path) -> str:
    """Repository-relative when it can be, absolute otherwise. `--out-root` may point anywhere —
    a temporary directory in a test, a mounted `/workspace` in the harness container — and a
    crash while *printing* a successful render would be an absurd way to fail."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.render",
        description=(
            "Renders a deployment's own files from osprey.yaml (spec/05_DEPLOYMENT.md §2.1): "
            "the compose file, environment file, versions.lock and the per-deployment runbook."
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument(
        "--build",
        action="store_true",
        help=(
            "Build owned images from this checkout's own source rather than pulling them by "
            "digest — round 07's developer/CI path. Equivalent to declaring "
            "components.source_path in osprey.yaml, using this checkout's own root."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift against what is on disk and exit 1 if any; write nothing.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show what would change, per path, before writing; write nothing.",
    )
    parser.add_argument(
        "--allow-unpinned",
        action="store_true",
        help="Write versions.lock marking unresolvable digests 'unresolved', not failing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = load_config(args.config)
    if args.build:
        components = config.components.model_copy(update={"source_path": str(REPO_ROOT)})
        config = config.model_copy(update={"components": components})
    out_dir = args.out_root / generated_folder(config)
    resolver = None
    if config.profile is Profile.CLOUD_PLATFORM:
        # ADR-148 decision 8: theirs resolved even when unpinned (ours alone wait for the push),
        # and each one the previous plan copied pinned by the digest it copied.
        from harness.cloud_platform.carry import carried_resolver

        resolver = carried_resolver(out_dir / "images.yaml", daemon_then_registry_digest_resolver)
    result = render(config, resolver=resolver, allow_unpinned=args.allow_unpinned)

    if args.check:
        drifted = find_drift(result, out_dir)
        if drifted:
            print("render --check: drift against osprey.yaml in:")
            for name in drifted:
                print(f"  {_display(out_dir / name)}")
            print(f"\n{len(drifted)} path(s) differ. Regenerate rather than hand-edit.")
            return 1
        print(f"render --check: {len(result.artefacts)} artefact(s) match osprey.yaml, no drift.")
        return 0

    if args.diff:
        diffs = diff_for(result, out_dir)
        if not diffs:
            print("render --diff: nothing would change.")
            return 0
        for name, text in diffs.items():
            print(f"--- would change: {_display(out_dir / name)}")
            print(text, end="")
        print(f"\n{len(diffs)} path(s) would change.")
        return 0

    written = write(result, out_dir)
    write_config_copy(args.config, out_dir)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"render: {config.profile.value}, {len(written)} artefact(s), {stamp}")
    for path in written:
        print(f"  {_display(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
