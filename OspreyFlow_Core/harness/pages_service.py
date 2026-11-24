"""The page service in a deployment: what the renderers add when `pages.enabled` is on (ADR-152
Amendment 3, items 1 to 4; decision 7's route table and `OSPREY_PAGES_TREE`; invariant I22).

The setting is one boolean in `osprey.yaml`, off by default, turned on for one deployment at a time
by the owner (`schemas.deployment.PagesConfig`). **Off means unchanged, byte for byte**: every
function here that adds something returns nothing while the setting is off. Nothing here is read
from a profile, a brand or a release: `enabled` is the only input to "on".

What "on" adds, in the shapes that can run it (local-lite is refused over plain HTTP or an
untrusted certificate, and the cloud-platform shape has no sign-in for it yet, both by
`harness.page_addresses`; so, in effect, small and cluster: the compose file, the chart's values):

* the `pages` service (`harness.render.compose_services`; the chart's workloads and the lock are
  translated from it): its image is the owned `pages` image, its two secrets by reference to the
  names `apply` has minted since PL9a and the cluster's install mints (`harness.realm`), never a
  value, and **only those two**: the service reads no `env_file` (it has no use for the stores'
  passwords);
* the route table for the deployment's brand (`route_paths`): the Studio's paths on the default
  theme, `pages`' own paths on both, and every path once the GOV.UK tree is complete (I22), when
  there is no workspace service and no route to one;
* `OSPREY_PAGES_TREE`, from `appearance.brand` (`default` or `govuk`), and the rest of the
  service's variables (`service_environment`).

**Its addresses are not worked out here.** The origin, the issuer, the sign-in variables, the
trust file, the identity alias and the identity listener's port are
`harness.page_addresses.derive`'s, the only place that computes them (the owner's ruling of
24 November 2026, slice PL7f); `service_environment` copies what it returns, and the refusals that
used to live here (plain HTTP, the own certificate's trust, the cloud-platform shape, a default
port, a port the proxy already uses, the cutover without the setting) moved there with their words.

The state of the GOV.UK tree is `scripts.tree_parity.govuk_tree_state()` (PL7a1): the one function,
asked when the render runs, never a second reading of it and never recorded.
"""

from __future__ import annotations

from schemas.deployment import OspreyConfig

#: The compose service's name, the chart's workload's, and the front proxy's upstream host.
SERVICE = "pages"
#: Where the service listens (`apps/pages/server/config.ts`'s own default `OSPREY_PAGES_PORT`).
PAGES_PORT = 8090
UPSTREAM = f"{SERVICE}:{PAGES_PORT}"
#: The image's Dockerfile, relative to the checkout (`apps/pages/Dockerfile`).
DOCKERFILE = "apps/pages/Dockerfile"
#: What the workspace listens on, which decision 7's table sends every other path to.
WORKSPACE_UPSTREAM = "workspace:8080"

#: The paths decision 7 sends to `pages` whichever the theme: the service's own (`/session/…`
#: sign-in and its callback, `/assets/pages/…` its assets). Each also matches its own folder
#: (`/session`), as the front proxy's `path` matcher does not match a bare folder for `/session/*`.
OWN_PATHS = ("/session", "/assets/pages")
#: The Studio's paths, on the default theme (decision 7: "on the default theme, the Studio's paths
#: (`/studio/…`)"). On the GOV.UK theme a function's path goes to `pages` once its tree has it.
STUDIO_PATHS = ("/studio",)


def enabled(config: OspreyConfig) -> bool:
    """Whether this deployment runs the page service: `pages.enabled`, and nothing else."""
    return config.pages.enabled


def tree(config: OspreyConfig) -> str:
    """`OSPREY_PAGES_TREE`: the tree the service loads, from the deployment's brand (decision 7)."""
    return "govuk" if config.appearance.brand == "govuk" else "default"


def govuk_tree_is_complete(config: OspreyConfig) -> bool:
    """A GOV.UK deployment whose derived tree state is complete (invariant I22). The state is
    `scripts.tree_parity.govuk_tree_state()` (read when this is called, so a test can point it at
    a fixture tree by the three files it reads); the default brand has no GOV.UK tree to complete,
    and is not asked."""
    if config.appearance.brand != "govuk":
        return False
    from scripts import tree_parity

    return tree_parity.govuk_tree_state() == tree_parity.COMPLETE


def workspace_removed(config: OspreyConfig) -> bool:
    """I22: with the setting on and the GOV.UK tree complete, no workspace service and no route
    to one. (With it off, the complete tree is refused before this is asked.)"""
    return enabled(config) and govuk_tree_is_complete(config)


def route_paths(config: OspreyConfig) -> list[str]:
    """The paths the front door sends to `pages` while the workspace still serves the rest: the
    service's own, the Studio's on the default theme, and on the GOV.UK theme each function's path
    once its tree has it (decision 7: `apps/pages/tree-govuk/routes.yaml` is that tree's list,
    read through `scripts.tree_parity.govuk_tree_routes`; none is rendered until the first function
    has its page). Empty while the setting is off."""
    if not enabled(config):
        return []
    paths = list(OWN_PATHS)
    if config.appearance.brand != "govuk":
        return [*STUDIO_PATHS, *paths]
    from scripts import tree_parity

    for route in tree_parity.govuk_tree_routes():
        path = route.rstrip("/") or "/"
        if path not in paths:
            paths.append(path)
    return paths


def caddy_matcher(paths: list[str]) -> str:
    """The front proxy's named `path` matcher for `paths`: each path and everything under it (the
    root, `/`, being every path, is `/*`: a `//*` would match nothing)."""
    return "@pages path " + " ".join(
        "/ /*" if path == "/" else f"{path} {path}/*" for path in paths
    )


def service_environment(config: OspreyConfig, *, with_sign_in: bool) -> dict[str, str]:
    """The page service's own variables, as the compose file and a chart's workload carry them.

    The two secrets are **references** to the env file's names (`${NAME:?…}`), never values: the
    file is `deployment.env`, mode 600, and the cluster's Secret, where each is minted once. No
    other secret reaches the service. The addresses are `harness.page_addresses.derive`'s, copied:
    `with_sign_in` is whether the deployment runs the identity provider the service signs in
    against, where it does the service is given **all three** sign-in variables (and the trust file,
    where it needs one) or `derive` refuses, never fewer. The cloud platform runs no identity
    provider of ours and is refused with the setting on."""
    from harness import page_addresses
    from harness.realm import PAGES_SESSION_SECRET_KEY

    derived = page_addresses.require(config, with_sign_in=with_sign_in)
    assert derived is not None, "the page service's environment is asked for with the setting off"
    refer = "${%s:?set in the deployment env file}"
    environment = {
        "OSPREY_PAGES_TREE": tree(config),
        "OSPREY_PAGES_PORT": str(PAGES_PORT),
        page_addresses.ORIGIN_VARIABLE: derived.public_origin,
        "OSPREY_PAGES_CONDUIT_URL": "http://api:8000",
        "OSPREY_PAGES_SESSION_SECRET": refer % PAGES_SESSION_SECRET_KEY,
        # The service's own database number and key prefix are its own defaults (decision 4); the
        # Valkey it reads is the Conduit's, by the same names (`VALKEY_*`).
        "VALKEY_HOST": "${VALKEY_HOST:?set in the deployment env file}",
        "VALKEY_PORT": "${VALKEY_PORT:-6379}",
        "VALKEY_TLS": "${VALKEY_TLS:-false}",
        "VALKEY_PASSWORD": "${VALKEY_PASSWORD:-}",
    }
    if with_sign_in:
        environment.update(derived.sign_in())
        if derived.trust:
            environment[page_addresses.TRUST_VARIABLE] = derived.trust
    return environment
