"""The page service's addresses, derived in one place (ADR-152 Amendment 3, decisions 4 and 7; build
id PL7, slice PL7f; the owner's rulings of 23 and 24 November 2026).

With `pages.enabled` on, the page service is given an issuer, a public origin, a sign-in client and,
where it needs one, a trust file; the front proxy answers to the identity name inside the network
and listens for it on one more port. Each was once worked out where it was used, and each round of
the first build found a new place where two of them disagreed. **`derive` is the only place that
computes any of them.** It returns the issuer, the public origin (its default port removed), the
identity alias, the identity listener's port, the trust variable and the three sign-in variables, as
a `PageAddresses`, or a `Refusal` in plain words that names `pages.enabled` and the cause, or `None`
where the setting is off and there is nothing to derive or refuse.

The page-service render module (`harness.pages_service`), the front proxy's module
(`harness.site`: the Caddyfile and the ports it publishes), the compose renderer
(`harness.render`) and the cloud-platform renderer read what it returns and compute none of it.
Nothing in the Caddyfile, the compose file or the chart names a port, a host or an alias that
`derive` did not return. The page service's own start-up checks (`apps/pages/server/config.ts`)
are not weakened: every value returned here passes them
(`apps/pages/test/server/pageAddresses.test.ts` calls them on every row of the table of cases) and
every Caddyfile that follows loads in the proxy image's own Caddy
(`tests/harness/test_page_addresses_caddy.py`).

**The order of the refusals** (the first that applies is the answer): the shape (the cloud platform
has no page-service sign-in yet), the form of `network.public_origin` (more than an origin, an IP
address or a bracketed host, a name the service cannot make an identity name from), plain HTTP, a
port the front proxy already uses, the proxy's own authority, the organisation's own certificate
with no `ca`. Each check is a function of its own that returns a `Refusal` or `None`, so a test can
take one out and show what stands behind it (rule 15).

**The table of cases** is `tests/fixtures/page_addresses_cases.json`, read by the Python tests, the
node test and the real-Caddy test.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from schemas.deployment import OspreyConfig, Profile

if TYPE_CHECKING:
    from harness.site import ProxyPort, Sites

#: Where the organisation's CA (`network.tls.ca`) is mounted into the service, read-only, and what
#: node's `NODE_EXTRA_CA_CERTS` names: the service's discovery, key set and token request go to the
#: identity name, whose certificate is the organisation's. Node keeps its own roots beside it.
CA_IN_SERVICE = "/etc/ssl/organisation-ca.pem"

#: The three variables that sign people in, and the one that carries the trust file, by name.
ISSUER_VARIABLE = "OSPREY_PAGES_OIDC_ISSUER"
CLIENT_ID_VARIABLE = "OSPREY_PAGES_CLIENT_ID"
CLIENT_SECRET_VARIABLE = "OSPREY_PAGES_CLIENT_SECRET"
ORIGIN_VARIABLE = "OSPREY_PAGES_PUBLIC_ORIGIN"
TRUST_VARIABLE = "NODE_EXTRA_CA_CERTS"


# ---- what a refusal is --------------------------------------------------------------------------


class PageServiceNeedsHttps(ValueError):
    """The page service is on, and its sign-in has no address the service accepts: the identity
    address is neither https nor loopback (the owner's ruling of 23 November 2026)."""


class PageServiceNeedsTrust(ValueError):
    """The page service is on, and the identity name's certificate is one the service cannot verify:
    the front proxy signs that name itself, with its own internal authority, which node does not
    trust (round 5 of PL7a2b: the service's certificate check is not weakened or switched off)."""


class PageServiceNeedsCa(ValueError):
    """The page service is on, and the identity name is served with the organisation's own
    certificate (`network.tls`) that names no CA: the certificate may come from a private root,
    which node trusts only where `NODE_EXTRA_CA_CERTS` names it, and the render cannot tell by the
    name (rounds 7 and 8 of PL7a2b)."""


class PageServiceNeedsAnOrigin(ValueError):
    """The page service is on, and `network.public_origin` is written in a form the service refuses
    to start on, or cannot make its identity address from (a path, a query, a user name, an IP
    address or a bracketed host, a name that is not plain ASCII DNS)."""


class PageServiceNeedsAnotherPort(ValueError):
    """The page service is on, and the origin's port is one the front proxy already uses (the owner,
    24 November 2026: any port it publishes but its own HTTPS port, and its plain-HTTP ports in
    every shape), which Caddy refuses to load or Docker refuses to publish twice (round 9 of
    PL7a2b)."""


class PageServiceNotOnThisShape(ValueError):
    """The page service is on for the cloud-platform shape, which has no sign-in for it yet (the
    owner's ruling of 23 November 2026, PL7a2b case C: ADR-148 Amendment 23 item 1 needs the chart's
    egress to the identity provider and the page service's own Entra registration, a part of its
    own, PL7e)."""


class PageServiceNotEnabled(ValueError):
    """A GOV.UK deployment whose tree is complete would lose its workspace with nothing to take its
    place (ADR-152 Amendment 3 item 4)."""


#: A refusal's key (as the table of cases names it) and the error it is raised as.
ERRORS: dict[str, type[ValueError]] = {
    "needs_https": PageServiceNeedsHttps,
    "needs_trust": PageServiceNeedsTrust,
    "needs_ca": PageServiceNeedsCa,
    "needs_origin": PageServiceNeedsAnOrigin,
    "port_taken": PageServiceNeedsAnotherPort,
    "cloud_platform": PageServiceNotOnThisShape,
    "cutover": PageServiceNotEnabled,
}


@dataclass(frozen=True)
class Refusal:
    """What `derive` returns where the page service cannot be given an address that works: the key
    that says which rule, and the words, in plain English, that name `pages.enabled` (the cutover's
    are the amendment's own) and the cause."""

    key: str
    words: str

    def error(self) -> ValueError:
        return ERRORS[self.key](self.words)


@dataclass(frozen=True)
class PageAddresses:
    """Every address the page service and the front proxy are given for it, and no other source."""

    #: `OSPREY_PAGES_PUBLIC_ORIGIN`: scheme, host and port, lower case, the default port left off.
    public_origin: str
    #: The identity address, `<scheme>://id.<host>[:port]`.
    identity: str
    #: `OSPREY_PAGES_OIDC_ISSUER`: the identity address and the realm.
    issuer: str
    #: The name the proxy answers to on the internal network `osprey`: `id.<host>`.
    identity_alias: str
    #: The port the service reaches the identity name on (the origin's port).
    identity_port: int
    #: The port the proxy must also listen on, inside its container, for the identity name; None
    #: where the origin's port is the one it listens on already, and for a shape with no alias.
    extra_listener: int | None
    #: The port the proxy itself listens on for HTTPS inside its container (443; 8443 beside the
    #: organisation's certificate); None where the shape has no proxy of this kind.
    proxy_https_port: int | None
    #: `NODE_EXTRA_CA_CERTS`'s value: where the organisation's CA is mounted in the service.
    trust: str | None

    def sign_in(self) -> dict[str, str]:
        """The three sign-in variables: the issuer, the client and a reference to its secret (the
        env file's name, never a value)."""
        from harness.realm import PAGES_CLIENT_ID, PAGES_CLIENT_SECRET_KEY

        secret = f"${{{PAGES_CLIENT_SECRET_KEY}:?set in the deployment env file}}"
        return {
            ISSUER_VARIABLE: self.issuer,
            CLIENT_ID_VARIABLE: PAGES_CLIENT_ID,
            CLIENT_SECRET_VARIABLE: secret,
        }

    def environment(self) -> dict[str, str]:
        """The variables this object gives the service, in the order the service lists them."""
        return {
            ORIGIN_VARIABLE: self.public_origin,
            **self.sign_in(),
            **({TRUST_VARIABLE: self.trust} if self.trust else {}),
        }


# ---- the words ----------------------------------------------------------------------------------

#: The words of the cutover refusal, as the amendment gives them.
CUTOVER = (
    "the GOV.UK tree is complete, so the workspace would be removed, and the page service is not "
    "enabled for this deployment"
)

NEEDS_SIGN_IN_ON_CLOUD_PLATFORM = (
    "pages.enabled is on, but the page service cannot run on the cloud-platform shape yet: people "
    "would have no way to sign in to it there (the chart gives it no egress to the identity "
    "provider, and it has no registration with the organisation's Entra ID: ADR-148 Amendment 23). "
    "Leave pages.enabled off for this deployment until the page service is offered on the "
    "cloud-platform shape"
)

NEEDS_HTTPS = (
    "pages.enabled is on, but the identity address {identity} is neither https nor a loopback "
    "address, and the page service does not sign people in over plain HTTP: serve the identity "
    "address over HTTPS with a certificate the page service trusts, or leave pages.enabled off"
)

NEEDS_TRUST = (
    "pages.enabled is on, but the identity address {identity} is served with a certificate from "
    "the front proxy's own internal authority, which the page service does not trust, so people "
    "could not sign in: give the deployment an address with a certificate the page service trusts "
    "(a public name, or network.tls on a Small), or leave pages.enabled off"
)

NEEDS_CA = (
    "pages.enabled is on, but the identity address {identity} is served with the deployment's own "
    "certificate (network.tls), which names no CA, so the page service cannot tell which root to "
    "trust for it and people could not sign in: give network.tls a ca (the root certificate that "
    "signed it; a public authority's root will do), or leave pages.enabled off"
)

NEEDS_ORIGIN = (
    "pages.enabled is on, but network.public_origin {problem}, and the page service refuses to "
    "start on an address written that way, so people could not sign in: {fix}, or leave "
    "pages.enabled off"
)

#: A port the proxy serves as plain HTTP inside its container in this shape: the words of round 9.
NEEDS_ANOTHER_PORT = (
    "pages.enabled is on, but network.public_origin gives the identity address {identity} the port "
    ":{port}, which the front proxy already serves as plain HTTP inside its container ({use}), and "
    "one port cannot serve both plain HTTP and HTTPS, so the front proxy would not start: give "
    "network.public_origin a different port, or leave pages.enabled off"
)

#: Any other port the proxy uses: published for a door or a redirect, or its plain-HTTP port in
#: another shape (the owner, 24 November 2026).
NEEDS_ANOTHER_PORT_ELSEWHERE = (
    "pages.enabled is on, but network.public_origin gives the identity address {identity} the port "
    ":{port}, which the front proxy uses ({use}), and an HTTPS address cannot share a port with "
    "plain HTTP or with a port the proxy publishes, so the front proxy would not start or could "
    "not be reached: give network.public_origin a different port, or leave pages.enabled off"
)

#: What is wrong with the origin and what to write, for the two forms the owner named.
MORE_THAN_AN_ORIGIN = (
    "carries a path, a query, a fragment or a user name",
    "write the origin alone (scheme, host and port, for example https://osprey.example.org)",
)
AN_IP_ADDRESS = (
    "is an IP address or a bracketed host, and the identity address (id.<host>) needs a name a "
    "certificate can carry",
    "give the deployment a DNS name written in lower case ASCII (for example "
    "https://osprey.example.org), not an IP address",
)

_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
_DNS_NAME = re.compile(rf"{_LABEL}(?:\.{_LABEL})*", re.ASCII)
#: A last label the service's URL parser reads as a number (decimal, or `0x` and hex digits), which
#: makes the whole host an IPv4 address to it, whatever the labels before: `id.<host>` is then no
#: name.
_NUMBER_LAST = re.compile(r"[0-9]+|0[xX][0-9a-fA-F]*")
#: The names Caddy signs itself, with its own internal authority, rather than ask a public one
#: (certmagic's `SubjectIsInternal`, with an IP address, which no public authority signs for).
_INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")


# ---- what each check says ---------------------------------------------------------------------


def _sites(config: OspreyConfig) -> Sites:
    from harness.site import sites

    return sites(config)


def _on_cloud_platform(config: OspreyConfig) -> Refusal | None:
    """The page service is not rendered for the cloud-platform shape (development or the proof of
    concept) with the setting on: it would hold none of its three sign-in variables, and the chart
    has no egress to the identity provider for it. No sign-in is built here, no egress is added and
    the chart's policy is untouched; the part that gives the page service its Entra sign-in (PL7e)
    lifts this."""
    if config.profile is Profile.CLOUD_PLATFORM:
        return Refusal("cloud_platform", NEEDS_SIGN_IN_ON_CLOUD_PLATFORM)
    return None


def _origin_problem(config: OspreyConfig) -> Refusal | None:
    """What is wrong with `network.public_origin` for the page service, or None where the values
    made from it are ones the service starts with.

    `config.ts` (`publicOrigin`, `oidcSettings`) accepts a value only where it is exactly what its
    URL parser makes of it, and the identity name is `id.` in front of the host. So the origin is
    refused where it carries more than scheme, host and port (a path, a query, a fragment, a user
    name), where the host is an IP address in any form or bracketed (an identity name needs a name a
    certificate can carry: the owner, 24 November 2026), or where it is not a plain ASCII DNS name,
    lower case, letters, digits and hyphens between dots (no non-ASCII, percent-encoded or
    punycode name, no trailing dot, no last label the parser reads as a number). The scheme's
    default port is not refused: it is left off (`derive`). This is stricter than the service in
    a few forms (a punycode name, a trailing dot, an underscore): a host nobody could be sure of is
    refused, in words."""
    names = _sites(config)
    raw = config.network.public_origin
    parsed = urlsplit(raw.rstrip("/"))
    if parsed.path or parsed.query or parsed.fragment or "?" in raw or "#" in raw or (
        parsed.username is not None or parsed.password is not None
    ):  # fmt: skip
        problem, fix = MORE_THAN_AN_ORIGIN
        return Refusal("needs_origin", NEEDS_ORIGIN.format(problem=problem, fix=fix))
    host = names.host
    if "[" in parsed.netloc or _is_ip_address(host):
        problem, fix = AN_IP_ADDRESS
        return Refusal("needs_origin", NEEDS_ORIGIN.format(problem=problem, fix=fix))
    reason = None
    if not _DNS_NAME.fullmatch(host):
        reason = "is not a plain ASCII DNS name (letters, digits and hyphens between dots)"
    elif _NUMBER_LAST.fullmatch(host.rsplit(".", 1)[-1]):
        reason = "ends in a number, which makes it an IP address to the page service"
    elif any(label.startswith("xn--") for label in host.split(".")):
        reason = "is a punycode name"
    if reason is not None:
        return Refusal(
            "needs_origin",
            NEEDS_ORIGIN.format(
                problem=f"names the host {host!r}, which {reason}",
                fix="give the deployment a DNS name written in lower case ASCII "
                "(for example https://osprey.example.org), not an IP address",
            ),
        )
    return None


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _service_accepts_issuer(issuer: str) -> bool:
    """`apps/pages/server/config.ts`'s `oidcSettings` refuses an issuer that is not `https`, bar an
    `http` one whose host is exactly loopback (`localhost`, `[::1]`, `127.x.x.x`). That check is not
    weakened: the render holds itself to it, here, and refuses where it cannot meet it."""
    url = urlsplit(issuer)
    host = url.hostname or ""
    loopback = host in ("localhost", "::1") or re.fullmatch(r"127(\.\d{1,3}){3}", host)
    return url.scheme == "https" or (url.scheme == "http" and bool(loopback))


def _needs_https(config: OspreyConfig) -> Refusal | None:
    """The page service is given its sign-in (all three variables) or it is not turned on: a
    deployment whose identity address is neither https nor loopback (local-lite on plain HTTP: a
    `.localhost` name is not loopback by the service's own rule) has no address to give it."""
    from harness.site import REALM

    names = _sites(config)
    if not _service_accepts_issuer(f"{names.identity}/realms/{REALM}"):
        return Refusal("needs_https", NEEDS_HTTPS.format(identity=_identity(names)))
    return None


def _taken_ports(config: OspreyConfig) -> dict[int, tuple[ProxyPort | None, str]]:
    """Every number the front proxy uses, other than its own HTTPS port, by the entry that uses it:
    the list `harness.site.proxy_ports` publishes (so a port added there is covered at once), and
    the ports the proxy serves plain HTTP on in some shape or other, in every shape."""
    from harness.site import PLAIN_HTTP_PORTS, proxy_ports

    taken: dict[int, tuple[ProxyPort | None, str]] = {}
    for entry in proxy_ports(config):
        if entry.origin:
            continue
        for number in (entry.container, entry.host):
            if number is not None:
                taken.setdefault(number, (entry, entry.use))
    for number, use in PLAIN_HTTP_PORTS.items():
        taken.setdefault(number, (None, use))
    return taken


def _port_taken(config: OspreyConfig) -> Refusal | None:
    """The identity listener, and the origin, are not put on a port the proxy already uses: Caddy
    refuses a Caddyfile with an HTTP site and an HTTPS site on one listener, and Docker refuses a
    host port published twice, so the front proxy, the deployment's only door, would not start
    (round 9 of PL7a2b). The ports are every one `harness.site.proxy_ports` lists but the proxy's
    own HTTPS port (where the origin's port is that one, no listener is added); the plain-HTTP
    ports, 80 and 8080, count in every shape: an HTTPS origin on a plain-HTTP port is refused
    whichever certificate it has (the owner, 24 November 2026). A shape with no proxy of this kind
    (a cluster's, with no alias and no doors) has none to clash with."""
    if config.profile not in (Profile.LOCAL_LITE, Profile.SMALL):
        return None
    names = _sites(config)
    if names.scheme != "https":
        return None
    found = _taken_ports(config).get(names.port)
    if found is None:
        return None
    entry, use = found
    template = (
        NEEDS_ANOTHER_PORT
        if entry is not None and entry.plain_http and entry.container == names.port
        else NEEDS_ANOTHER_PORT_ELSEWHERE
    )
    return Refusal(
        "port_taken", template.format(identity=_identity(names), port=names.port, use=use)
    )


def _caddy_signs_itself(host: str) -> bool:
    """Whether Caddy gives `host` a certificate from its own internal authority: `localhost`, a name
    under `.localhost`, `.local`, `.internal` or `.home.arpa`, or an IP address (the names no public
    authority signs for). Node does not trust that authority."""
    name = host.rstrip(".").lower()
    if _is_ip_address(name):
        return True
    return name == "localhost" or name.endswith(_INTERNAL_SUFFIXES)


def _needs_trust(config: OspreyConfig) -> Refusal | None:
    """An https identity address the proxy signs itself (local-lite's `.localhost` name: Lite has no
    `network.tls`) is served with an authority node does not trust, so discovery would fail at
    sign-in; no trust path is given (it would take the authority's root out of the proxy's data
    volume, which holds its private key) and the service's check is not touched."""
    names = _sites(config)
    if names.scheme == "https" and config.network.tls is None and _caddy_signs_itself(names.host):
        return Refusal("needs_trust", NEEDS_TRUST.format(identity=_identity(names)))
    return None


def _needs_ca(config: OspreyConfig) -> Refusal | None:
    """The organisation's own certificate (`network.tls`) with no `ca` is refused, on any name. It
    may come from a private root, which node trusts only where `NODE_EXTRA_CA_CERTS` names it; the
    render cannot tell a private root from a public one by the name and does not read the
    certificate, so with no `ca` the sign-in could fail at sign-in time. A certificate signed by a
    public authority is no worse off: its root is harmless to give. Nothing is trusted that was not
    named, and the service's check is not touched."""
    names = _sites(config)
    tls = config.network.tls
    if names.scheme == "https" and tls is not None and not tls.ca:
        return Refusal("needs_ca", NEEDS_CA.format(identity=_identity(names)))
    return None


def _identity(names: Sites) -> str:
    """The identity address as the words name it: `id.` in front of the host, the origin's port
    where it is not the scheme's own (the address `derive` returns as `identity`)."""
    default = 443 if names.scheme == "https" else 80
    return f"{names.scheme}://id.{names.host}" + (f":{names.port}" if names.port != default else "")


# ---- the one place -----------------------------------------------------------------------------


def derive(config: OspreyConfig, *, with_sign_in: bool = True) -> PageAddresses | Refusal | None:
    """Every address the page service is given, or the refusal in plain words, or None.

    * The setting off: None, or the cutover's refusal where a GOV.UK deployment's tree is complete
      (ADR-152 Amendment 3, item 4: a deployment with neither front end).
    * On: a `PageAddresses`, or the first refusal of `_on_cloud_platform`, `_origin_problem`,
      `_needs_https` (with sign-in), `_port_taken`, `_needs_trust` and `_needs_ca` (with sign-in).

    `with_sign_in` is whether the deployment runs the identity provider the service signs in
    against: where it does, the service is given **all three** sign-in variables or it is refused,
    never fewer."""
    from harness import pages_service
    from harness.site import PROXY_HTTPS_PORT, REALM

    if not pages_service.enabled(config):
        if pages_service.govuk_tree_is_complete(config):
            return Refusal("cutover", CUTOVER)
        return None
    in_order = (
        _on_cloud_platform,
        _origin_problem,
        *((_needs_https,) if with_sign_in else ()),
        _port_taken,
        *((_needs_trust, _needs_ca) if with_sign_in else ()),
    )
    for check in in_order:
        refused = check(config)
        if refused is not None:
            return refused

    names = _sites(config)
    default = 443 if names.scheme == "https" else 80
    suffix = f":{names.port}" if names.port != default else ""
    identity = f"{names.scheme}://id.{names.host}{suffix}"
    tls = config.network.tls
    has_proxy = config.profile in (Profile.LOCAL_LITE, Profile.SMALL)
    own_port = PROXY_HTTPS_PORT if tls is not None else 443
    proxy_https_port = own_port if has_proxy and names.scheme == "https" else None
    extra = names.port if proxy_https_port is not None and names.port != proxy_https_port else None
    has_ca = config.profile is Profile.SMALL and tls is not None and bool(tls.ca)
    trust = CA_IN_SERVICE if has_ca else None
    issuer = f"{identity}/realms/{REALM}"
    return PageAddresses(
        public_origin=f"{names.scheme}://{names.host}{suffix}",
        identity=identity,
        issuer=issuer,
        identity_alias=f"id.{names.host}",
        identity_port=names.port,
        extra_listener=extra,
        proxy_https_port=proxy_https_port,
        trust=trust,
    )


def require(config: OspreyConfig, *, with_sign_in: bool = True) -> PageAddresses | None:
    """`derive`, with a refusal raised as the error that names it (`ERRORS`), in its words: what
    every renderer calls, so that a deployment whose page service cannot sign anyone in is refused
    at render time, in words, and nothing is rendered."""
    got = derive(config, with_sign_in=with_sign_in)
    if isinstance(got, Refusal):
        raise got.error()
    return got
