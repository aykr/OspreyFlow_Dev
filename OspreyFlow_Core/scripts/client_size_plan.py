"""The client-size synthetic dataset's plan (ROUTE_052 step B, `v052-load`): twelve sources, each a
dataset with its own marking, generated deterministically from a seed, row by row, so nothing is
held in memory but the row being written.

Everything here is invented (rule 9). The people are drawn from a synthetic population of "master"
people; each source records some of them under its own ids, with its own spelling of their names
(a variant from the same group, a sound-alike, or a one-letter slip), which is what plants the
spelling variants, the sound-alikes and the cross-dataset `SAME_AS` candidates search is measured
on. Identifiers are kept out of anything real by construction:

- telephone numbers are `+447700` numbers outside the drama block `07700 900xxx` the Prison
  Intelligence Dataset uses;
- National Insurance numbers carry only prefixes HMRC never allocates (`TN`, `NT`, `BG`, `GB`,
  `KN`, `NK`, `ZZ`);
- postcodes start `ZZ`, which is no UK postcode area;
- account numbers are IBANs of the invented bank code `XSYN`;
- e-mail addresses are at `example.org` / `example.net` (RFC 2606);
- IMEIs start `35999`, followed by a Luhn digit.

The plan is pure: it builds rows. `scripts.generate_client_size` writes them to files and
`scripts.load_client_size` loads the files. See
`OspreyFlow_Build/process/lanes/rules/v052-load/DESIGN.md` for the sizes and why they are shaped so.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache, lru_cache, partial
from typing import Any

from scripts import client_size_text as text

#: Bumped whenever a change would make the same seed produce different bytes.
GENERATOR_VERSION = 1

#: The seed the load on the test server uses.
DEFAULT_SEED = 20261116

#: The window every dated row falls in.
WINDOW_START = datetime(2025, 1, 1, tzinfo=UTC)
WINDOW_DAYS = 670  # to early November 2026

#: The planted `SAME_AS` edges' model version, so they can be told from the resolver's own.
SAME_AS_MODEL = "client-size-plant-1"

CREATED_BY = "client-size-generator"


# --- Determinism --------------------------------------------------------------------------------


def rng(seed: int, *parts: object) -> random.Random:
    """A generator for one named thing, the same for the same seed and parts on every machine
    and Python version (`random.Random` seeded with an int is stable; only `seed()` of a str is
    not, which is why the parts are hashed here first)."""
    key = ":".join(str(p) for p in (seed, *parts)).encode()
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


def unit_hash(seed: int, *parts: object) -> float:
    """A float in [0, 1) for one named thing, without building a generator."""
    key = ":".join(str(p) for p in (seed, *parts)).encode()
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big") / 2**64


def scaled(count: int, scale: float, *, floor: int = 1) -> int:
    return max(floor, int(round(count * scale)))


# --- Markings -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Marking:
    classification: str
    handling_code: str
    owning_unit: str
    originator: str

    def as_dict(self) -> dict[str, str]:
        return {
            "classification": self.classification,
            "handling_code": self.handling_code,
            "owning_unit": self.owning_unit,
            "originator": self.originator,
        }


def _m(classification: str, code: str, unit: str) -> Marking:
    return Marking(classification, code, unit, unit)


OFFICIAL_P_RECORDS = _m("OFFICIAL", "P", "unit-records")
OS_C_CUSTODY = _m("OFFICIAL-SENSITIVE", "C", "unit-custody")
OFFICIAL_P_ECONOMIC = _m("OFFICIAL", "P", "unit-economic")
OS_C_COMMS = _m("OFFICIAL-SENSITIVE", "C", "unit-comms")
OS_P_ECONOMIC = _m("OFFICIAL-SENSITIVE", "P", "unit-economic")
SECRET_R_FIU = _m("SECRET", "R", "unit-fiu")
OS_C_INTEL = _m("OFFICIAL-SENSITIVE", "C", "unit-intel")
SECRET_C_INTEL = _m("SECRET", "C", "unit-intel")
SECRET_R_INTEL_COVERT = _m("SECRET", "R", "unit-intel-covert")
OFFICIAL_P_INVESTIGATIONS = _m("OFFICIAL", "P", "unit-investigations")
SECRET_R_COVERT = _m("SECRET", "R", "unit-covert")
OS_R_BORDER = _m("OFFICIAL-SENSITIVE", "R", "unit-border")


# --- Names --------------------------------------------------------------------------------------

#: Forename groups: each tuple is one name as differently spelt (variants, sound-alikes,
#: transliterations, accented and folded forms). The first is the commonest spelling.
FORENAME_GROUPS: tuple[tuple[str, ...], ...] = (
    ("Mohammed", "Muhammad", "Mohamed", "Mohamad", "Mohammad", "Muhammed", "Mohammod"),
    ("Ahmed", "Ahmad", "Ahmet", "Achmed"),
    ("Yusuf", "Yousef", "Youssef", "Yousuf", "Yosef"),
    ("Ibrahim", "Ebrahim", "Ibraheem"),
    ("Hussain", "Hussein", "Husain", "Hossein"),
    ("Fatima", "Fatimah", "Fatma"),
    ("Aisha", "Ayesha", "Aysha", "Aishah"),
    ("Stephen", "Steven", "Stefan", "Steffan"),
    ("Catherine", "Katherine", "Kathryn", "Catharine", "Katharine"),
    ("John", "Jon", "Jonathan", "Johnathan"),
    ("Sean", "Shaun", "Shawn", "Seán"),
    ("Siobhan", "Shivaun", "Siobhán"),
    ("Niamh", "Neve", "Neave"),
    ("Zoe", "Zoë", "Zoey"),
    ("Jakub", "Jacob", "Jakob", "Yakub"),
    ("Aleksander", "Alexander", "Aleksandr", "Oleksandr", "Alexandre"),
    ("Joanna", "Johanna", "Joana"),
    ("Lewis", "Louis", "Luis"),
    ("Claire", "Clare", "Clair"),
    ("Ann", "Anne", "Anna"),
    ("Philip", "Phillip", "Filip"),
    ("Geoffrey", "Jeffrey", "Jeffery", "Geoffry"),
    ("Sophie", "Sophia", "Sofia", "Sofie"),
    ("Michael", "Micheal", "Michal", "Mikhail"),
    ("Daniel", "Daniël", "Danyal"),
    ("Isaac", "Isaak", "Izaak"),
    ("Chloe", "Chloé", "Khloe"),
    ("Rebecca", "Rebekah", "Rebeca"),
    ("Jose", "José", "Josè"),
    ("Renee", "Renée", "Renae"),
    ("Lukasz", "Łukasz", "Lucas", "Lukas"),
    ("Grace", "Grayce"),
    ("Olivia", "Olivea"),
    ("Thomas", "Tomas", "Tomasz", "Tommaso"),
    ("Peter", "Piotr", "Pieter", "Pete"),
    ("Kieran", "Ciaran", "Kieron", "Ciarán"),
    ("Imran", "Imraan"),
    ("Bilal", "Belal"),
    ("Priya", "Preeya"),
    ("Mei", "May"),
    ("Abdul", "Abdel", "Abdal"),
    ("Omar", "Umar", "Omer"),
    ("Ruth",),
    ("Harriet",),
    ("Callum", "Calum", "Kallum"),
    ("Megan", "Meghan", "Meagan"),
    ("Hannah", "Hanna", "Hana"),
    ("Liam",),
    ("Ellie", "Elly", "Ellie-May"),
    ("Tariq", "Tarik", "Tareq"),
)

#: Surname groups, as the forenames.
SURNAME_GROUPS: tuple[tuple[str, ...], ...] = (
    ("Smith", "Smyth", "Smithe"),
    ("Thompson", "Thomson", "Tomson"),
    ("Macdonald", "McDonald", "MacDonald", "Mcdonald"),
    ("O'Brien", "OBrien", "O Brien", "O'Bryan"),
    ("Reid", "Reed", "Read", "Reade"),
    ("Clarke", "Clark", "Clerk"),
    ("Khan", "Kahn", "Khaan"),
    ("Chaudhry", "Choudhury", "Chowdhury", "Chaudhary", "Choudhary"),
    ("Nowak", "Novak", "Nowack"),
    ("Kowalski", "Kowalsky", "Kovalski"),
    ("Stewart", "Stuart", "Steward"),
    ("Gray", "Grey"),
    ("Phillips", "Philips", "Phillipps"),
    ("Davies", "Davis", "Davys"),
    ("Rahman", "Rehman", "Rahmen"),
    ("Muller", "Müller", "Mueller", "Miller"),
    ("Siddiqui", "Siddiqi", "Siddique"),
    ("Ali", "Aly", "Alli"),
    ("Walsh", "Welsh", "Walshe"),
    ("Fernandes", "Fernandez", "Fernandas"),
    ("Al-Hassan", "Alhassan", "El Hassan", "Al Hasan"),
    ("Abdullah", "Abdulla", "Abdallah"),
    ("Hussain", "Hussein", "Husain"),
    ("Mohammed", "Muhammad", "Mohamed"),
    ("Nguyen", "Nguyễn", "Ngyuen"),
    ("Kaur", "Kour"),
    ("Singh", "Sing"),
    ("Begum", "Begam"),
    ("Okafor", "Okafo"),
    ("Adeyemi", "Adeyemmi"),
    ("Dvorak", "Dvořák", "Dvorack"),
    ("Kelly", "Kelley", "Kelli"),
    ("Byrne", "Byrnes", "Beirne"),
    ("Lloyd", "Loyd", "Floyd"),
    ("Vaughan", "Vaughn", "Vaugn"),
    ("Mackenzie", "McKenzie", "MacKenzie"),
    ("Jones",),
    ("Williams", "Willliams"),
    ("Patel", "Pattel"),
    ("Wright", "Right", "Rite"),
)

#: Syllables the invented surnames are made from (so the population has thousands of family names,
#: not just the groups above). Checked against the Prison Intelligence Dataset's names (a test).
_SURNAME_HEADS = (
    "Ash",
    "Bram",
    "Carr",
    "Dun",
    "Elm",
    "Fen",
    "Gar",
    "Hal",
    "Ing",
    "Kel",
    "Lang",
    "Mar",
    "Nor",
    "Pen",
    "Quin",
    "Ros",
    "Sel",
    "Tam",
    "Ul",
    "Ver",
    "Wex",
    "Yar",
    "Bro",
    "Cal",
    "Har",
    "Lyn",
    "Mor",
    "Ock",
    "Rad",
    "Stan",
)
_SURNAME_TAILS = (
    "by",
    "ton",
    "wick",
    "ley",
    "ham",
    "worth",
    "field",
    "more",
    "stead",
    "cott",
    "ridge",
    "bury",
    "well",
    "hope",
    "lock",
    "sey",
    "nell",
    "drew",
    "away",
    "low",
)

#: Sound-alike rewrites a source may apply to an invented surname (one each way).
_SOUND_ALIKES = (("ph", "f"), ("ck", "k"), ("y", "ie"), ("ey", "y"), ("c", "k"), ("w", ""))


@cache
def invented_surnames() -> tuple[str, ...]:
    from demo_fixtures.pid_names import SURNAMES as PID_SURNAMES

    taken = {s.lower() for s in PID_SURNAMES}
    names = sorted({h + t for h in _SURNAME_HEADS for t in _SURNAME_TAILS} - {"Wrightley"})
    return tuple(n for n in names if n.lower() not in taken)


def sound_alike(name: str, r: random.Random) -> str:
    """A spelling that sounds the same, or the name itself when no rule applies."""
    rules = [(a, b) for a, b in _SOUND_ALIKES if a in name.lower()]
    if not rules:
        return name
    a, b = r.choice(rules)
    lowered = name.lower().replace(a, b, 1)
    return lowered[:1].upper() + lowered[1:] if lowered else name


def slip(name: str, r: random.Random) -> str:
    """One keying slip: two letters swapped, a letter dropped or a letter doubled."""
    if len(name) < 4:
        return name
    i = r.randrange(1, len(name) - 1)
    kind = r.randrange(3)
    if kind == 0:
        return name[:i] + name[i + 1] + name[i] + name[i + 2 :]
    if kind == 1:
        return name[:i] + name[i + 1 :]
    return name[:i] + name[i] + name[i:]


# --- The population ------------------------------------------------------------------------------

#: The number of master people at scale 1.
POPULATION = 150_000


@dataclass(frozen=True)
class Master:
    """One synthetic person, as nobody records them: the group and canonical spelling of each
    name, and the facts every source agrees on."""

    index: int
    forename_group: int  # -1: an invented-free forename from the group list's singletons
    forename: str
    surname_group: int  # -1: an invented surname
    surname: str
    date_of_birth: date
    nino: str
    nickname: str


_NICKNAMES = (
    "Bear",
    "Ghost",
    "Shorty",
    "Tiny",
    "Smudge",
    "Ginger",
    "Dodger",
    "Scouse",
    "Spider",
    "Junior",
    "Taff",
    "Jock",
    "Paddy",
    "Lefty",
    "Mouse",
    "Chalky",
    "Dusty",
    "Nobby",
)
_NINO_PREFIXES = ("TN", "NT", "BG", "GB", "KN", "NK", "ZZ")


@lru_cache(maxsize=262_144)
def master(seed: int, index: int) -> Master:
    r = rng(seed, "master", index)
    forename_group = r.randrange(len(FORENAME_GROUPS))
    forename = FORENAME_GROUPS[forename_group][0]
    if r.random() < 0.45:
        surname_group = r.randrange(len(SURNAME_GROUPS))
        surname = SURNAME_GROUPS[surname_group][0]
    else:
        surname_group = -1
        surname = r.choice(invented_surnames())
    born = date(1950, 1, 1) + timedelta(days=r.randrange(365 * 55))
    nino = f"{r.choice(_NINO_PREFIXES)}{index:06d}{'ABCD'[index % 4]}"
    return Master(
        index=index,
        forename_group=forename_group,
        forename=forename,
        surname_group=surname_group,
        surname=surname,
        date_of_birth=born,
        nino=nino,
        nickname=r.choice(_NICKNAMES),
    )


@dataclass(frozen=True)
class Spelling:
    """How one record spells a master's name, and how far it is from the canonical spelling:
    `exact`, `variant` (another spelling in the group), `sound_alike` or `slip`."""

    given: str
    family: str
    distance: str


def spell(seed: int, person: Master, *where: object) -> Spelling:
    """The spelling a record (named by `where`) gives a master."""
    r = rng(seed, "spell", person.index, *where)
    given, family, distance = person.forename, person.surname, "exact"
    roll = r.random()
    if roll < 0.30:
        group = FORENAME_GROUPS[person.forename_group]
        if len(group) > 1:
            given = r.choice(group[1:])
            distance = "variant"
    elif roll < 0.50:
        if person.surname_group >= 0 and len(SURNAME_GROUPS[person.surname_group]) > 1:
            family = r.choice(SURNAME_GROUPS[person.surname_group][1:])
            distance = "variant"
        else:
            changed = sound_alike(family, r)
            if changed != family:
                family, distance = changed, "sound_alike"
    elif roll < 0.58:
        family, distance = slip(family, r), "slip"
    return Spelling(given, family, distance)


_SCORE_BY_DISTANCE = {"exact": 0.99, "variant": 0.94, "sound_alike": 0.9, "slip": 0.86}


def score_for(a: Spelling, b: Spelling, seed: int, *where: object) -> float:
    """A match score for two spellings of the same master: the further either is, the lower."""
    base = min(_SCORE_BY_DISTANCE[a.distance], _SCORE_BY_DISTANCE[b.distance])
    if (a.given, a.family) == (b.given, b.family):
        base = 0.999
    return round(base - unit_hash(seed, "score", *where) * 0.03, 6)


# --- Membership: which masters a source records -------------------------------------------------


def _coprime_multiplier(seed: int, modulus: int, *where: object) -> int:
    r = rng(seed, "multiplier", modulus, *where)
    while True:
        a = r.randrange(1, modulus) if modulus > 1 else 1
        if math.gcd(a, modulus) == 1:
            return a


@dataclass(frozen=True)
class Membership:
    """Record `k` of a source (0 <= k < count) is master `(a*k + b) mod population`: a
    permutation, so a source never records one master twice, and two sources overlap by chance
    (about count_s * count_t / population records), which is where the merge candidates come from.
    The inverse finds a master's record in a source in constant time."""

    population: int
    count: int
    a: int
    b: int
    a_inverse: int

    @classmethod
    def of(cls, seed: int, population: int, count: int, *where: object) -> Membership:
        count = min(count, population)
        a = _coprime_multiplier(seed, population, *where)
        b = rng(seed, "offset", *where).randrange(population)
        return cls(population, count, a, b, pow(a, -1, population) if population > 1 else 0)

    def master_of(self, k: int) -> int:
        return (self.a * k + self.b) % self.population

    def record_of(self, master_index: int) -> int | None:
        k = ((master_index - self.b) * self.a_inverse) % self.population
        return k if k < self.count else None


# --- Identifiers ---------------------------------------------------------------------------------


def msisdn(n: int) -> str:
    """The E.164 form of synthetic number `n`, skipping `+447700900000` to `900999`."""
    if n >= 900_000:
        n += 1_000
    if n >= 1_000_000:
        raise ValueError("the synthetic number range holds 999,000 numbers")
    return f"+447700{n:06d}"


def written_msisdn(e164: str, style: int) -> str:
    """How a source writes a number: national with a space, international with spaces, or bare."""
    national = "0" + e164[3:]
    if style == 0:
        return f"{national[:5]} {national[5:]}"
    if style == 1:
        return f"+44 {e164[3:7]} {e164[7:]}"
    return e164[1:]


def _luhn_digit(digits: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def imei(n: int) -> str:
    body = f"35999{n:09d}"
    return body + _luhn_digit(body)


def iban(n: int) -> str:
    bban = f"XSYN{(n * 7919) % 1_000_000:06d}{n:08d}"
    rearranged = bban + "GB00"
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    check = 98 - int(numeric) % 97
    return f"GB{check:02d}{bban}"


def postcode(n: int) -> str:
    letters = "ABDEFGHJLNPQRSTUWXYZ"
    return f"ZZ{n % 90 + 1} {n % 9 + 1}{letters[n % 20]}{letters[(n // 20) % 20]}"


def pnc_id(index: int) -> str:
    return f"{(index % 30) + 90:02d}/{index:07d}{'ABCDEFGHJKLMNPQRTUVWXY'[index % 22]}"


def prison_number(index: int) -> str:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return (
        f"Z{index % 10_000:04d}{letters[(index // 10_000) % 24]}{letters[(index // 240_000) % 24]}"
    )


def company_number(n: int) -> str:
    return f"CS{n:08d}"


# --- Places and organisations --------------------------------------------------------------------

_TOWN_HEADS = ("East", "West", "North", "South", "Lower", "Upper", "Old", "New", "Kings", "Market")
_TOWN_BODIES = (
    "field",
    "brook",
    "gate",
    "moor",
    "ford",
    "haven",
    "dale",
    "wood",
    "mere",
    "holme",
    "thorpe",
    "bridge",
    "stone",
    "well",
    "cliffe",
)
_STREETS = (
    "Station Road",
    "Church Lane",
    "High Street",
    "Mill Lane",
    "Victoria Road",
    "Park Avenue",
    "Queens Road",
    "Green Lane",
    "Manor Way",
    "Albert Street",
    "Canal Side",
    "Orchard Close",
    "Chapel Row",
    "Forge Lane",
    "Meadow View",
    "Quarry Road",
)
_ORG_WORDS = (
    "Northgate",
    "Riverside",
    "Summit",
    "Harbour",
    "Crescent",
    "Meridian",
    "Beacon",
    "Granite",
    "Silverline",
    "Oakmont",
    "Bluewater",
    "Redfern",
    "Kestrel",
    "Highfield",
    "Lantern",
    "Quayside",
    "Ironbridge",
    "Westmoor",
    "Copperleaf",
    "Falcon",
)
_ORG_TRADES = (
    ("Logistics", "transport"),
    ("Motors", "motor trade"),
    ("Cash and Carry", "wholesale"),
    ("Property Holdings", "real estate"),
    ("Car Wash", "services"),
    ("Lettings", "real estate"),
    ("Imports", "wholesale"),
    ("Security Services", "services"),
    ("Recruitment", "services"),
    ("Food Distribution", "wholesale"),
    ("Construction", "construction"),
    ("Mobile Repairs", "retail"),
    ("Nail Bar", "retail"),
    ("Barbers", "retail"),
    ("Scrap Metal", "recycling"),
    ("Freight Forwarding", "transport"),
)
_COUNTRIES = ("GB", "GB", "GB", "GB", "IE", "NL", "AE", "CY", "PK", "TR", "PL", "ES")
_SUFFIXES = (("Ltd", "Limited", "Ltd."), ("LLP", "L.L.P."), ("Ltd", "Limited"))
_GROUP_NAMES = ("Crew", "Boys", "Firm", "Gang", "Lot", "Family", "Mob")


def town(n: int) -> str:
    return (
        _TOWN_HEADS[n % len(_TOWN_HEADS)]
        + _TOWN_BODIES[(n // len(_TOWN_HEADS)) % len(_TOWN_BODIES)]
    )


def address(seed: int, n: int) -> str:
    r = rng(seed, "address", n)
    return f"{r.randrange(1, 240)} {r.choice(_STREETS)}, {town(r.randrange(150))}"


@dataclass(frozen=True)
class Company:
    index: int
    stem: str
    trade: str
    industry: str
    suffixes: tuple[str, ...]
    country: str

    def name(self, style: int = 0) -> str:
        """Style 0 is the registered name; others are how another source writes it."""
        suffix = self.suffixes[style % len(self.suffixes)]
        stem = self.stem
        if style == 2 and " " not in stem and len(stem) > 6:
            stem = stem[:5] + " " + stem[5:]
        return f"{stem} {self.trade} {suffix}"


def company(seed: int, n: int) -> Company:
    r = rng(seed, "company", n)
    trade, industry = r.choice(_ORG_TRADES)
    stem = r.choice(_ORG_WORDS)
    if n >= len(_ORG_WORDS):
        stem = f"{stem} {town(n // len(_ORG_WORDS))}" if r.random() < 0.5 else stem + str(n % 97)
    return Company(n, stem, trade, industry, r.choice(_SUFFIXES), r.choice(_COUNTRIES))


def group_name(seed: int, n: int) -> str:
    r = rng(seed, "group", n)
    return f"the {town(r.randrange(150))} {r.choice(_GROUP_NAMES)}"


# --- Rows ----------------------------------------------------------------------------------------


@dataclass
class Rows:
    """What one generated row adds to each of the four kinds of file."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    texts: list[dict[str, Any]] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


EVENT_COLUMNS = (
    "event_id",
    "edge_id",
    "edge_type",
    "source_id",
    "target_id",
    "occurred_at",
    "duration_s",
    "cell_site",
    "lat",
    "lon",
    "direction",
    "properties",
)


def node(
    node_id: str, type_: str, props: dict[str, Any], *, locator: str, marking: Marking | None = None
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": node_id, "type": type_, "props": props, "loc": locator}
    if marking is not None:
        row["marking"] = marking.as_dict()
    return row


def edge(
    edge_id: str,
    type_: str,
    source: str,
    target: str,
    *,
    locator: str,
    props: dict[str, Any] | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    occurrences: int = 1,
    marking: Marking | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": edge_id, "type": type_, "s": source, "t": target, "loc": locator}
    if props:
        row["props"] = props
    if valid_from is not None:
        row["from"] = iso(valid_from)
        row["to"] = iso(valid_to) if valid_to is not None else None
    if occurrences != 1:
        row["occ"] = occurrences
    if marking is not None:
        row["marking"] = marking.as_dict()
    return row


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def moment_in_window(r: random.Random) -> datetime:
    return WINDOW_START + timedelta(seconds=r.randrange(WINDOW_DAYS * 86_400))


def event_line(cells: tuple[Any, ...]) -> str:
    """One CSV line; no field holds a comma or a quote but `properties`, which is quoted."""
    *head, properties = cells
    rendered = ["" if c is None else str(c) for c in head]
    blob = json.dumps(properties, separators=(",", ":"), sort_keys=True).replace('"', '""')
    return ",".join(rendered) + f',"{blob}"\n'


def person_props(person: Master, spelling: Spelling, **extra: Any) -> dict[str, Any]:
    props: dict[str, Any] = {
        "family_name": spelling.family,
        "given_names": spelling.given,
        "date_of_birth": person.date_of_birth.isoformat(),
    }
    props.update(extra)
    return props


# --- Sources -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Stream:
    """One kind of row a source generates: how many at scale 1, how many to a file, and the
    function that builds row `i`. Every stream's row count follows `--graph-scale`; the analytics
    rows a stream writes alongside its links follow `--scale` (`_volume`)."""

    name: str
    count: int
    part_size: int
    build: Callable[[Context, int], Rows]


@dataclass(frozen=True)
class Source:
    key: str
    dataset: str
    name: str
    marking: Marking
    description: str
    streams: tuple[Stream, ...]


@dataclass(frozen=True)
class Context:
    seed: int
    scale: float
    graph_scale: float

    def count(self, stream: Stream) -> int:
        return scaled(stream.count, self.graph_scale)

    def n(self, base: int) -> int:
        """A graph-tier size at this context's graph scale."""
        return scaled(base, self.graph_scale)

    @property
    def population(self) -> int:
        return self.n(POPULATION)

    def members(self, source: str, base: int) -> Membership:
        return Membership.of(self.seed, self.population, self.n(base), "members", source)

    def master(self, index: int) -> Master:
        return master(self.seed, index)


# Sizes at scale 1 (see DESIGN.md's table).
N_NOMINALS = 80_000
N_ADDRESSES = 30_000
N_CUSTODY = 30_000
N_ESTABLISHMENTS = 60
N_COMPANIES = 25_000
N_OFFICERS = 20_000
N_SUBSCRIBERS = 40_000
N_SUBSCRIBED_NUMBERS = 50_000
N_NUMBERS = 60_000  # 50,000 subscribed and 10,000 nobody is recorded holding
N_DEVICES = 30_000
N_CELL_SITES = 3_000
N_ACCOUNT_HOLDERS = 30_000
N_ACCOUNTS = 40_000
N_SAR_DOCS = 12_000
N_SAR_PEOPLE = 10_000
N_SAR_ORGS = 3_000
N_SAR_ACCOUNTS = 8_000
N_INTEL_DOCS = 40_000
N_INTEL_PEOPLE = 30_000
N_INTEL_ORGS = 2_000
N_INTEL_PLACES = 5_000
N_INTEL_NUMBERS = 8_000
N_CASE_DOCS = 15_000
N_CASE_PEOPLE = 20_000
N_CASE_PLACES = 3_000
N_COVERT_PEOPLE = 6_000
N_COVERT_GROUPS = 400
N_COVERT_DOCS = 5_000
N_WATCHLIST = 15_000

#: The analytics rows at scale 1: the call records are the source in the tens of millions.
E_CALLS = 60_000_000
E_TRANSACTIONS = 15_000_000
E_SIGHTINGS = 25_000_000

#: Average contacts per number, payees per account and cell sites per device.
CONTACTS = 3.5
PAYEES = 3.0
SITES = 3.0

_GRAPH_PART = 20_000
_EVENT_CALLER_PART = 2_000


def _person_record(
    ctx: Context, source: str, base: int, k: int, node_id: str, **extra: Any
) -> tuple[dict[str, Any], Master, Spelling]:
    m = ctx.master(ctx.members(source, base).master_of(k))
    s = spell(ctx.seed, m, source, k)
    props = person_props(m, s, **extra)
    return node(node_id, "Person", props, locator=f"{source}:person:{k}"), m, s


# nominals: the police nominal index --------------------------------------------------------------


def _nominal(ctx: Context, k: int) -> Rows:
    r = rng(ctx.seed, "nominal", k)
    m = ctx.master(ctx.members("nominals", N_NOMINALS).master_of(k))
    extra: dict[str, Any] = {"pnc_id": pnc_id(m.index)}
    aliases = []
    if r.random() < 0.35:
        aliases.append(m.nickname)
    if r.random() < 0.25:
        other = spell(ctx.seed, m, "nominals-alias", k)
        aliases.append(f"{other.given} {other.family}")
    if aliases:
        extra["aliases"] = aliases
    person, _m, _s = _person_record(
        ctx, "nominals", N_NOMINALS, k, f"cs-nominals-person-{k}", **extra
    )
    place = r.randrange(ctx.n(N_ADDRESSES))
    since = moment_in_window(r) - timedelta(days=r.randrange(2_000))
    link = edge(
        f"cs-nominals-lives-{k}",
        "PRESENT_AT",
        person["id"],
        f"cs-nominals-address-{place}",
        locator=f"nominals:person:{k}",
        valid_from=since,
    )
    return Rows(nodes=[person], edges=[link])


def _nominal_address(ctx: Context, n: int) -> Rows:
    props = {"name": address(ctx.seed, n), "postcode": postcode(n)}
    return Rows(
        nodes=[node(f"cs-nominals-address-{n}", "Location", props, locator=f"nominals:address:{n}")]
    )


# custody: custody and prison records -------------------------------------------------------------


def _establishment_name(n: int) -> str:
    return f"HMP {town(n * 7 + 3)}" if n % 3 else f"{town(n * 7 + 3)} Custody Suite"


def _custody(ctx: Context, k: int) -> Rows:
    r = rng(ctx.seed, "custody", k)
    m = ctx.master(ctx.members("custody", N_CUSTODY).master_of(k))
    person, _m, _s = _person_record(
        ctx,
        "custody",
        N_CUSTODY,
        k,
        f"cs-custody-person-{k}",
        prison_number=prison_number(m.index),
        nino=m.nino,
    )
    edges = []
    for stay in range(1 + (r.random() < 0.5)):
        site = r.randrange(ctx.n(N_ESTABLISHMENTS))
        start = moment_in_window(r) - timedelta(days=r.randrange(900))
        end = start + timedelta(days=r.randrange(1, 400))
        edges.append(
            edge(
                f"cs-custody-held-{k}-{stay}",
                "PRESENT_AT",
                person["id"],
                f"cs-custody-site-{site}",
                locator=f"custody:stay:{k}:{stay}",
                valid_from=start,
                valid_to=end,
            )
        )
    return Rows(nodes=[person], edges=edges)


def _establishment(ctx: Context, n: int) -> Rows:
    props = {"name": _establishment_name(n), "site_ref": f"CS-EST-{n:04d}"}
    return Rows(
        nodes=[node(f"cs-custody-site-{n}", "Location", props, locator=f"custody:site:{n}")]
    )


# companies: the company register ------------------------------------------------------------------


def _company(ctx: Context, n: int) -> Rows:
    c = company(ctx.seed, n)
    props = {
        "name": c.name(0),
        "org_ref": company_number(n),
        "country": c.country,
        "industry": c.industry,
    }
    return Rows(
        nodes=[node(f"cs-companies-org-{n}", "Organisation", props, locator=f"companies:org:{n}")]
    )


def _officer(ctx: Context, k: int) -> Rows:
    r = rng(ctx.seed, "officer", k)
    person, _m, _s = _person_record(ctx, "companies", N_OFFICERS, k, f"cs-companies-person-{k}")
    edges = []
    for j in range(1 + (r.random() < 0.5)):
        org = r.randrange(ctx.n(N_COMPANIES))
        since = moment_in_window(r) - timedelta(days=r.randrange(3_000))
        edges.append(
            edge(
                f"cs-companies-officer-{k}-{j}",
                "MEMBER_OF",
                person["id"],
                f"cs-companies-org-{org}",
                locator=f"companies:appointment:{k}:{j}",
                valid_from=since,
            )
        )
    return Rows(nodes=[person], edges=edges)


# subscribers, calls and cell sites: the communications data ---------------------------------------


def _number_node(ctx: Context, n: int, source: str) -> dict[str, Any]:
    e164 = msisdn(n)
    style = int(unit_hash(ctx.seed, "style", source, n) * 3)
    props = {
        "value_raw": written_msisdn(e164, style),
        "value_normalised": e164,
        "endpoint_kind": "msisdn",
        "e164": e164,
    }
    return node(f"cs-msisdn-{n}", "Endpoint", props, locator=f"{source}:number:{n}")


def _device_node(n: int, source: str) -> dict[str, Any]:
    return node(f"cs-imei-{n}", "Device", {"imei": imei(n)}, locator=f"{source}:device:{n}")


def _subscriber(ctx: Context, k: int) -> Rows:
    r = rng(ctx.seed, "subscriber", k)
    person, _m, _s = _person_record(
        ctx, "subscribers", N_SUBSCRIBERS, k, f"cs-subscribers-person-{k}"
    )
    rows = Rows(nodes=[person])
    numbers = ctx.n(N_SUBSCRIBED_NUMBERS)
    held = [k % numbers] + ([r.randrange(numbers)] if r.random() < 0.25 else [])
    for j, n in enumerate(dict.fromkeys(held)):
        rows.edges.append(
            edge(
                f"cs-subscribers-uses-{k}-{j}",
                "USES",
                person["id"],
                f"cs-msisdn-{n}",
                locator=f"subscribers:contract:{k}:{j}",
                valid_from=moment_in_window(r) - timedelta(days=r.randrange(1_500)),
            )
        )
    if k < ctx.n(N_DEVICES):
        rows.edges.append(
            edge(
                f"cs-subscribers-device-{k}",
                "USES",
                person["id"],
                f"cs-imei-{k}",
                locator=f"subscribers:handset:{k}",
            )
        )
    return rows


def _subscribed_number(ctx: Context, n: int) -> Rows:
    rows = Rows(nodes=[_number_node(ctx, n, "subscribers")])
    if n < ctx.n(N_DEVICES):
        rows.nodes.append(_device_node(n, "subscribers"))
    return rows


def _contacts(ctx: Context, caller: int, numbers: int) -> list[tuple[int, float]]:
    """The numbers `caller` calls, each with its share of the caller's calls."""
    r = rng(ctx.seed, "contacts", caller)
    k = max(1, min(numbers - 1, int(r.expovariate(1 / CONTACTS)) + 1))
    chosen: dict[int, float] = {}
    while len(chosen) < k:
        other = (
            (caller + 1 + int(r.paretovariate(1.2) * 37)) % numbers
            if r.random() < 0.6
            else r.randrange(numbers)
        )
        if other != caller:
            chosen[other] = r.random() + 0.1
    total = sum(chosen.values())
    return [(n, w / total) for n, w in chosen.items()]


def _volume(ctx: Context, total_events: int, nodes: int, r: random.Random) -> float:
    """How many analytics rows one node (a caller, a handset, a payer) writes, before it is
    shared among its links: the source's total at `--scale`, spread over its nodes unevenly."""
    return scaled(total_events, ctx.scale) / max(1, nodes) * r.expovariate(1.0)


def _cell_site_of(ctx: Context, n: int) -> tuple[str, float, float]:
    r = rng(ctx.seed, "cell", n)
    return f"CS-CELL-{n:05d}", round(50.2 + r.random() * 5.3, 5), round(-4.9 + r.random() * 6.5, 5)


def _calls_by(ctx: Context, caller: int) -> Rows:
    """A caller's links to each number it calls, and every call, written together so each link's
    count and dates are exactly its calls'."""
    numbers = ctx.n(N_NUMBERS)
    rows = Rows()
    r = rng(ctx.seed, "calls", caller)
    volume = _volume(ctx, E_CALLS, numbers, r)
    for callee, share in _contacts(ctx, caller, numbers):
        count = max(1, round(volume * share))
        link_id = f"cs-call-{caller}-{callee}"
        first: datetime | None = None
        last: datetime | None = None
        for i in range(count):
            at = moment_in_window(r)
            first = at if first is None or at < first else first
            last = at if last is None or at > last else last
            site, lat, lon = _cell_site_of(ctx, r.randrange(ctx.n(N_CELL_SITES)))
            rows.events.append(
                event_line(
                    (
                        f"cs-call-ev-{caller}-{callee}-{i}",
                        link_id,
                        "COMMUNICATED_WITH",
                        f"cs-msisdn-{caller}",
                        f"cs-msisdn-{callee}",
                        iso(at),
                        r.randrange(3, 1_800),
                        site,
                        lat,
                        lon,
                        "outbound",
                        {"call_type": "voice" if r.random() < 0.8 else "sms"},
                    )
                )
            )
        assert first is not None and last is not None
        rows.edges.append(
            edge(
                link_id,
                "COMMUNICATED_WITH",
                f"cs-msisdn-{caller}",
                f"cs-msisdn-{callee}",
                locator=f"calls:pair:{caller}:{callee}",
                props={"direction": "outbound"},
                valid_from=first,
                valid_to=last,
                occurrences=count,
            )
        )
    return rows


def _call_number(ctx: Context, n: int) -> Rows:
    return Rows(nodes=[_number_node(ctx, n, "calls")])


def _cell_site(ctx: Context, n: int) -> Rows:
    site, _lat, _lon = _cell_site_of(ctx, n)
    props = {"name": f"Mast {site} ({town(n % 150)})", "site_ref": site}
    return Rows(nodes=[node(f"cs-cells-site-{n}", "Location", props, locator=f"cells:site:{n}")])


def _sightings_of(ctx: Context, device: int) -> Rows:
    devices = ctx.n(N_DEVICES)
    r = rng(ctx.seed, "sightings", device)
    volume = _volume(ctx, E_SIGHTINGS, devices, r)
    sites = ctx.n(N_CELL_SITES)
    home = r.randrange(sites)
    rows = Rows(nodes=[_device_node(device, "cells")])
    k = max(1, min(sites, int(r.expovariate(1 / SITES)) + 1))
    chosen = list(
        dict.fromkeys([home] + [(home + r.randrange(1, 25)) % sites for _ in range(k - 1)])
    )
    for site_n in chosen:
        count = max(1, round(volume / len(chosen)))
        site, lat, lon = _cell_site_of(ctx, site_n)
        link_id = f"cs-seen-{device}-{site_n}"
        first: datetime | None = None
        last: datetime | None = None
        for i in range(count):
            at = moment_in_window(r)
            first = at if first is None or at < first else first
            last = at if last is None or at > last else last
            rows.events.append(
                event_line(
                    (
                        f"cs-seen-ev-{device}-{site_n}-{i}",
                        link_id,
                        "PRESENT_AT",
                        f"cs-imei-{device}",
                        f"cs-cells-site-{site_n}",
                        iso(at),
                        None,
                        site,
                        lat,
                        lon,
                        None,
                        {"source": "network-registration"},
                    )
                )
            )
        assert first is not None and last is not None
        rows.edges.append(
            edge(
                link_id,
                "PRESENT_AT",
                f"cs-imei-{device}",
                f"cs-cells-site-{site_n}",
                locator=f"cells:pair:{device}:{site_n}",
                valid_from=first,
                valid_to=last,
                occurrences=count,
            )
        )
    return rows


# transactions: bank account records ---------------------------------------------------------------

_TX_TYPES = ("TRANSFER", "PAYMENT", "PAYMENT", "TRANSFER", "CASH_IN", "CASH_OUT", "DEBIT")
_REFERENCES = (
    "rent",
    "car",
    "loan",
    "gift",
    "invoice",
    "deposit",
    "materials",
    "wages",
    "food",
    "holiday",
    "phone",
    "repairs",
    "x",
    "thanks",
    "",
)


def _account_node(ctx: Context, n: int) -> dict[str, Any]:
    value = iban(n)
    props = {
        "value_raw": " ".join(value[i : i + 4] for i in range(0, len(value), 4)),
        "value_normalised": value,
        "endpoint_kind": "iban",
    }
    return node(f"cs-iban-{n}", "Endpoint", props, locator=f"transactions:account:{n}")


def _account_holder(ctx: Context, k: int) -> Rows:
    r = rng(ctx.seed, "holder", k)
    person, _m, _s = _person_record(
        ctx, "transactions", N_ACCOUNT_HOLDERS, k, f"cs-transactions-person-{k}"
    )
    accounts = ctx.n(N_ACCOUNTS)
    held = [k % accounts] + ([r.randrange(accounts)] if r.random() < 0.3 else [])
    edges = [
        edge(
            f"cs-transactions-holds-{k}-{j}",
            "USES",
            person["id"],
            f"cs-iban-{n}",
            locator=f"transactions:mandate:{k}:{j}",
        )
        for j, n in enumerate(dict.fromkeys(held))
    ]
    return Rows(nodes=[person], edges=edges)


def _payments_by(ctx: Context, payer: int) -> Rows:
    accounts = ctx.n(N_ACCOUNTS)
    r = rng(ctx.seed, "payments", payer)
    volume = _volume(ctx, E_TRANSACTIONS, accounts, r)
    rows = Rows(nodes=[_account_node(ctx, payer)])
    k = max(1, min(accounts - 1, int(r.expovariate(1 / PAYEES)) + 1))
    payees = [p for p in dict.fromkeys(r.randrange(accounts) for _ in range(k)) if p != payer]
    for payee in payees:
        kind = r.choice(_TX_TYPES)
        count = max(1, round(volume / len(payees)))
        link_id = f"cs-tx-{payer}-{payee}"
        total = 0.0
        first: datetime | None = None
        last: datetime | None = None
        for i in range(count):
            at = moment_in_window(r)
            amount = round(min(250_000.0, r.lognormvariate(4.5, 1.4)), 2)
            total += amount
            first = at if first is None or at < first else first
            last = at if last is None or at > last else last
            rows.events.append(
                event_line(
                    (
                        f"cs-tx-ev-{payer}-{payee}-{i}",
                        link_id,
                        "TRANSACTED",
                        f"cs-iban-{payer}",
                        f"cs-iban-{payee}",
                        iso(at),
                        None,
                        None,
                        None,
                        None,
                        None,
                        {
                            "amount": amount,
                            "transaction_type": kind,
                            "reference": r.choice(_REFERENCES),
                        },
                    )
                )
            )
        assert first is not None and last is not None
        rows.edges.append(
            edge(
                link_id,
                "TRANSACTED",
                f"cs-iban-{payer}",
                f"cs-iban-{payee}",
                locator=f"transactions:pair:{payer}:{payee}",
                props={"amount": round(total, 2), "transaction_type": kind},
                valid_from=first,
                valid_to=last,
                occurrences=count,
            )
        )
    return rows


# Narrative sources (SARs, intelligence reports, case files, covert reporting) ---------------------


@dataclass(frozen=True)
class Narrative:
    """A document source: its documents and the subjects (people, organisations, places,
    numbers, accounts) its documents mention, each a node of the source's own."""

    source: str
    kind: str  # text.KINDS key
    docs: int
    people: int
    orgs: int = 0
    places: int = 0
    numbers: int = 0
    accounts: int = 0
    mentions: tuple[int, int] = (1, 4)


SAR = Narrative("sars", "sar", N_SAR_DOCS, N_SAR_PEOPLE, orgs=N_SAR_ORGS, accounts=N_SAR_ACCOUNTS)
INTEL = Narrative(
    "intel",
    "intel",
    N_INTEL_DOCS,
    N_INTEL_PEOPLE,
    orgs=N_INTEL_ORGS,
    places=N_INTEL_PLACES,
    numbers=N_INTEL_NUMBERS,
    mentions=(2, 5),
)
CASE = Narrative(
    "casefiles", "statement", N_CASE_DOCS, N_CASE_PEOPLE, places=N_CASE_PLACES, mentions=(2, 5)
)
COVERT = Narrative(
    "covert", "chis", N_COVERT_DOCS, N_COVERT_PEOPLE, orgs=N_COVERT_GROUPS, mentions=(2, 4)
)


def _intel_marking(ctx: Context, d: int) -> Marking:
    roll = unit_hash(ctx.seed, "intel-marking", d)
    if roll < 0.70:
        return OS_C_INTEL
    if roll < 0.95:
        return SECRET_C_INTEL
    return SECRET_R_INTEL_COVERT


def _subject_person(ctx: Context, spec: Narrative, k: int) -> Rows:
    person, _m, _s = _person_record(
        ctx, spec.source, spec.people, k, f"cs-{spec.source}-person-{k}"
    )
    if spec.source == "covert":
        m = ctx.master(ctx.members("covert", spec.people).master_of(k))
        person["props"]["aliases"] = [m.nickname]
    rows = Rows(nodes=[person])
    r = rng(ctx.seed, spec.source, "ties", k)
    if spec.source in ("casefiles", "covert") and k > 0:
        other = r.randrange(k)
        rows.edges.append(
            edge(
                f"cs-{spec.source}-assoc-{k}",
                "ASSOCIATE_OF",
                person["id"],
                f"cs-{spec.source}-person-{other}",
                locator=f"{spec.source}:tie:{k}",
            )
        )
        if spec.source == "casefiles" and r.random() < 0.5:
            rows.edges.append(
                edge(
                    f"cs-casefiles-family-{k}",
                    "FAMILY_OF",
                    person["id"],
                    f"cs-casefiles-person-{r.randrange(k)}",
                    locator=f"casefiles:family:{k}",
                    props={
                        "relation": r.choice(
                            ("brother", "sister", "cousin", "partner", "mother", "son")
                        )
                    },
                )
            )
    if spec.source == "covert" and ctx.n(spec.orgs) and r.random() < 0.6:
        rows.edges.append(
            edge(
                f"cs-covert-member-{k}",
                "MEMBER_OF",
                person["id"],
                f"cs-covert-group-{r.randrange(ctx.n(spec.orgs))}",
                locator=f"covert:membership:{k}",
            )
        )
    if spec.source == "sars" and ctx.n(spec.accounts):
        rows.edges.append(
            edge(
                f"cs-sars-holds-{k}",
                "USES",
                person["id"],
                f"cs-sars-account-{k % ctx.n(spec.accounts)}",
                locator=f"sars:account-holder:{k}",
            )
        )
    return rows


def _subject_org(ctx: Context, spec: Narrative, n: int) -> Rows:
    if spec.source == "covert":
        props: dict[str, Any] = {"name": group_name(ctx.seed, n)}
        return Rows(
            nodes=[node(f"cs-covert-group-{n}", "Organisation", props, locator=f"covert:group:{n}")]
        )
    # SARs and intelligence name companies on the register, written their own way.
    register = ctx.n(N_COMPANIES)
    c = company(ctx.seed, (n * 7 + (3 if spec.source == "sars" else 11)) % register)
    style = 1 + int(unit_hash(ctx.seed, spec.source, "org-style", n) * 2)
    props = {"name": c.name(style), "org_ref": company_number(c.index)}
    return Rows(
        nodes=[
            node(
                f"cs-{spec.source}-org-{n}", "Organisation", props, locator=f"{spec.source}:org:{n}"
            )
        ]
    )


def _subject_place(ctx: Context, spec: Narrative, n: int) -> Rows:
    props = {"name": address(ctx.seed, n * 13 + 5), "postcode": postcode(n * 13 + 5)}
    return Rows(
        nodes=[
            node(
                f"cs-{spec.source}-place-{n}", "Location", props, locator=f"{spec.source}:place:{n}"
            )
        ]
    )


def _subject_number(ctx: Context, spec: Narrative, n: int) -> Rows:
    target = (n * 7) % ctx.n(N_NUMBERS)
    e164 = msisdn(target)
    props = {
        "value_raw": written_msisdn(e164, n % 3),
        "value_normalised": e164,
        "endpoint_kind": "msisdn",
        "e164": e164,
    }
    return Rows(
        nodes=[
            node(
                f"cs-{spec.source}-number-{n}",
                "Endpoint",
                props,
                locator=f"{spec.source}:number:{n}",
            )
        ]
    )


def _subject_account(ctx: Context, spec: Narrative, n: int) -> Rows:
    value = iban((n * 5) % ctx.n(N_ACCOUNTS))
    props = {"value_raw": value, "value_normalised": value, "endpoint_kind": "iban"}
    return Rows(
        nodes=[
            node(
                f"cs-{spec.source}-account-{n}",
                "Endpoint",
                props,
                locator=f"{spec.source}:account:{n}",
            )
        ]
    )


def _document(ctx: Context, spec: Narrative, d: int) -> Rows:
    r = rng(ctx.seed, spec.source, "doc", d)
    marking = {"intel": _intel_marking(ctx, d)}.get(spec.source)
    when = moment_in_window(r)
    people = ctx.n(spec.people)
    low, high = spec.mentions
    picked = list(dict.fromkeys(r.randrange(people) for _ in range(r.randint(low, high))))
    members = ctx.members(spec.source, spec.people)
    cast: list[text.Mention] = []
    for k in picked:
        m = ctx.master(members.master_of(k))
        # The text names the subject its own way: the record's spelling, or another of the group.
        s = (
            spell(ctx.seed, m, spec.source, k)
            if r.random() < 0.6
            else spell(ctx.seed, m, spec.source, "text", d, k)
        )
        cast.append(text.Mention(f"{s.given} {s.family}", m.nickname, m.date_of_birth))
    extras: dict[str, list[str]] = {}
    links = [(f"cs-{spec.source}-person-{k}", "person", k) for k in picked]
    for kind, count, label in (
        ("org", spec.orgs, "orgs"),
        ("place", spec.places, "places"),
        ("number", spec.numbers, "numbers"),
        ("account", spec.accounts, "accounts"),
    ):
        if count and r.random() < 0.7:
            n = r.randrange(ctx.n(count))
            subject = _subject_node(ctx, spec, kind, n)
            extras.setdefault(label, []).append(_display(subject))
            links.append((subject["id"], kind, n))
    body = text.compose(spec.kind, r, cast, extras, when)
    title = text.title(spec.kind, r, cast, extras, when)
    doc_id = f"cs-{spec.source}-doc-{d}"
    props = {"title": title, "sent_at": iso(when), "media_kind": "text"}
    rows = Rows(
        nodes=[node(doc_id, "Document", props, locator=f"{spec.source}:doc:{d}", marking=marking)]
    )
    for subject_id, kind, n in links:
        rows.edges.append(
            edge(
                f"cs-{spec.source}-mention-{d}-{kind}-{n}",
                "MENTIONED_IN",
                subject_id,
                doc_id,
                locator=f"{spec.source}:doc:{d}:{kind}:{n}",
                marking=marking,
            )
        )
    owning = (marking or SOURCES_BY_KEY[spec.source].marking).owning_unit
    rows.texts.append({"document_id": doc_id, "owning_unit": owning, "text": body})
    return rows


def _subject_node(ctx: Context, spec: Narrative, kind: str, n: int) -> dict[str, Any]:
    build = {
        "org": _subject_org,
        "place": _subject_place,
        "number": _subject_number,
        "account": _subject_account,
    }[kind]
    return build(ctx, spec, n).nodes[0]


def _display(subject: dict[str, Any]) -> str:
    props = subject["props"]
    return str(props.get("name") or props.get("value_raw") or props.get("value_normalised"))


def _subject_row(
    build: Callable[[Context, Narrative, int], Rows], spec: Narrative, ctx: Context, n: int
) -> Rows:
    return build(ctx, spec, n)


def _narrative_streams(spec: Narrative) -> tuple[Stream, ...]:
    streams = [
        Stream("documents", spec.docs, 5_000, lambda ctx, d: _document(ctx, spec, d)),
        Stream("people", spec.people, _GRAPH_PART, lambda ctx, k: _subject_person(ctx, spec, k)),
    ]
    for name, count, build in (
        ("orgs", spec.orgs, _subject_org),
        ("places", spec.places, _subject_place),
        ("numbers", spec.numbers, _subject_number),
        ("accounts", spec.accounts, _subject_account),
    ):
        if count:
            streams.append(Stream(name, count, _GRAPH_PART, partial(_subject_row, build, spec)))
    return tuple(streams)


# watchlist: a border watchlist ---------------------------------------------------------------


def _watchlisted(ctx: Context, k: int) -> Rows:
    r = rng(ctx.seed, "watchlist", k)
    m = ctx.master(ctx.members("watchlist", N_WATCHLIST).master_of(k))
    aliases = []
    for j in range(r.randint(1, 3)):
        s = spell(ctx.seed, m, "watchlist-alias", k, j)
        aliases.append(f"{s.given} {s.family}")
    if r.random() < 0.3:
        aliases.append(f"{m.surname.upper()}, {m.forename}")
    person, _m, _s = _person_record(
        ctx,
        "watchlist",
        N_WATCHLIST,
        k,
        f"cs-watchlist-person-{k}",
        aliases=aliases,
        listing="sanction" if r.random() < 0.2 else "adverse_media",
        list_name="Synthetic Border Watchlist",
        nino=m.nino,
    )
    return Rows(nodes=[person])


# The twelve sources --------------------------------------------------------------------------

SOURCES: tuple[Source, ...] = (
    Source(
        "nominals",
        "cs-nominals",
        "Nominal index (synthetic)",
        OFFICIAL_P_RECORDS,
        "people known to police, their PNC ids, aliases and home addresses",
        (
            Stream("addresses", N_ADDRESSES, _GRAPH_PART, _nominal_address),
            Stream("people", N_NOMINALS, _GRAPH_PART, _nominal),
        ),
    ),
    Source(
        "custody",
        "cs-custody",
        "Custody and prison records (synthetic)",
        OS_C_CUSTODY,
        "people held, by prison number and NINO, and where and when",
        (
            Stream("establishments", N_ESTABLISHMENTS, _GRAPH_PART, _establishment),
            Stream("people", N_CUSTODY, _GRAPH_PART, _custody),
        ),
    ),
    Source(
        "companies",
        "cs-companies",
        "Company register (synthetic)",
        OFFICIAL_P_ECONOMIC,
        "companies and their officers",
        (
            Stream("companies", N_COMPANIES, _GRAPH_PART, _company),
            Stream("officers", N_OFFICERS, _GRAPH_PART, _officer),
        ),
    ),
    Source(
        "subscribers",
        "cs-subscribers",
        "Subscriber records (synthetic)",
        OS_C_COMMS,
        "who holds which number and handset",
        (
            Stream("numbers", N_SUBSCRIBED_NUMBERS, _GRAPH_PART, _subscribed_number),
            Stream("people", N_SUBSCRIBERS, _GRAPH_PART, _subscriber),
        ),
    ),
    Source(
        "calls",
        "cs-calls",
        "Call records (synthetic)",
        OS_C_COMMS,
        "every call between numbers: the source in the tens of millions",
        (
            Stream("numbers", N_NUMBERS, _GRAPH_PART, _call_number),
            Stream("calls", N_NUMBERS, _EVENT_CALLER_PART, _calls_by),
        ),
    ),
    Source(
        "cells",
        "cs-cells",
        "Cell-site sightings (synthetic)",
        OS_C_COMMS,
        "handsets seen at cell sites",
        (
            Stream("sites", N_CELL_SITES, _GRAPH_PART, _cell_site),
            Stream("sightings", N_DEVICES, _EVENT_CALLER_PART, _sightings_of),
        ),
    ),
    Source(
        "transactions",
        "cs-transactions",
        "Bank transactions (synthetic)",
        OS_P_ECONOMIC,
        "accounts, their holders and every payment between them",
        (
            Stream("accounts", N_ACCOUNTS, _EVENT_CALLER_PART, _payments_by),
            Stream("holders", N_ACCOUNT_HOLDERS, _GRAPH_PART, _account_holder),
        ),
    ),
    Source(
        "sars",
        "cs-sars",
        "Suspicious activity reports (synthetic)",
        SECRET_R_FIU,
        "narrative reports on accounts, people and companies",
        _narrative_streams(SAR),
    ),
    Source(
        "intel",
        "cs-intel",
        "Intelligence reports (synthetic)",
        OS_C_INTEL,
        "narrative reports, each marked OS/C, SECRET/C or SECRET/R",
        _narrative_streams(INTEL),
    ),
    Source(
        "casefiles",
        "cs-casefiles",
        "Case files and statements (synthetic)",
        OFFICIAL_P_INVESTIGATIONS,
        "long witness statements and case notes",
        _narrative_streams(CASE),
    ),
    Source(
        "covert",
        "cs-covert",
        "Covert source reporting (synthetic)",
        SECRET_R_COVERT,
        "covert reporting on groups and their members",
        _narrative_streams(COVERT),
    ),
    Source(
        "watchlist",
        "cs-watchlist",
        "Border watchlist (synthetic)",
        OS_R_BORDER,
        "listed people with their aliases and transliterations",
        (Stream("people", N_WATCHLIST, _GRAPH_PART, _watchlisted),),
    ),
)

SOURCES_BY_KEY = {s.key: s for s in SOURCES}

#: Sources whose streams must load in this order because a later one writes links to an earlier
#: one's nodes (subscribers' numbers and handsets before the calls and the sightings).
LOAD_ORDER = tuple(s.key for s in SOURCES)


def stream_parts(ctx: Context, stream: Stream) -> list[tuple[int, int, int]]:
    """(part number, first row, row after the last) for each file of the stream."""
    total = ctx.count(stream)
    return [
        (p, start, min(start + stream.part_size, total))
        for p, start in enumerate(range(0, total, stream.part_size))
    ]


def build_part(
    ctx: Context, source: Source, stream: Stream, start: int, stop: int
) -> Iterator[Rows]:
    for i in range(start, stop):
        yield stream.build(ctx, i)


# --- The planted merge candidates ---------------------------------------------------------------

#: Source pairs whose shared people are planted as `SAME_AS` candidates, with the share planted.
#: Most cross access: an OFFICIAL record and a SECRET or restricted one of the same person.
SAME_AS_PAIRS: tuple[tuple[str, int, str, int, float], ...] = (
    ("nominals", N_NOMINALS, "custody", N_CUSTODY, 0.6),
    ("nominals", N_NOMINALS, "intel", N_INTEL_PEOPLE, 0.5),
    ("nominals", N_NOMINALS, "watchlist", N_WATCHLIST, 0.6),
    ("intel", N_INTEL_PEOPLE, "covert", N_COVERT_PEOPLE, 0.7),
    ("subscribers", N_SUBSCRIBERS, "transactions", N_ACCOUNT_HOLDERS, 0.4),
    ("casefiles", N_CASE_PEOPLE, "nominals", N_NOMINALS, 0.5),
    ("transactions", N_ACCOUNT_HOLDERS, "sars", N_SAR_PEOPLE, 0.7),
    ("companies", N_OFFICERS, "sars", N_SAR_PEOPLE, 0.5),
)


#: Of every 100 planted person candidates, how many are near misses: two different people with the
#: same surname, scored low. They are what a careless merge would join.
DECOYS_PER_HUNDRED = 8

#: How many records a near-miss search looks at before giving up on that candidate.
_NEAR_MISS_TRIES = 3_000


def same_as_rows(
    ctx: Context, left: str, left_base: int, right: str, right_base: int, share: float
) -> Iterator[dict[str, Any]]:
    """The planted person candidates between two sources, in record order of the left source:
    `truth` is `same` for two records of one master and `different` for a near miss."""
    a = ctx.members(left, left_base)
    b = ctx.members(right, right_base)
    for k in range(a.count):
        m_index = a.master_of(k)
        j = b.record_of(m_index)
        if j is None:
            continue
        where = (left, right, k)
        if unit_hash(ctx.seed, "plant", *where) >= share:
            continue
        m = ctx.master(m_index)
        sa, sb = spell(ctx.seed, m, left, k), spell(ctx.seed, m, right, j)
        if unit_hash(ctx.seed, "decoy", *where) < DECOYS_PER_HUNDRED / 100:
            other = _near_miss(ctx, b, m, j)
            if other is None:
                continue
            j = other
            sb = spell(ctx.seed, ctx.master(b.master_of(j)), right, j)
            score = round(0.35 + unit_hash(ctx.seed, "decoy-score", *where) * 0.3, 6)
            truth = "different"
        else:
            score = score_for(sa, sb, ctx.seed, *where)
            truth = "same"
        yield _same_as(
            f"cs-same-{left}-{k}-{right}-{j}",
            f"cs-{left}-person-{k}",
            f"cs-{right}-person-{j}",
            score,
            truth,
            [sa.distance, sb.distance],
        )


def _near_miss(ctx: Context, members: Membership, m: Master, own: int) -> int | None:
    """Another record of the right source whose master has `m`'s canonical surname."""
    r = rng(ctx.seed, "near-miss", m.index)
    start = r.randrange(members.count)
    for step in range(min(_NEAR_MISS_TRIES, members.count)):
        j = (start + step) % members.count
        if j == own:
            continue
        other = ctx.master(members.master_of(j))
        if other.index != m.index and other.surname == m.surname:
            return j
    return None


def _same_as(
    edge_id: str, source: str, target: str, score: float, truth: str, distance: list[str]
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "s": source,
        "t": target,
        "score": score,
        "truth": truth,
        "distance": distance,
    }


def same_as_identifier_rows(ctx: Context, kind: str) -> Iterator[dict[str, Any]]:
    """Candidates on a shared identifier: a narrative source's organisation, account or number
    and the register's, the bank's or the network's record of the same thing, held at different
    access. Scored high (the identifier agrees), but still `inferred` until a person confirms."""
    if kind == "orgs":
        for source, offset, count in (("sars", 3, N_SAR_ORGS), ("intel", 11, N_INTEL_ORGS)):
            for n in range(ctx.n(count)):
                c = (n * 7 + offset) % ctx.n(N_COMPANIES)
                yield _same_as(
                    f"cs-same-{source}-org-{n}",
                    f"cs-{source}-org-{n}",
                    f"cs-companies-org-{c}",
                    round(0.95 + unit_hash(ctx.seed, "org", source, n) * 0.04, 6),
                    "same",
                    ["identifier", "name-style"],
                )
    elif kind == "accounts":
        for n in range(ctx.n(N_SAR_ACCOUNTS)):
            target = (n * 5) % ctx.n(N_ACCOUNTS)
            yield _same_as(
                f"cs-same-sars-account-{n}",
                f"cs-sars-account-{n}",
                f"cs-iban-{target}",
                0.999,
                "same",
                ["identifier", "identifier"],
            )
    elif kind == "numbers":
        for n in range(ctx.n(N_INTEL_NUMBERS)):
            target = (n * 7) % ctx.n(N_NUMBERS)
            yield _same_as(
                f"cs-same-intel-number-{n}",
                f"cs-intel-number-{n}",
                f"cs-msisdn-{target}",
                0.999,
                "same",
                ["identifier", "identifier"],
            )
    else:
        raise ValueError(f"no identifier plant called {kind!r}")


#: Every planted file: its name and the rows it holds.
def same_as_plants(ctx: Context) -> list[tuple[str, Callable[[], Iterator[dict[str, Any]]]]]:
    plants: list[tuple[str, Callable[[], Iterator[dict[str, Any]]]]] = [
        (f"people-{left}-{right}", partial(same_as_rows, ctx, left, lb, right, rb, share))
        for left, lb, right, rb, share in SAME_AS_PAIRS
    ]
    plants += [
        (kind, partial(same_as_identifier_rows, ctx, kind))
        for kind in ("orgs", "accounts", "numbers")
    ]
    return plants
