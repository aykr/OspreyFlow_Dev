"""Synthetic SMS fixture (ADR-094 step 1): messages with text between four phones, so a phone link
can be read and extracted from as an Enron email link can. Every name, number, place and date here
is invented (rule 9); the numbers are in valid UK mobile ranges so the `msisdn` Knowledge Adapter
normalises them, and one of them is the CDR fixture's `B_PARTY`, so the two exports meet on one
`Endpoint` when both are loaded into a case.

Deterministic: a fixed list, no random component, so a test can name a message by its text.
"""

from __future__ import annotations

from .cdr import B_PARTY

PHONES = {
    "dana": B_PARTY,  # 07911123456, shared with the CDR fixture
    "callum": "07912345678",
    "priya": "07913456789",
    "tomasz": "07914567890",
}

#: (sender, recipient, ISO instant, text). Text names people, places, dates and numbers, which is
#: what extraction looks for.
_MESSAGES = (
    (
        "dana",
        "callum",
        "2026-01-12T08:14:00Z",
        "Callum, the van is booked for Friday. Pick it up from Unit 4, Marsh Lane, Purfleet.",
    ),
    (
        "callum",
        "dana",
        "2026-01-12T08:20:00Z",
        "Got it. Is Priya Nair still meeting us at Tilbury dock?",
    ),
    (
        "dana",
        "priya",
        "2026-01-12T09:02:00Z",
        "Priya, Friday 16 January at 6am, Tilbury. Bring the paperwork for the Harlow shipment.",
    ),
    (
        "priya",
        "dana",
        "2026-01-12T09:40:00Z",
        "Fine. Tomasz Wolski will drive. His number is 07914567890.",
    ),
    (
        "tomasz",
        "priya",
        "2026-01-13T19:05:00Z",
        "Car is a grey Ford Transit, reg AB12 CDE. I can be there by 5:30.",
    ),
    (
        "priya",
        "tomasz",
        "2026-01-13T19:12:00Z",
        "Good. Park behind the Riverside Cafe, Dock Road. Don't call Dana on the old number.",
    ),
    (
        "callum",
        "tomasz",
        "2026-01-14T07:30:00Z",
        "Tomasz, it's Callum Price. Dana says the payment of £4,500 goes to the Barclays "
        "account ending 1192.",
    ),
    (
        "tomasz",
        "callum",
        "2026-01-14T07:45:00Z",
        "Understood. I'll send the receipt to callum.price@example.com.",
    ),
    (
        "dana",
        "callum",
        "2026-01-15T21:10:00Z",
        "Change of plan. Meet at the Harlow industrial estate instead, gate 3, 7am Friday.",
    ),
    ("callum", "dana", "2026-01-15T21:15:00Z", "OK. Telling Priya and Tomasz now."),
    ("priya", "callum", "2026-01-16T06:50:00Z", "At gate 3. No sign of the Transit yet."),
    (
        "tomasz",
        "dana",
        "2026-01-16T07:05:00Z",
        "Five minutes away, traffic on the M11 at junction 7.",
    ),
)

FIELDS = ("message_id", "sender", "recipient", "sent_at", "text")


def generate_sms_rows() -> list[dict[str, str]]:
    """One row per message, as a carrier's SMS export might list it."""
    return [
        {
            "message_id": f"SMS-{index:04d}",
            "sender": PHONES[sender],
            "recipient": PHONES[recipient],
            "sent_at": sent_at,
            "text": text,
        }
        for index, (sender, recipient, sent_at, text) in enumerate(_MESSAGES, start=1)
    ]
