"""The page service in a deployment: what the renderers add when `pages.enabled` is on (ADR-152
Amendment 3, items 1 to 4; decision 7's route table and `OSPREY_PAGES_TREE`; invariant I22).

The setting is one boolean in `osprey.yaml`, off by default, turned on for one deployment at a time
by the owner (`schemas.deployment.PagesConfig`). **Off means unchanged, byte for byte**: every
function here that adds something returns nothing while the setting is off, and the one that
refuses (`refuse_a_cutover_without_the_service`) refuses a configuration that would otherwise
render a deployment with neither front end. Nothing here is read from a profile, a brand or a
release: `enabled` is the only input to "on".

What "on" adds, in each of the four shapes (the compose file, the chart's values, the platform
Ingress):

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

The state of the GOV.UK tree is `scripts.tree_parity.govuk_tree_state()` (PL7a1): the one function,
asked when the render runs, never a second reading of it and never recorded.
"""

from __future__ import annotations

from schemas.deployment import OspreyConfig, Profile

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


#: Where the organisation's CA (`network.tls.ca`) is mounted into the service, read-only, and what
#: node's `NODE_EXTRA_CA_CERTS` names: the service's discovery, key set and token request go to the
#: identity name, whose certificate is the organisation's. Node keeps its own roots beside it.
CA_IN_SERVICE = "/etc/ssl/organisation-ca.pem"


class PageServiceNeedsHttps(ValueError):
    """The page service is on, and its sign-in has no address the service accepts: the identity
    address is neither https nor loopback (the owner's ruling of 23 November 2026)."""


class PageServiceNeedsTrust(ValueError):
    """The page service is on, and the identity name's certificate is one the service cannot verify:
    the front proxy signs that name itself, with its own internal authority, which node does not
    trust (round 5 of PL7a2b: the service's certificate check is not weakened or switched off)."""


class PageServiceNotEnabled(ValueError):
    """A GOV.UK deployment whose tree is complete would lose its workspace with nothing to take its
    place (ADR-152 Amendment 3 item 4)."""


#: The words of the refusal, as the amendment gives them.
REFUSAL = (
    "the GOV.UK tree is complete, so the workspace would be removed, and the page service is not "
    "enabled for this deployment"
)


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


def refuse_a_cutover_without_the_service(config: OspreyConfig) -> None:
    """Amendment 3 item 4: a GOV.UK deployment whose tree is complete and whose setting is off is
    refused in words, rather than rendering a deployment with neither front end."""
    if not enabled(config) and govuk_tree_is_complete(config):
        raise PageServiceNotEnabled(REFUSAL)


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


#: The words of the second refusal, with the identity address in them.
NEEDS_HTTPS = (
    "pages.enabled is on, but the identity address {identity} is neither https nor a loopback "
    "address, and the page service does not sign people in over plain HTTP: serve the identity "
    "address over HTTPS with a certificate the page service trusts, or leave pages.enabled off"
)

#: The words of the third refusal, with the identity address in them.
NEEDS_TRUST = (
    "pages.enabled is on, but the identity address {identity} is served with a certificate from "
    "the front proxy's own internal authority, which the page service does not trust, so people "
    "could not sign in: give the deployment an address with a certificate the page service trusts "
    "(a public name, or network.tls on a Small), or leave pages.enabled off"
)

#: The names Caddy signs itself, with its own internal authority, rather than ask a public one
#: (certmagic's `SubjectIsInternal`, with an IP address, which no public authority signs for).
_INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")


def service_accepts_issuer(issuer: str) -> bool:
    """`apps/pages/server/config.ts`'s `oidcSettings` refuses an issuer that is not `https`, bar an
    `http` one whose host is exactly loopback (`localhost`, `[::1]`, `127.x.x.x`). That check is not
    weakened: the render holds itself to it, here, and refuses where it cannot meet it."""
    import re
    from urllib.parse import urlsplit

    url = urlsplit(issuer)
    host = url.hostname or ""
    loopback = host in ("localhost", "::1") or re.fullmatch(r"127(\.\d{1,3}){3}", host)
    return url.scheme == "https" or (url.scheme == "http" and bool(loopback))


def refuse_sign_in_without_https(config: OspreyConfig) -> None:
    """The page service is given its sign-in (all three variables) or it is not turned on: a
    deployment whose identity address is neither https nor loopback (local-lite on plain HTTP: a
    `.localhost` name is not loopback by the service's own rule) has no address to give it, and is
    refused in plain words rather than rendered with a service whose sign-in cannot work."""
    from harness.site import REALM, sites

    names = sites(config)
    if not service_accepts_issuer(f"{names.identity}/realms/{REALM}"):
        raise PageServiceNeedsHttps(NEEDS_HTTPS.format(identity=names.identity))


def caddy_signs_itself(host: str) -> bool:
    """Whether Caddy gives `host` a certificate from its own internal authority: `localhost`, a name
    under `.localhost`, `.local`, `.internal` or `.home.arpa`, or an IP address (the names no public
    authority signs for). Node does not trust that authority."""
    import ipaddress

    name = host.rstrip(".").lower()
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return name == "localhost" or name.endswith(_INTERNAL_SUFFIXES)
    return True


def refuse_sign_in_without_trust(config: OspreyConfig) -> None:
    """The page service is given a sign-in whose certificate it can verify, or it is not turned on.
    An https identity address the proxy signs itself (local-lite's `.localhost` name: Lite has no
    `network.tls`) is served with an authority node does not trust, so discovery would fail at
    sign-in; no trust path is given (it would take the authority's root out of the proxy's data
    volume, which holds its private key) and the service's check is not touched: the render refuses.
    The organisation's own certificate (`network.tls`, its CA mounted where it is given) and a
    public name are trusted. Plain HTTP is `refuse_sign_in_without_https`'s."""
    from harness.site import sites

    names = sites(config)
    if names.scheme == "https" and config.network.tls is None and caddy_signs_itself(names.host):
        raise PageServiceNeedsTrust(NEEDS_TRUST.format(identity=names.identity))


def identity_listener_port(config: OspreyConfig) -> int | None:
    """The port the front proxy must also listen on, inside its container, for the identity name,
    so the page service reaches its issuer through the alias (round 5 of PL7a2b).

    The issuer is the public identity name with the origin's port (Keycloak reports its issuer as
    the public address whichever door a request came through, and the service checks the discovery
    document against the address it asked, so an issuer carrying the proxy's in-container port would
    be refused). The proxy's own in-container HTTPS port is 8443 with the organisation's certificate
    and 443 otherwise, and the host's published port maps to it: the alias does not. So where the
    origin's port is not the proxy's own, the identity site is given an address at the origin's
    port too. Nothing is published, no network is added. None where no listener is needed, where
    the page service is off, or where the origin is plain HTTP (refused above)."""
    from harness.site import PROXY_HTTPS_PORT, sites

    names = sites(config)
    if not enabled(config) or names.scheme != "https":
        return None
    own = PROXY_HTTPS_PORT if config.network.tls is not None else 443
    return None if names.port == own else names.port


def identity_alias(config: OspreyConfig) -> str:
    """The identity name (`id.<host>`) the proxy answers to on the internal network `osprey`, so the
    page service reaches its issuer there with no route out (the owner's ruling of 23 November 2026:
    ADR-114 Amendment 7, `egress_needs` not widened for the service)."""
    from harness.site import sites

    return f"id.{sites(config).host}"


def service_environment(config: OspreyConfig, *, with_sign_in: bool) -> dict[str, str]:
    """The page service's own variables, as the compose file and a chart's workload carry them.

    The two secrets are **references** to the env file's names (`${NAME:?…}`), never values: the
    file is `deployment.env`, mode 600, and the cluster's Secret, where each is minted once. No
    other secret reaches the service. `with_sign_in` is whether the deployment runs the identity
    provider the service signs in against: where it does, the service is given **all three** sign-in
    variables or the render refuses (`refuse_sign_in_without_https`), never fewer. The cloud
    platform's people sign in with the organisation's own (PL9b), so its service holds no client of
    ours and answers sign-in as it did before it was built."""
    from harness.realm import PAGES_CLIENT_ID, PAGES_CLIENT_SECRET_KEY, PAGES_SESSION_SECRET_KEY
    from harness.site import REALM, sites

    names = sites(config)
    refer = "${%s:?set in the deployment env file}"
    environment = {
        "OSPREY_PAGES_TREE": tree(config),
        "OSPREY_PAGES_PORT": str(PAGES_PORT),
        "OSPREY_PAGES_PUBLIC_ORIGIN": names.glass,
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
        refuse_sign_in_without_https(config)
        refuse_sign_in_without_trust(config)
        environment["OSPREY_PAGES_OIDC_ISSUER"] = f"{names.identity}/realms/{REALM}"
        environment["OSPREY_PAGES_CLIENT_ID"] = PAGES_CLIENT_ID
        environment["OSPREY_PAGES_CLIENT_SECRET"] = refer % PAGES_CLIENT_SECRET_KEY
        tls = config.network.tls
        if config.profile is Profile.SMALL and tls is not None and tls.ca:
            environment["NODE_EXTRA_CA_CERTS"] = CA_IN_SERVICE
    return environment
