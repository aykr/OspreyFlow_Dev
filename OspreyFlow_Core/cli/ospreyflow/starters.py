"""Starters: a theme and a domain chosen at install (`06_DECISIONS.md` ADR-138 decision 1).

A starter is named `<theme>-<domain>`. It only pre-fills answers the install already asks — the
brand (`appearance.brand`), for the GOV.UK theme the service's name, organisation and phase, the
demo packs, and whether demo accounts are made — and each can still be changed. The `osprey.yaml`
it makes records the starter as a comment, not a setting: nothing at run time depends on it.

The domain also sets the demo cases' domain packs (ADR-126's `domains`), as ADR-138's table says.
Every domain pack stays in the ontology whatever the starter (ADR-126 is unchanged): the domain
chooses the demo data and what its cases are set to, never what the ontology offers.

This module depends on nothing but the standard library, as the rest of the command does.
"""

from __future__ import annotations

from dataclasses import dataclass

#: ADR-138 decision 1: a theme is an `appearance.brand` value.
THEMES = {
    "ospreyflow": "The base OspreyFlow look",
    "govuk": "The GOV.UK Design System, for a service on a gov.uk domain only",
}
#: The phases a GOV.UK service may be in (`appearance.phase`).
PHASES = ("alpha", "beta", "live", "none")
#: The phase a GOV.UK starter offers first: a newly installed service is not yet live.
DEFAULT_PHASE = "beta"


@dataclass(frozen=True)
class Domain:
    id: str
    label: str
    #: ADR-126: the domain packs each demo case the starter loads is set to.
    case_domains: tuple[str, ...]
    #: The demo packs loaded, in order.
    demo_packs: tuple[str, ...]
    #: Whether the install makes the demo accounts.
    demo_accounts: bool
    #: The GOV.UK service name offered first (the install still asks, and refuses none). It names
    #: the service the whole deployment is, which holds many cases — never one demo case's name
    #: (build-order step 9d finding 3: "Prison Intelligence" showed on every case).
    service_name: str | None
    #: Said at the end of the install.
    note: str = ""


DOMAINS: dict[str, Domain] = {
    "crime": Domain(
        "crime",
        "Crime and intelligence analysis",
        ("niem",),
        ("prison-intelligence", "hmp"),
        True,
        "Analyse crime intelligence",
    ),
    "aml": Domain(
        "aml",
        "Anti-money laundering",
        ("fibo",),
        ("operation-ledger",),
        True,
        "Investigate money laundering",
        "Operation Ledger brings its synthetic screening lists; its typology and screening "
        "templates are deployed in the case as its walkthrough describes (DEMO_GUIDE.md §8b).",
    ),
    "fraud": Domain(
        "fraud",
        "Fraud detection",
        ("fibo",),
        ("fixture-corp",),
        True,
        "Investigate fraud",
        "PaySim (6.36 million simulated mobile-money transactions) is offered as your own "
        "download, never fetched by the install: get it from https://www.kaggle.com/datasets/"
        "ealaxi/paysim1, then run ospreyflow demo add paysim --file <path>.",
    ),
    "cyber": Domain(
        "cyber",
        "Cyber threat analysis (STIX 2.1)",
        ("stix",),
        ("cyber-intrusion",),
        True,
        "Investigate cyber incidents",
        "A public network-traffic dataset can be added beside it: ospreyflow demo add public "
        "--file <path> --manifest vast-2012-mc2 (section 1a of the administration guide).",
    ),
    "blank": Domain(
        "blank",
        "Blank: a real service starting from nothing",
        (),
        (),
        False,
        None,
        "No demo case and no demo accounts were made. Every domain pack is available to the "
        "cases you create.",
    ),
}


class UnknownStarter(ValueError):
    """The name is not a starter; the message lists them."""


@dataclass(frozen=True)
class Starter:
    theme: str
    domain: Domain

    @property
    def name(self) -> str:
        return f"{self.theme}-{self.domain.id}"

    @property
    def govuk(self) -> bool:
        return self.theme == "govuk"


def names() -> list[str]:
    return [f"{theme}-{domain}" for theme in THEMES for domain in DOMAINS]


def parse(name: str) -> Starter:
    theme, _, domain = name.partition("-")
    if theme not in THEMES or domain not in DOMAINS:
        raise UnknownStarter(
            f"there is no starter called {name!r}; the starters are {', '.join(names())} "
            "(ospreyflow starters lists them)"
        )
    return Starter(theme, DOMAINS[domain])


def comment(starter: Starter, demo_packs: tuple[str, ...]) -> str:
    """The lines a starter's `osprey.yaml` begins with (ADR-138 decision 1)."""
    packs = ", ".join(demo_packs) if demo_packs else "none"
    return (
        f"# Starter: {starter.name} (ADR-138). A record of the answers it pre-filled, not a "
        "setting:\n"
        f"# theme {starter.theme}; domain {starter.domain.id}; demo packs: {packs}.\n"
    )


def listing() -> list[str]:
    """What `ospreyflow starters` prints: the theme × domain table, then one command per starter."""
    lines = ["Themes:"]
    lines += [f"  {theme}: {about}" for theme, about in THEMES.items()]
    lines.append("Domains:")
    for domain in DOMAINS.values():
        packs = ", ".join(domain.demo_packs) or "no demo data"
        cases = ", ".join(domain.case_domains) or "none chosen"
        accounts = "" if domain.demo_accounts else "; no demo accounts"
        lines.append(f"  {domain.id}: {domain.label} — demo packs: {packs}; case domains: "
                     f"{cases}{accounts}")  # fmt: skip
    lines.append("Starters (ospreyflow install --mode lite --starter <name>):")
    for name in names():
        starter = parse(name)
        extra = ' --service-name "…"' if starter.govuk else ""
        lines.append(f"  {name}: ospreyflow install --mode lite --starter {name}{extra}")
    return lines
