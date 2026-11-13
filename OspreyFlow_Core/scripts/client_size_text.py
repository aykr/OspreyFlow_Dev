"""Narrative text for the client-size dataset's documents (ROUTE_052 step B): templated synthetic
prose, no real text (rule 9). Four kinds: an intelligence report (`intel`, about 4 KB), a witness
statement or case note (`statement`, about 8 KB), a suspicious activity report (`sar`, about
2.5 KB) and a covert source's report (`chis`, about 3 KB).

A document names its subjects as its writer spelt them (the caller passes each subject's spelling),
so the full text carries the same spelling variants the records do, and a sound-alike search over
the text has something to find. Every value in the text (a number, an account, a vehicle, an
e-mail address) is as synthetic as the records' (`client_size_plan`'s module note).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class Mention:
    name: str
    nickname: str
    date_of_birth: date


#: The average number of paragraphs per kind, and how far either side a document may go.
KINDS: dict[str, tuple[int, int]] = {
    "intel": (16, 6),
    "statement": (32, 10),
    "sar": (9, 3),
    "chis": (12, 4),
}

_VEHICLES = (
    "a silver hatchback",
    "a black saloon",
    "a white panel van",
    "a dark blue estate",
    "a red pick-up",
    "a grey people carrier",
    "a green motorcycle",
    "a black SUV with tinted windows",
)
_COMMODITIES = (
    "cannabis",
    "cocaine",
    "cash",
    "mobile phones",
    "counterfeit cigarettes",
    "stolen catalytic converters",
    "spice",
    "power tools",
)
_RANKS = ("DC", "PC", "DS", "Sgt", "Insp", "DI")
_STAFF = (
    "Harker",
    "Wendell",
    "Pryor",
    "Asquith",
    "Tolland",
    "Merrow",
    "Ellery",
    "Corder",
    "Brandreth",
    "Lidgate",
)
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_GRADES = ("B2", "B3", "C3", "A2", "B4")

_INTEL = (
    'Intelligence indicates that {p0}, also known as "{nick0}", is involved in the supply of '
    "{commodity} in the {town} area. {p0} is believed to be using {vehicle} to move product "
    "between addresses, and has been seen at {place} on several occasions in recent weeks.",
    "On {weekday} {date} at about {time}, {p0} was seen meeting {p1} outside {place}. The meeting "
    "lasted around ten minutes. A package was passed from {p1} to {p0}, who then left in "
    "{vehicle}. Neither appeared to notice the observation.",
    "{p0} is using the number {number} and changes handsets often. The number has been in "
    "frequent contact with a number attributed to {p1} over the last month, mostly late at night "
    "and in short calls, which is consistent with arranging deliveries.",
    "It is reported that {p1} owes {p0} a sum in the region of {amount} following the loss of a "
    "consignment. {p0} has made threats towards {p1} and has told associates that the debt must "
    "be cleared by the end of the month.",
    "{org} is believed to be used by {p0} to launder the proceeds of {commodity} supply. Cash "
    "takings at {org} are reported to be far higher than the footfall would support.",
    "{p1} is described as a runner for {p0}. {p1} is young, has no fixed address and is thought "
    "to stay at {place} most nights. Concerns are noted about exploitation.",
    "The source of this report has provided reliable information in the past. The information "
    "was obtained first hand. Handling and dissemination restrictions apply; consult the "
    "originator before any action is taken on it.",
    "A search of {place} on {date} found {commodity}, a set of digital scales and a notebook "
    "listing first names and sums of money. {p0} was not present at the time of the search.",
    "{p0} (born {dob0}) has recently been seen with an expensive watch and new clothing, and "
    "has told others that business is going well. {p0} has no declared employment.",
    "There is a link between {p0} and {org}: {p0} has been seen collecting envelopes from the "
    "premises on {weekday}s, usually just before closing time.",
    "{p2} is said to be a new associate of {p0}, introduced by {p1}. Little is known about {p2} "
    "beyond a first name and the fact that {p2} drives {vehicle}.",
    "Assessment: the picture is consistent with an established local supply line run by {p0}, "
    "with {p1} in a trusted role. Further development is recommended before any overt action.",
)
_STATEMENT = (
    "This statement, consisting of several pages each signed by me, is true to the best of my "
    "knowledge and belief, and I make it knowing that, if it is tendered in evidence, I shall be "
    "liable to prosecution if I have wilfully stated in it anything which I know to be false.",
    "I live at {place} and have done so for about six years. I know the area well and I know "
    "most of my neighbours by sight. I am making this statement about what I saw on {weekday} "
    "{date}.",
    "At about {time} I was looking out of my front window when I saw {vehicle} pull up across "
    "the road. Two men got out. I now know one of them to be {p0}. I had seen him around before "
    'and people call him "{nick0}".',
    "The other man was taller, wearing a dark hooded top and grey tracksuit bottoms. I did not "
    "recognise him at the time, but I have since been told his name is {p1}. I would recognise "
    "him again if I saw him.",
    "{p0} went to the door of the house opposite and knocked loudly several times. When nobody "
    "answered he shouted something I could not make out and kicked the door. {p1} stayed by the "
    "car and kept looking up and down the street as if he was keeping watch.",
    "After a few minutes a woman came out of the house. I now know her to be {p2}. She was "
    "crying and saying \"I haven't got it, I told you I haven't got it\". {p0} grabbed her arm "
    "and pulled her towards the car.",
    "I was frightened and I did not go outside. I phoned the police on my mobile, which is "
    "{number}. I stayed on the phone while the call handler asked me questions about what I "
    "could see.",
    "{p1} then got back into the driver's seat. {p0} let go of {p2} and pointed at her and said "
    'something like "Friday, or you know what happens". Then he got into the passenger side and '
    "the car drove off quickly towards {town}.",
    "I did not see the whole registration of the car but I think it began with the letters YX. "
    "It was {vehicle} with a dent in the rear bumper and a sticker in the back window.",
    "Later that evening I spoke to {p2}. She told me that {p0} had lent her money some months "
    "ago and that the amount she owed kept going up. She said she was too scared to report it.",
    "On {date} I was shown a set of photographs by an officer. I picked out photograph number "
    "four as the man I saw kicking the door. I was sure about it because of his walk and his "
    "face.",
    "I have been asked whether I know anyone connected with {org}. I know that {p1} used to work "
    "there, washing cars, but I do not know if he still does.",
    "Case note ({rank} {staff}): spoke to the witness by telephone on {date}. The witness "
    "confirmed the account given above and is willing to attend court. Special measures are to "
    "be considered given the witness's fear of reprisals.",
    "Case note ({rank} {staff}): enquiries at {place} found the occupant, {p2}, unwilling to "
    "provide a statement at this time. Safeguarding referral made. Further visit planned.",
    "Case note ({rank} {staff}): the vehicle described is believed to be linked to {p1}. "
    "Checks are being made with the registered keeper. CCTV requested from premises on the "
    "route towards {town}.",
    "I have nothing further to add at this time. I am willing to attend court if required. I "
    "can be contacted on {number} or at {email}.",
    "I want to add that, a week before this happened, I saw {p0} and {p1} together outside "
    "{place}. They were sitting in {vehicle} with the engine running for over an hour.",
    "Case note ({rank} {staff}): telephone billing for {number} has been requested. The "
    "suspect's own number is believed to be held under another name.",
)
_SAR = (
    "The reporting institution has concerns about the conduct of the account {account} held "
    "by {p0} (date of birth {dob0}). Since {date} the account has received a high volume of "
    "cash deposits, each just under the institution's reporting threshold.",
    "Deposits are typically made at different branches on the same day, followed within hours "
    "by transfers out to accounts held with other institutions. The total received over the "
    "period is approximately {amount}.",
    "The customer described their occupation as self-employed, working in the {trade} trade. "
    "The activity seen is not consistent with the stated occupation or with the expected "
    "turnover declared when the account was opened.",
    'Several transfers have been made to {org}, with references such as "invoice" or '
    '"materials". No invoices were provided when the customer was asked to explain them.',
    "When contacted by telephone on {number}, the customer became evasive and ended the call. "
    "A second account holder, {p1}, has since been added to the account.",
    "The institution notes that {p1} is linked to another account that was closed in the past "
    "year following similar concerns. Adverse media has been found relating to {org}.",
    "The reporting institution requests consent to continue to operate the account while the "
    "matter is considered. No further transactions have been permitted above {amount}.",
    "Funds were also received from a number of individuals with no apparent connection to "
    '{p0}, in round sums, with references such as "rent" and "loan".',
)
_CHIS = (
    'Source reports that {p0} ("{nick0}") is a senior figure in {org}, which controls '
    "the supply of {commodity} around {town}. {p0} rarely handles product himself.",
    "Source reports that {p1} acts as {p0}'s driver and is trusted to collect money. {p1} "
    "drives {vehicle} and is often seen near {place}.",
    "Source states that {org} is currently in dispute with a rival group over territory near "
    "{place}. Source believes there is a risk of violence in the coming weeks.",
    "Source reports that {p0} has started using a new phone and that only a small number of "
    "people have the number. Source was not able to obtain it.",
    "Source reports that a meeting is planned for {weekday} at {place}, attended by {p0}, {p1} "
    "and {p2}. The purpose is said to be to agree prices for the next consignment.",
    "Source grading {grade}. The source has access to the group through a family connection and "
    "is considered reliable. This report must not be disseminated without the handler's consent.",
    "Source reports that {p2} has recently been recruited by {org} and is being used to hold "
    "cash at an address in {town}.",
    "Source says that {p0} keeps records of debts in a notebook carried at all times, and that "
    "{p1} has been told to collect a debt of {amount} from a customer.",
)
_TEMPLATES = {"intel": _INTEL, "statement": _STATEMENT, "sar": _SAR, "chis": _CHIS}

_TITLES = {
    "intel": "Intelligence report: {p0}, {town}, {date}",
    "statement": "Witness statement re incident at {place}, {date}",
    "sar": "SAR: account activity, {p0}, {date}",
    "chis": "Source report: {org}, {date}",
}

_TOWN_STEMS = (
    "Eastfield",
    "Westbrook",
    "Northgate",
    "Southmoor",
    "Lowerford",
    "Kingshaven",
    "Marketdale",
    "Oldwood",
    "Newmere",
    "Upperholme",
)
_TRADES = ("building", "car repair", "catering", "cleaning", "haulage", "retail")


def _fill(
    r: random.Random, cast: Sequence[Mention], extras: dict[str, list[str]], when: datetime
) -> dict[str, str]:
    names = [m.name for m in cast] or ["an unknown male"]
    while len(names) < 3:
        names.append(r.choice(("an unknown male", "an unknown female", "a third party")))
    day = (when - timedelta(days=r.randrange(0, 40))).date()
    first = cast[0] if cast else Mention("an unknown male", "unknown", date(1990, 1, 1))
    number = (extras.get("numbers") or [f"07700 {r.randrange(10_000, 899_999):06d}"])[0]
    account = (extras.get("accounts") or ["an account held elsewhere"])[0]
    return {
        "p0": names[0],
        "p1": names[1],
        "p2": names[2],
        "nick0": first.nickname,
        "dob0": first.date_of_birth.strftime("%d/%m/%Y"),
        "place": (extras.get("places") or [f"an address on {r.choice(_TOWN_STEMS)} Road"])[0],
        "org": (extras.get("orgs") or [f"{r.choice(_TOWN_STEMS)} Hand Car Wash"])[0],
        "number": number,
        "account": account,
        "town": r.choice(_TOWN_STEMS),
        "date": day.strftime("%d %B %Y"),
        "weekday": _WEEKDAYS[day.weekday()],
        "time": f"{r.randrange(0, 24):02d}:{r.choice(('00', '15', '20', '30', '45', '50'))}",
        "vehicle": r.choice(_VEHICLES),
        "commodity": r.choice(_COMMODITIES),
        "amount": f"£{r.randrange(2, 400) * 250:,}",
        "rank": r.choice(_RANKS),
        "staff": r.choice(_STAFF),
        "grade": r.choice(_GRADES),
        "trade": r.choice(_TRADES),
        "email": f"{names[0].split()[0].lower()}.{r.randrange(100, 999)}@example.org"
        if cast
        else f"witness.{r.randrange(100, 999)}@example.net",
    }


def compose(
    kind: str,
    r: random.Random,
    cast: Sequence[Mention],
    extras: dict[str, list[str]],
    when: datetime,
) -> str:
    """A document's full text: paragraphs drawn from its kind's templates, in a stable order
    after the first, which opens every document of that kind."""
    mean, spread = KINDS[kind]
    templates = _TEMPLATES[kind]
    count = max(2, mean + r.randint(-spread, spread))
    values = _fill(r, cast, extras, when)
    chosen = [templates[0]] + [
        templates[1 + r.randrange(len(templates) - 1)] for _ in range(count - 1)
    ]
    return "\n\n".join(t.format(**values) for t in chosen)


def title(
    kind: str,
    r: random.Random,
    cast: Sequence[Mention],
    extras: dict[str, list[str]],
    when: datetime,
) -> str:
    values = _fill(r, cast, extras, when)
    values["date"] = when.strftime("%d %b %Y")
    return _TITLES[kind].format(**values)
