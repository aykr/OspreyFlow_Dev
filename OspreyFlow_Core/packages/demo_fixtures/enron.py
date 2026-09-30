"""The Enron mail corpus, read for an owner-run demo on the owner's own machine (ADR-053 and its
Amendment 1).

**This is real data.** It is admitted only through `config/real_data_exceptions.yaml`, is never
committed, and is never read by anything that ships. This module is pure: it reads and shapes
records, and holds no path to any corpus. Writing them is `scripts/seed_enron.py`, which refuses
first unless the exceptions entry, the provisioned folder and a checkout are all there.

**Shape (the owner chose "option A", 30 September 2026).** An email address is an `Endpoint` of kind
`email`; a person is not invented from an address. Each sender-to-recipient pair is one summarised
`COMMUNICATED_WITH` edge, and every message to a recipient is one analytics event on that edge, so
counts, time windows and subjects come from the events, as ADR-055 does for PaySim. The graph takes
the company's own addresses (`@enron.com`) and the links between them; every message, including
those to and from outside addresses, is in the analytics store. No ontology change is needed.

**The corpus holds the same email many times**: one email is commonly in `sent`,
`all_documents` and `discussion_threads` of the same custodian, and in a recipient's `inbox`. A
message is read once, by `Message-ID` (or by a hash of its headers and body when it has none), in a
fixed order, so two passes over the folder agree.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email import message_from_binary_file
from email.message import Message as EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from schemas.analytics import EventRecord
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    NodeWrite,
    Provenance,
    ProvenanceState,
    SourceRef,
)

#: How much of a message body rides on its event. The whole corpus is over a gigabyte of text.
EXCERPT_CHARS = 300
#: The company's own addresses are the graph; everything else is events only.
GRAPH_DOMAIN = "@enron.com"

_NAMESPACE = uuid.UUID("6f0a5c1e-6b0e-4e2a-9d0a-50a15a1e0053")


class EnronFolderError(ValueError):
    """The folder is not a corpus of mailboxes this loader reads."""


@dataclass
class Tally:
    """What was skipped, and why. A loader that skips silently reports a false total."""

    files: int = 0
    kept: int = 0
    duplicates: int = 0
    unreadable: int = 0
    undated: int = 0
    senderless: int = 0
    no_recipients: int = 0

    def lines(self) -> list[str]:
        return [
            f"{self.files:,} files read; {self.kept:,} distinct messages kept",
            f"skipped: {self.duplicates:,} duplicates, {self.unreadable:,} unreadable, "
            f"{self.undated:,} undated, {self.senderless:,} without a sender, "
            f"{self.no_recipients:,} without a readable recipient",
        ]


@dataclass(frozen=True)
class Recipient:
    address: str
    kind: str  # "to", "cc" or "bcc"


@dataclass(frozen=True)
class Message:
    message_id: str
    custodian: str
    folder: str
    sent_at: datetime
    sender: str
    recipients: tuple[Recipient, ...]
    subject: str
    excerpt: str


@dataclass
class PairSummary:
    count: int
    first: datetime
    last: datetime


def _addresses(header: object) -> list[str]:
    found: list[str] = []
    for _name, address in getaddresses([str(header)]) if header else []:
        clean = address.strip().strip("'\"<>").lower()
        if "@" in clean and clean not in found:
            found.append(clean)
    return found


def _excerpt(message: EmailMessage) -> str:
    payload = message.get_payload(decode=False)
    text = payload if isinstance(payload, str) else ""
    return " ".join(text.split())[:EXCERPT_CHARS]


def _content_key(message: EmailMessage) -> str:
    material = "\x1f".join(
        str(message.get(h, "")) for h in ("Date", "From", "To", "Cc", "Subject")
    ) + str(message.get_payload(decode=False))
    return "hash:" + hashlib.sha1(material.encode("utf-8", "replace")).hexdigest()  # noqa: S324


def _files(root: Path) -> Iterator[Path]:
    """Every file, in a fixed order, so the first copy of a duplicate is always the same one."""
    for directory, subdirectories, names in os.walk(root):
        subdirectories.sort()
        for name in sorted(names):
            yield Path(directory) / name


def read_messages(root: Path, *, tally: Tally | None = None) -> Iterator[Message]:
    """Each distinct message once. Layout is `<custodian>/<folder...>/<file>`; a file directly under
    `root` is not a mailbox and is ignored. A folder with no mailbox at all is refused."""
    tally = tally if tally is not None else Tally()
    if not root.is_dir() or not any(child.is_dir() for child in root.iterdir()):
        raise EnronFolderError(
            f"{root} holds no mailboxes; expected one folder per custodian, each with its mail."
        )
    seen: set[str] = set()
    for path in _files(root):
        relative = path.relative_to(root).parts
        if len(relative) < 3:
            continue
        tally.files += 1
        try:
            with path.open("rb") as handle:
                message = message_from_binary_file(handle)
        except (OSError, ValueError):
            tally.unreadable += 1
            continue
        sender = next(iter(_addresses(message.get("From"))), "")
        if not sender:
            tally.senderless += 1
            continue
        try:
            sent_at = parsedate_to_datetime(str(message.get("Date", "")))
        except (TypeError, ValueError, IndexError):
            tally.undated += 1
            continue
        if sent_at is None:
            tally.undated += 1
            continue
        sent_at = sent_at.replace(tzinfo=UTC) if sent_at.tzinfo is None else sent_at.astimezone(UTC)
        message_id = str(message.get("Message-ID", "")).strip() or _content_key(message)
        if message_id in seen:
            tally.duplicates += 1
            continue
        recipients: list[Recipient] = []
        for header, kind in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
            for address in _addresses(message.get(header)):
                if address != sender and all(r.address != address for r in recipients):
                    recipients.append(Recipient(address, kind))
        if not recipients:
            tally.no_recipients += 1
            continue
        seen.add(message_id)
        tally.kept += 1
        yield Message(
            message_id=message_id,
            custodian=relative[0],
            folder="/".join(relative[1:-1]).lower(),
            sent_at=sent_at,
            sender=sender,
            recipients=tuple(recipients),
            subject=" ".join(str(message.get("Subject", "")).split()),
            excerpt=_excerpt(message),
        )


def endpoint_node_id(address: str) -> str:
    return f"enron-ep-{uuid.uuid5(_NAMESPACE, address.lower()).hex}"


def pair_edge_id(sender: str, recipient: str) -> str:
    """One edge per *directed* pair: who wrote to whom matters."""
    return f"enron-comm-{uuid.uuid5(_NAMESPACE, f'{sender.lower()}>{recipient.lower()}').hex}"


def to_events(
    message: Message, *, investigation_scope: str, handling: Handling
) -> Iterator[EventRecord]:
    """One event per recipient, on the pair's summarised edge."""
    for recipient in message.recipients:
        key = f"{message.message_id}>{recipient.address}"
        yield EventRecord(
            event_id=f"enron-ev-{uuid.uuid5(_NAMESPACE, key).hex}",
            edge_id=pair_edge_id(message.sender, recipient.address),
            edge_type="COMMUNICATED_WITH",
            source_id=endpoint_node_id(message.sender),
            target_id=endpoint_node_id(recipient.address),
            occurred_at=message.sent_at,
            direction="outbound",
            properties={
                "subject": message.subject,
                "message_id": message.message_id,
                "custodian": message.custodian,
                "folder": message.folder,
                "kind": recipient.kind,
                "excerpt": message.excerpt,
            },
            investigation_scope=investigation_scope,
            handling=handling,
        )


def summarise(messages: Iterable[Message]) -> dict[tuple[str, str], PairSummary]:
    """Per directed pair, how many messages and over what span."""
    pairs: dict[tuple[str, str], PairSummary] = {}
    for message in messages:
        for recipient in message.recipients:
            key = (message.sender, recipient.address)
            found = pairs.get(key)
            if found is None:
                pairs[key] = PairSummary(1, message.sent_at, message.sent_at)
            else:
                found.count += 1
                found.first = min(found.first, message.sent_at)
                found.last = max(found.last, message.sent_at)
    return pairs


def _in_graph(address: str) -> bool:
    return address.endswith(GRAPH_DOMAIN)


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="enron-corpus", locator="mailboxes", excerpt_hash="enron")],
        first_seen=datetime.now(UTC),
    )


def build_graph_writes(
    pairs: dict[tuple[str, str], PairSummary], *, created_by: str, handling: Handling
) -> tuple[list[NodeWrite], list[EdgeWrite]]:
    """`Endpoint` (kind `email`) nodes for the company's addresses, and one `COMMUNICATED_WITH`
    edge per directed pair between two of them, spanning the pair's first to last message."""
    nodes: dict[str, NodeWrite] = {}
    edges: list[EdgeWrite] = []
    now = datetime.now(UTC)
    for (sender, recipient), summary in sorted(pairs.items()):
        if not (_in_graph(sender) and _in_graph(recipient)):
            continue
        for address in (sender, recipient):
            node_id = endpoint_node_id(address)
            if node_id not in nodes:
                nodes[node_id] = NodeWrite(
                    id=node_id,
                    type="Endpoint",
                    properties={
                        "value_raw": address,
                        "value_normalised": address,
                        "endpoint_kind": "email",
                    },
                    provenance=_provenance(),
                    handling=handling,
                    created_by=created_by,
                    created_at=now,
                )
        edges.append(
            EdgeWrite(
                id=pair_edge_id(sender, recipient),
                type="COMMUNICATED_WITH",
                source=endpoint_node_id(sender),
                target=endpoint_node_id(recipient),
                properties={"direction": "outbound"},
                interval=Interval(valid_from=summary.first, valid_to=summary.last),
                provenance=_provenance(),
                handling=handling,
                created_by=created_by,
                created_at=now,
            )
        )
    return list(nodes.values()), edges


__all__ = [
    "EXCERPT_CHARS",
    "EnronFolderError",
    "Message",
    "PairSummary",
    "Recipient",
    "Tally",
    "build_graph_writes",
    "endpoint_node_id",
    "pair_edge_id",
    "read_messages",
    "summarise",
    "to_events",
]
