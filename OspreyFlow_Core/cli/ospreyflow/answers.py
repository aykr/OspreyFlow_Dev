"""The install answers file, `install.yaml` (`06_DECISIONS.md` ADR-114 Amendment 3 decision 5): what
every question writes — the guided page, the prompts, or a hand-written file passed to
`ospreyflow install --config` — and the `osprey.yaml` it becomes. One file, so a person at the page,
a person at the prompts and CI install the same way.

    mode: lite                     # lite | small | enterprise
    components:
      dashboards: true             # report-sync and Superset (`reporting:`); on by default
    folders:                       # host folders; absolute, or under the home folder with ~
      ingest: ~/OspreyFlow/ingest  # what the Ingest Studio lists (read-only to the Conduit)
      tiles: ~/OspreyFlow/basemap  # where a built basemap lives
    models:
      local_only: true             # no case content leaves the deployment
    demo_packs: [operation-ledger, hmp]
    paysim_file: ~/Downloads/PS_20174392719_1491204439457_log.csv
    mail:                          # optional: invitations by email (ADR-114 Amendment 5)
      host: smtp.example.org       #   its password is never an answer: set OSPREY_SMTP_PASSWORD
      port: 587
      from: osprey@example.org
      starttls: true
      username: osprey-mailer      #   leave out for a relay that takes mail without signing in
    cloud:                         # small and enterprise only
      provider: aws                # aws | azure
      region: eu-west-2
      domain: osprey.example.org
      dns_zone: example.org        # optional: the Route 53 / Azure DNS zone to add the record to
      admin_email: ops@example.org # optional: the first administrator's email
      api_cidrs: [203.0.113.0/24]  # enterprise with --cloud: who reaches the cluster's API (05 §3b)
    external:                      # written by OpenTofu for the server's first boot: the managed
      postgres: {host: …}          #   services (`05_DEPLOYMENT.md` §3a), copied into osprey.yaml
    cluster:                       # enterprise only (05 §3b)
      namespace: ospreyflow        #   the Kubernetes namespace
      storage_class: gp3           #   each store's own volumes; the cluster's default when left out
      shared_storage_class: efs-sc #   the volume every Conduit shares: EFS on AWS, Azure Files
    server:                        # small only (ADR-114 Amendment 33): a server you provide,
      address: https://osprey.example.internal   # every store in a container; https:// only
      certificate: /etc/ospreyflow/tls/osprey.crt  # PEM: the certificate, then its intermediates
      key: /etc/ospreyflow/tls/osprey.key          # PEM, unencrypted, mode 600
      ca: /etc/ospreyflow/tls/org-root.pem         # optional: the organisation's root
      ingest: /srv/ospreyflow/ingest   # folders.ingest: where the CSV exports are put
      redirect_http: false         #   true also publishes 80, only to send people to 443
      listen_address: 192.0.2.10   #   optional: one interface of the server; default every one
      backups: /srv/ospreyflow/backups  # where `ospreyflow backup` writes; ~/OspreyFlow/backups
      memory_gib: auto             #   or a number (GiB): what the stores are sized to
      gpu: nvidia                  #   optional: the local engine on the server's NVIDIA GPU; none
    sign_in:                       # small on a server, optional; without it, local accounts only
      organisation:                #   the organisation's OpenID Connect provider (Entra ID, ADFS…)
        alias: org                 #   in the address the organisation registers; default org
        label: Example Department account  # its name on the sign-in pages
        issuer: https://login.microsoftonline.com/<tenant>/v2.0
        client_id: 00000000-0000-0000-0000-000000000000
        # its client secret is never an answer: set OSPREY_ORG_SIGN_IN_SECRET for the install
    admin_email: ops@example.org   # small on a server: the first administrator's email
    config: ./osprey.yaml          # instead of the sections above: use this osprey.yaml as it is
    starter: govuk-crime           # ADR-138: a theme and a domain, pre-filling the answers below
    appearance:                    # the look (appearance.* in osprey.yaml)
      brand: govuk                 #   ospreyflow | govuk
      service_name: Analyse crime intelligence   # GOV.UK: required; names the whole service
      organisation: Example Department
      phase: beta                  #   alpha | beta | live | none
    demo_accounts: true            # false for no demo accounts (the blank starter's answer)

Unknown keys are refused by name, as `osprey.yaml`'s are, so a typo never silently means the
default. This module depends on nothing but PyYAML: the command is small, and the deployment's own
schema checks the result when it is rendered.
"""

from __future__ import annotations

import copy
import ipaddress
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from ospreyflow import starters
from ospreyflow.home import LITE_ORIGIN

MODES = ("lite", "small", "enterprise")
CLOUDS = ("aws", "azure")
#: Each mode's `osprey.yaml` profile (`spec/05_DEPLOYMENT.md` §2).
PROFILES = {"lite": "local-lite", "small": "small", "enterprise": "cluster"}

_TOP = {
    "mode", "components", "folders", "models", "demo_packs", "paysim_file", "cloud", "config",
    "mail", "external", "cluster", "starter", "appearance", "demo_accounts", "server",
    "admin_email", "sign_in",
}  # fmt: skip
#: ADR-114 Amendment 33: `server:` (drop 1), with `backups` and `memory_gib` (drop 2, units 5–6),
#: and ADR-135 Amendment 1's `gpu`.
_SERVER = {
    "address", "certificate", "key", "ca", "ingest", "redirect_http", "listen_address",
    "backups", "memory_gib", "gpu",
}  # fmt: skip
#: ADR-135 Amendment 1 decision 1: the GPUs the local engine can be given.
GPUS = ("none", "nvidia")
#: Amendment 33 decision 6 and the owner's answer 16: a server is at least a nominal 32 GB one
#: (30 GiB as Docker reports it is `doctor`'s floor); the sizing rule's own floor is 16.
MIN_MEMORY_GIB = 16
#: Amendment 33 decision 4 (drop 2, unit 7): `sign_in.organisation`.
_SIGN_IN = {"organisation"}
_ORGANISATION = {"alias", "label", "issuer", "client_id"}
#: The provider's alias when none is given: part of the address the organisation registers.
DEFAULT_ORGANISATION_ALIAS = "org"
DEFAULT_ORGANISATION_LABEL = "Organisation account"
#: The organisation's client secret: from the installer's environment only (Amendment 33
#: decision 4).
ORGANISATION_SECRET_VARIABLE = "OSPREY_ORG_SIGN_IN_SECRET"
_SECTIONS = {
    "components": {"dashboards"},
    "folders": {"ingest", "tiles"},
    "models": {"local_only"},
    "cloud": {"provider", "region", "domain", "size", "dns_zone", "admin_email", "api_cidrs"},
    "mail": {"host", "port", "from", "starttls", "username"},
    "cluster": {"namespace", "storage_class", "shared_storage_class"},
    "appearance": {"brand", "service_name", "organisation", "phase"},
}
#: The sections a named `config:` replaces; giving both is refused rather than one silently winning.
_CONFIG_SECTIONS = ("components", "folders", "models")


class AnswersRefused(Exception):
    """The answers cannot be installed from; the message says which key and why."""


@dataclass(frozen=True)
class Answers:
    mode: str
    dashboards: bool = True
    ingest: Path | None = None
    tiles: Path | None = None
    local_only: bool = True
    demo_packs: tuple[str, ...] = ()
    paysim_file: Path | None = None
    cloud: dict[str, str] = field(default_factory=dict)
    config: Path | None = None
    mail: dict[str, Any] = field(default_factory=dict)
    #: The managed services a cloud server runs on (05 §3a); checked by the deployment's schema.
    external: dict[str, Any] = field(default_factory=dict)
    #: Enterprise's namespace and storage classes (05 §3b).
    cluster: dict[str, str] = field(default_factory=dict)
    #: The addresses OpenTofu opens the cluster's API to (ADR-114 Amendment 19): an input to the
    #: build, not a setting of the deployment, so never in `osprey.yaml`.
    api_cidrs: tuple[str, ...] = ()
    #: ADR-138: the starter the answers were pre-filled from, if any (recorded as a comment only).
    starter: starters.Starter | None = None
    #: `appearance.*` as the answers set it (brand, service_name, organisation, phase); empty
    #: leaves the product's own.
    appearance: dict[str, str] = field(default_factory=dict)
    #: Whether the install makes the demo accounts (`--no-demo-accounts` also turns them off).
    demo_accounts: bool = True
    #: ADR-126 `domains` the demo cases are set to: the starter's domain's, else each seed's own.
    case_domains: tuple[str, ...] | None = None
    #: ADR-114 Amendment 33: Small on a server of your own — its address, certificate paths and
    #: options as `osprey.yaml`'s `network` takes them. Empty for every other install.
    server: dict[str, Any] = field(default_factory=dict)
    #: The first administrator's email, on a server of your own (a cloud's is `cloud.admin_email`).
    admin_email: str | None = None
    #: Amendment 33 decision 5: where `ospreyflow backup` writes on a server of your own.
    backups: Path | None = None
    #: Amendment 33 decision 6: `"auto"` (measured by the install), a number of GiB, or None.
    memory_gib: int | str | None = None
    #: ADR-135 Amendment 1: `nvidia` puts the local engine on the server's NVIDIA GPU.
    gpu: str = "none"
    #: Amendment 33 decision 4: the organisation's identity provider — alias, label, issuer and
    #: client id, as `governance` takes them. Empty without `sign_in.organisation`.
    organisation: dict[str, str] = field(default_factory=dict)


def _appearance(section: Mapping[str, Any], starter: starters.Starter | None) -> dict[str, str]:
    """The answers' `appearance`, with the starter's theme as the brand when none is given; a GOV.UK
    service refused in words without its name (ADR-138 decision 1)."""
    chosen = {k: str(v) for k, v in section.items() if v not in (None, "")}
    if starter is not None:
        chosen.setdefault("brand", starter.theme)
        if starter.govuk and chosen["brand"] == "govuk":
            chosen.setdefault("phase", starters.DEFAULT_PHASE)  # a new service is not yet live
    brand = chosen.get("brand")
    if brand is not None and brand not in starters.THEMES:
        raise AnswersRefused(
            f"appearance.brand is one of {', '.join(starters.THEMES)}, not {brand!r}"
        )
    phase = chosen.get("phase")
    if phase is not None and phase not in starters.PHASES:
        raise AnswersRefused(
            f"appearance.phase is one of {', '.join(starters.PHASES)}, not {phase!r}"
        )
    if brand == "govuk" and not chosen.get("service_name", "").strip():
        offered = starter.domain.service_name if starter is not None else None
        example = f" (this starter offers {offered!r})" if offered else ""
        raise AnswersRefused(
            "a GOV.UK service is named in its page title, and no service name was given: give "
            f"appearance.service_name, or --service-name{example}. Name the service the whole "
            "deployment is, since it holds many cases, not one case. Nothing was installed"
        )
    return chosen


def _known(where: str, raw: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise AnswersRefused(
            f"{where} has no setting called {', '.join(repr(k) for k in unknown)}; "
            f"the settings are {', '.join(sorted(allowed))}"
        )


def _host_path(key: str, value: object, home: Path) -> Path:
    text = str(value)
    if text.startswith("~"):
        return home / text[1:].lstrip("/")
    path = Path(text)
    if not path.is_absolute():
        raise AnswersRefused(f"{key} is a relative path ({text}); give it from / or from ~")
    return path


def _boolean(key: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise AnswersRefused(f"{key} is true or false, not {value!r}")
    return value


def _api_cidrs(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AnswersRefused(f"cloud.api_cidrs is a list of addresses, not {value!r}")
    if not value:
        raise AnswersRefused("cloud.api_cidrs names at least one address the operator works from")
    kept = []
    for item in value:
        try:
            network = ipaddress.ip_network(str(item), strict=False)
        except ValueError:
            raise AnswersRefused(
                f"cloud.api_cidrs: {item!r} is not an address range such as 203.0.113.0/24"
            ) from None
        if network.prefixlen == 0:
            raise AnswersRefused(
                f"cloud.api_cidrs: {item} is the whole internet; name the operator's own addresses"
            )
        kept.append(str(item))
    return tuple(kept)


def _server(section: object, mode: str, home: Path) -> dict[str, Any]:
    """ADR-114 Amendment 33 decision 1: `server:`, checked and turned into the `network` settings
    it becomes (`public_origin`, `tls`, `redirect_http`, `listen_address`) and its ingest."""
    if not isinstance(section, Mapping):
        raise AnswersRefused(f"server holds settings, not {section!r}")
    if mode != "small":
        raise AnswersRefused(
            f"server: is for the small mode (Small on a server of your own), not {mode}"
        )
    _known("server", section, _SERVER)
    address = str(section.get("address") or "").strip()
    if not address:
        raise AnswersRefused(
            "server.address is the https:// address people reach the deployment at, for example "
            "https://osprey.example.internal"
        )
    origin = urlsplit(address)
    if origin.scheme != "https" or not origin.hostname:
        raise AnswersRefused(
            f"server.address {address!r} must be an https:// address: a server is reached by "
            "other people over the organisation's network"
        )
    if origin.path not in ("", "/") or origin.query or origin.fragment:
        raise AnswersRefused(
            f"server.address {address!r} names the server and its port only, with no path"
        )
    network: dict[str, Any] = {"public_origin": address.rstrip("/")}
    files = {k: section[k] for k in ("certificate", "key", "ca") if section.get(k)}
    if ("certificate" in files) != ("key" in files):
        raise AnswersRefused(
            "server.certificate and server.key are given both or neither: the certificate and its "
            "key (or neither, for a certificate the front proxy obtains itself)"
        )
    if files:
        tls = {}
        for key, value in files.items():
            text = str(value)
            if not (text.startswith("/") or text.startswith("~")):
                raise AnswersRefused(
                    f"server.{key} is a relative path ({text}); give it from / or from ~"
                )
            tls[key] = str(_host_path(f"server.{key}", value, home))
        network["tls"] = tls
    if "redirect_http" in section:
        network["redirect_http"] = _boolean("server.redirect_http", section["redirect_http"])
    if section.get("listen_address") is not None:
        try:
            ipaddress.ip_address(str(section["listen_address"]))
        except ValueError:
            raise AnswersRefused(
                f"server.listen_address {section['listen_address']!r} is one IP address of the "
                "server, for example 192.0.2.10"
            ) from None
        network["listen_address"] = str(section["listen_address"])
    found: dict[str, Any] = {"network": network}
    if section.get("ingest"):
        found["ingest"] = _host_path("server.ingest", section["ingest"], home)
    if section.get("backups"):
        found["backups"] = _host_path("server.backups", section["backups"], home)
    if section.get("memory_gib") is not None:
        found["memory_gib"] = _memory(section["memory_gib"])
    if section.get("gpu") is not None:
        if section["gpu"] not in GPUS:
            raise AnswersRefused(
                f"server.gpu is none or nvidia (the local engine on the server's NVIDIA GPU), not "
                f"{section['gpu']!r}"
            )
        found["gpu"] = section["gpu"]
    return found


def _memory(value: object) -> int | str:
    """Amendment 33 decision 6: `auto` (the install measures it once, as Docker reports it) or a
    whole number of GiB, at least the sizing rule's floor."""
    if value == "auto":
        return "auto"
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnswersRefused(
            f"server.memory_gib is auto or a number of GiB (for example 64), not {value!r}"
        )
    if value < MIN_MEMORY_GIB:
        raise AnswersRefused(
            f"server.memory_gib is at least {MIN_MEMORY_GIB} (GiB); a server for this mode has "
            f"30 or more, as Docker reports it. {value} was given"
        )
    return value


def _organisation(section: object, server: bool) -> dict[str, str]:
    """Amendment 33 decision 4: `sign_in.organisation`, the organisation's OpenID Connect provider
    brokered by Keycloak; for Small on a server of your own only. Its client secret is never an
    answer."""
    if not isinstance(section, Mapping):
        raise AnswersRefused(f"sign_in holds settings, not {section!r}")
    _known("sign_in", section, _SIGN_IN)
    if not server:
        raise AnswersRefused(
            "sign_in is for Small on a server of your own (with server:); nothing was installed"
        )
    organisation = section.get("organisation")
    if organisation is None:
        return {}
    if not isinstance(organisation, Mapping):
        raise AnswersRefused(f"sign_in.organisation holds settings, not {organisation!r}")
    if any("secret" in str(key).lower() for key in organisation):
        raise AnswersRefused(
            "the organisation's client secret is never written in the answers file: set "
            f"{ORGANISATION_SECRET_VARIABLE} in this terminal for the install (it is kept only in "
            "the deployment's own secrets file)"
        )
    _known("sign_in.organisation", organisation, _ORGANISATION)
    chosen = {
        "alias": str(organisation.get("alias") or DEFAULT_ORGANISATION_ALIAS),
        "label": str(organisation.get("label") or DEFAULT_ORGANISATION_LABEL),
    }
    for key in ("issuer", "client_id"):
        value = str(organisation.get(key) or "").strip()
        if not value:
            raise AnswersRefused(
                f"sign_in.organisation.{key} is needed: "
                + ("the provider's issuer, for example "
                   "https://login.microsoftonline.com/<tenant>/v2.0"
                   if key == "issuer" else
                   "the application (client) id the organisation registered for OspreyFlow")
            )  # fmt: skip
        chosen[key] = value
    if not chosen["issuer"].startswith("https://"):
        raise AnswersRefused(
            f"sign_in.organisation.issuer {chosen['issuer']!r} must be an https:// address"
        )
    chosen["issuer"] = chosen["issuer"].rstrip("/")
    return chosen


def load_answers(
    raw: Mapping[str, Any] | Path, *, packs: Iterable[str], home: Path | None = None
) -> Answers:
    """The answers in `raw` (a mapping, or a path to `install.yaml`), checked. `packs` are the demo
    packs this checkout offers (`scripts/demo_packs.py`); `home` stands in for `~`."""
    home = home or Path.home()
    if isinstance(raw, Path):
        loaded = yaml.safe_load(raw.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise AnswersRefused(f"{raw} does not hold settings")
        raw = loaded
    _known("The answers file", raw, _TOP)
    mode = raw.get("mode")
    if mode not in MODES:
        raise AnswersRefused(f"mode is one of {', '.join(MODES)}, not {mode!r}")
    sections: dict[str, Mapping[str, Any]] = {}
    for name, allowed in _SECTIONS.items():
        section = raw.get(name) or {}
        if not isinstance(section, Mapping):
            raise AnswersRefused(f"{name} holds settings, not {section!r}")
        _known(name, section, allowed)
        sections[name] = section

    config = raw.get("config")
    if config is not None and any(raw.get(name) for name in _CONFIG_SECTIONS):
        raise AnswersRefused(
            "give either config (an osprey.yaml used as it is) or components, folders and models, "
            "not both"
        )

    cloud = {k: str(v) for k, v in sections["cloud"].items() if k != "api_cidrs"}
    api_cidrs: tuple[str, ...] = ()
    if "api_cidrs" in sections["cloud"]:
        if mode != "enterprise":
            raise AnswersRefused(f"cloud.api_cidrs is for the enterprise mode, not {mode}")
        api_cidrs = _api_cidrs(sections["cloud"]["api_cidrs"])
    if mode == "lite" and cloud:
        raise AnswersRefused("cloud settings are for the small and enterprise modes, not lite")
    if cloud and cloud.get("provider") not in CLOUDS:
        raise AnswersRefused(
            f"cloud provider is one of {', '.join(CLOUDS)}, not {cloud.get('provider')!r}"
        )

    external = raw.get("external") or {}
    if not isinstance(external, Mapping):
        raise AnswersRefused(f"external holds settings, not {external!r}")
    if mode == "lite" and external:
        raise AnswersRefused(
            "external services are for the small and enterprise modes, which run on a cloud's "
            "managed services; lite runs its own"
        )

    server: dict[str, Any] = {}
    if raw.get("server") is not None:
        server = _server(raw["server"], str(mode), home)
        if server.get("gpu") == "nvidia" and (raw.get("cloud") or external):
            # ADR-135 Amendment 1 decision 1, said before the general rule below.
            raise AnswersRefused(
                "server.gpu is for a server of your own; a cloud's server (cloud: or external:) is "
                "sized without a GPU. Nothing was installed"
            )
        if raw.get("cloud"):
            raise AnswersRefused(
                "build a server with --cloud (the cloud: settings), or install onto one you have "
                "with server:, not both"
            )
        if external:
            raise AnswersRefused(
                "server: is Small on a server of your own: self-contained means every store in a "
                "container. For a cloud's managed services (external:), leave out server:"
            )
    organisation = (
        _organisation(raw["sign_in"], bool(server)) if raw.get("sign_in") is not None else {}
    )
    admin_email = raw.get("admin_email")
    if admin_email is not None and not server:
        raise AnswersRefused(
            "admin_email is for Small on a server of your own (with server:); a cloud's is "
            "cloud.admin_email"
        )

    cluster = {k: str(v) for k, v in sections["cluster"].items()}
    if cluster and mode != "enterprise":
        raise AnswersRefused(f"cluster settings are for the enterprise mode, not {mode}")

    offered = tuple(packs)
    chosen = tuple(str(p) for p in raw.get("demo_packs") or ())
    for pack in chosen:
        if pack not in offered:
            raise AnswersRefused(
                f"there is no demo pack called {pack!r}; the packs are {', '.join(offered)}"
            )

    if raw.get("paysim_file") and "paysim" not in chosen:
        raise AnswersRefused(
            "paysim_file is the PaySim pack's file, and the paysim pack is not chosen"
        )

    starter: starters.Starter | None = None
    if raw.get("starter") is not None:
        try:
            starter = starters.parse(str(raw["starter"]))
        except starters.UnknownStarter as unknown:
            raise AnswersRefused(str(unknown)) from None
        if "demo_packs" not in raw:
            # Pre-filled: the starter's packs this checkout offers (a cyber starter on a checkout
            # without `cyber-intrusion` loads no demo case, and the install says so).
            chosen = tuple(p for p in starter.domain.demo_packs if p in offered)
    appearance = _appearance(sections["appearance"], starter)
    demo_accounts = _boolean(
        "demo_accounts",
        raw.get("demo_accounts", starter.domain.demo_accounts if starter is not None else True),
    )

    folders = sections["folders"]
    return Answers(
        mode=str(mode),
        dashboards=_boolean(
            "components.dashboards", sections["components"].get("dashboards", True)
        ),
        ingest=server["ingest"]
        if "ingest" in server
        else _host_path("folders.ingest", folders["ingest"], home)
        if "ingest" in folders
        else home / "OspreyFlow" / "ingest",
        tiles=_host_path("folders.tiles", folders["tiles"], home)
        if "tiles" in folders
        else home / "OspreyFlow" / "basemap",
        local_only=_boolean("models.local_only", sections["models"].get("local_only", True)),
        demo_packs=chosen,
        paysim_file=_host_path("paysim_file", raw["paysim_file"], home)
        if raw.get("paysim_file")
        else None,
        cloud=cloud,
        config=_host_path("config", config, home) if config is not None else None,
        mail=dict(sections["mail"]),
        external=copy.deepcopy(dict(external)),
        cluster=cluster,
        api_cidrs=api_cidrs,
        starter=starter,
        appearance=appearance,
        demo_accounts=demo_accounts,
        case_domains=starter.domain.case_domains if starter is not None else None,
        server=server.get("network", {}),
        admin_email=str(admin_email) if admin_email is not None else None,
        backups=server.get("backups", home / "OspreyFlow" / "backups") if server else None,
        memory_gib=server.get("memory_gib"),
        gpu=server.get("gpu", "none"),
        organisation=organisation,
    )


def osprey_config(answers: Answers, base: Mapping[str, Any]) -> dict[str, Any]:
    """The `osprey.yaml` the answers make: the product's committed defaults (`base`) with what the
    answers decide written over them — or, when they name a `config`, that file exactly."""
    if answers.config is not None:
        loaded = yaml.safe_load(answers.config.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise AnswersRefused(f"{answers.config} does not hold settings")
        if answers.appearance:
            # ADR-138: the guided page installs from its draft; the look is a Mode-screen answer.
            loaded["appearance"] = {**(loaded.get("appearance") or {}), **answers.appearance}
        return loaded
    config = copy.deepcopy(dict(base))
    config["profile"] = PROFILES[answers.mode]
    storage = config.setdefault("components", {}).setdefault("storage", {})
    storage["ingest"] = str(answers.ingest)
    storage["tiles"] = str(answers.tiles)
    config.setdefault("models", {})["local_only"] = answers.local_only
    config["reporting"] = {"sync": answers.dashboards, "superset": answers.dashboards}
    if answers.mail:
        config["mail"] = {
            "host": answers.mail.get("host"),
            "port": answers.mail.get("port", 587),
            "from_address": answers.mail.get("from"),
            "starttls": answers.mail.get("starttls", True),
            "username": answers.mail.get("username"),
        }
    if answers.external:
        config["external"] = copy.deepcopy(answers.external)
    if answers.appearance:
        # ADR-138: only what the answers say; the rest of the section stays as the base has it.
        config["appearance"] = {**(config.get("appearance") or {}), **answers.appearance}
    if answers.mode == "enterprise":
        # 05 §3b: a cluster's Conduits share ClickHouse; DuckDB would give each its own events.
        config.setdefault("components", {})["analytics_engine"] = "clickhouse"
        config["cluster"] = {**config.get("cluster", {}), **answers.cluster}
    # ADR-114 Amendment 4: every address derives from this one. Lite answers on this machine by
    # name; a cloud install at the client's own domain, over HTTPS.
    network = config.setdefault("network", {})
    if answers.mode == "lite":
        network["public_origin"] = LITE_ORIGIN
    elif answers.cloud.get("domain"):
        network["public_origin"] = f"https://{answers.cloud['domain']}"
    if answers.server:
        # ADR-114 Amendment 33: the server's address, and its own certificate's paths.
        network.update(copy.deepcopy(answers.server))
    if answers.backups is not None:
        # Amendment 33 decision 5: where `ospreyflow backup` writes on this server.
        storage["backups"] = str(answers.backups)
    if isinstance(answers.memory_gib, int):
        # Decision 6: a number given is written as it is; `auto` is measured by the install.
        config["resources"] = {**(config.get("resources") or {}), "memory_gib": answers.memory_gib}
    if answers.gpu == "nvidia":
        # ADR-135 Amendment 1: written only when asked for, so `none` changes nothing.
        config["resources"] = {**(config.get("resources") or {}), "gpu": "nvidia"}
    if answers.organisation:
        # Decision 4: the organisation's provider, by name and address; its secret is never here.
        governance = config.setdefault("governance", {})
        governance["organisation_sign_in"] = answers.organisation["alias"]
        governance["organisation_provider"] = {
            k: answers.organisation[k] for k in ("label", "issuer", "client_id")
        }
    return config
