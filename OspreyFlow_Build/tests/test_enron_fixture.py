"""Reading the Enron mail corpus for a demo (ADR-053 Amendment 1).

The tests build a small mailbox tree of *invented* messages in the corpus's layout
(`<custodian>/<folder>/<file>`), so nothing real is needed here or committed. Each test names the
fault it would catch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from internal_demos import enron
from schemas.domain import Handling

HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="enron-demo", owning_unit="enron-demo"
)


def _mail(
    *,
    message_id: str = "<1.a@thyme>",
    date: str | None = "Mon, 14 May 2001 16:39:00 -0700 (PDT)",
    sender: str = "Alice.Smith@Enron.com",
    to: str = "bob@enron.com",
    cc: str = "",
    bcc: str = "",
    subject: str = "Hello",
    body: str = "Body text.",
) -> str:
    lines = [f"Message-ID: {message_id}"]
    if date is not None:
        lines.append(f"Date: {date}")
    lines += [f"From: {sender}", f"To: {to}"]
    if cc:
        lines.append(f"Cc: {cc}")
    if bcc:
        lines.append(f"Bcc: {bcc}")
    lines += [f"Subject: {subject}", "", body]
    return "\n".join(lines)


def _message_with_body(root: Path, name: str, body: str) -> enron.Message:
    _put(root, "smith-a", "sent", name, _mail(message_id=f"<{name}@thyme>", body=body))
    return next(m for m in enron.read_messages(root) if m.message_id == f"<{name}@thyme>")


def _put(root: Path, custodian: str, folder: str, name: str, text: str) -> None:
    path = root / custodian / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_message_becomes_one_record_with_utc_time_and_lowercased_addresses(
    tmp_path: Path,
) -> None:
    """Catches local-time dates (the corpus mixes -0700 and -0800) and case-split addresses."""
    _put(tmp_path, "smith-a", "sent", "1.", _mail())
    (m,) = list(enron.read_messages(tmp_path))
    assert m.sent_at == datetime(2001, 5, 14, 23, 39, tzinfo=UTC)
    assert m.sender == "alice.smith@enron.com"
    assert [r.address for r in m.recipients] == ["bob@enron.com"]
    assert (m.custodian, m.folder, m.subject) == ("smith-a", "sent", "Hello")


def test_to_cc_and_bcc_are_all_recipients_and_keep_their_kind(tmp_path: Path) -> None:
    """Catches a reader that forgets Cc or Bcc, which hides who really saw a message."""
    _put(
        tmp_path,
        "smith-a",
        "sent",
        "1.",
        _mail(to="bob@enron.com, Carol <carol@enron.com>", cc="dan@x.org", bcc="eve@enron.com"),
    )
    (m,) = list(enron.read_messages(tmp_path))
    assert [(r.address, r.kind) for r in m.recipients] == [
        ("bob@enron.com", "to"),
        ("carol@enron.com", "to"),
        ("dan@x.org", "cc"),
        ("eve@enron.com", "bcc"),
    ]


def test_the_same_message_in_several_folders_is_read_once(tmp_path: Path) -> None:
    """Catches the corpus's own duplication (all_documents, sent_items and so on): without
    deduplication one email would count three times in every total."""
    for folder in ("sent", "all_documents", "discussion_threads/1"):
        _put(tmp_path, "smith-a", folder, "9.", _mail(message_id="<same@thyme>"))
    tally = enron.Tally()
    assert len(list(enron.read_messages(tmp_path, tally=tally))) == 1
    assert tally.duplicates == 2


def test_copies_of_one_email_under_different_message_ids_are_read_once(tmp_path: Path) -> None:
    """The real corpus, as the owner saw it: one email shown three times. The corpus gives every
    file its own Message-ID, so the copies of one email in `discussion_threads`, `general_stuff`
    and `all_documents` (or in two custodians' mailboxes) carry three different ids. The test
    above gave its copies one id, a corpus that does not exist, and so could not fail for this."""
    copies = [
        ("mann-k", "discussion_threads"),
        ("mann-k", "general_stuff"),
        ("mann-k", "all_documents"),
    ]
    for n, (custodian, folder) in enumerate(copies):
        _put(tmp_path, custodian, folder, f"{n}.", _mail(message_id=f"<{n}.1075845@thyme>"))
    _put(tmp_path, "brown-s", "sent", "1.", _mail(message_id="<9.1075999@thyme>"))
    tally = enron.Tally()
    assert len(list(enron.read_messages(tmp_path, tally=tally))) == 1
    assert tally.duplicates == 3


def test_two_different_messages_are_both_kept(tmp_path: Path) -> None:
    """Catches a dedupe that is too greedy (for example keyed on subject): the same subject from
    the same sender, at the same time, with a different body, is a different email."""
    _put(tmp_path, "a", "sent", "1.", _mail(message_id="<1@t>", subject="Same", body="One."))
    _put(tmp_path, "a", "sent", "2.", _mail(message_id="<2@t>", subject="Same", body="Two."))
    _put(
        tmp_path, "a", "sent", "3.", _mail(message_id="<3@t>", subject="Same", to="carol@enron.com")
    )
    assert len(list(enron.read_messages(tmp_path))) == 3


def test_a_message_without_an_id_is_still_deduplicated_by_its_content(tmp_path: Path) -> None:
    """Catches losing the dedupe when a header is absent."""
    text = _mail().replace("Message-ID: <1.a@thyme>\n", "")
    _put(tmp_path, "a", "sent", "1.", text)
    _put(tmp_path, "b", "inbox", "7.", text)
    assert len(list(enron.read_messages(tmp_path))) == 1


def test_an_undated_or_senderless_message_is_counted_not_guessed(tmp_path: Path) -> None:
    """Catches inventing a date (which would put the message in the wrong place on the timeline)."""
    _put(tmp_path, "a", "sent", "1.", _mail(message_id="<1@t>", date=None))
    _put(tmp_path, "a", "sent", "2.", _mail(message_id="<2@t>", date="not a date"))
    _put(tmp_path, "a", "sent", "3.", _mail(message_id="<3@t>", sender=""))
    _put(tmp_path, "a", "sent", "4.", _mail(message_id="<4@t>"))
    tally = enron.Tally()
    assert [m.message_id for m in enron.read_messages(tmp_path, tally=tally)] == ["<4@t>"]
    assert (tally.undated, tally.senderless) == (2, 1)


def test_a_message_to_nobody_readable_is_counted(tmp_path: Path) -> None:
    """Catches a message with only 'undisclosed-recipients:' yielding an event with no target."""
    _put(tmp_path, "a", "sent", "1.", _mail(to="undisclosed-recipients:;"))
    tally = enron.Tally()
    assert list(enron.read_messages(tmp_path, tally=tally)) == []
    assert tally.no_recipients == 1


def test_sending_to_yourself_is_not_a_link(tmp_path: Path) -> None:
    """Catches self-loops in the graph."""
    _put(tmp_path, "a", "sent", "1.", _mail(to="alice.smith@enron.com, bob@enron.com"))
    (m,) = list(enron.read_messages(tmp_path))
    assert [r.address for r in m.recipients] == ["bob@enron.com"]


def test_a_file_that_is_not_mail_is_counted_and_skipped(tmp_path: Path) -> None:
    """Catches one bad file stopping a half-million-message load."""
    _put(tmp_path, "a", "sent", "1.", "\x00\x01 not a mail at all")
    _put(tmp_path, "a", "sent", "2.", _mail(message_id="<2@t>"))
    tally = enron.Tally()
    assert len(list(enron.read_messages(tmp_path, tally=tally))) == 1
    assert tally.unreadable + tally.undated + tally.senderless >= 1


def test_the_excerpt_is_the_whole_body_however_long(tmp_path: Path) -> None:
    """ADR-095 decision 3 (replacing ADR-089's 4,000-character cut): the reader shows and
    extraction reads the whole email."""
    short = _message_with_body(tmp_path, "short.eml", "A short note.  With  spacing.")
    assert short.excerpt == "A short note. With spacing."
    assert short.truncated is False
    long = _message_with_body(tmp_path, "long.eml", "word " * 2000)
    assert len(long.excerpt) == len(("word " * 2000).strip())
    assert long.truncated is False


def test_a_quoted_printable_body_is_decoded(tmp_path: Path) -> None:
    """ADR-095 context 2: the owner's email showed `=20` and `Ken La= y`, because the body was
    never decoded. The header shape is that email's own."""
    body = "the Board and Ken La=\ny personally reinvest.=20 Portland."
    raw = _mail(message_id="<qp@thyme>", body=body)
    raw = raw.replace(
        "Subject: Hello",
        "Subject: Hello\nMime-Version: 1.0\nContent-Type: text/plain; charset=us-ascii\n"
        "Content-Transfer-Encoding: quoted-printable",
    )
    _put(tmp_path, "smith-a", "sent", "qp.", raw)
    (message,) = list(enron.read_messages(tmp_path))
    assert "Ken Lay personally reinvest. Portland." in message.excerpt
    assert "=20" not in message.excerpt


def test_the_read_order_is_the_same_every_time(tmp_path: Path) -> None:
    """Catches a dedupe whose winner depends on directory order: the two passes must agree."""
    for custodian in ("z-last", "a-first"):
        _put(tmp_path, custodian, "sent", "1.", _mail(message_id="<same@t>"))
    first = [m.custodian for m in enron.read_messages(tmp_path)]
    assert first == ["a-first"] == [m.custodian for m in enron.read_messages(tmp_path)]


def test_identifiers_are_stable_and_direction_matters() -> None:
    """Catches identifiers that change between loads, or a pair that ignores who wrote to whom."""
    a, b = "a@enron.com", "b@enron.com"
    assert enron.endpoint_node_id(a) == enron.endpoint_node_id("A@Enron.com".lower())
    assert enron.pair_edge_id(a, b) == enron.pair_edge_id(a, b)
    assert enron.pair_edge_id(a, b) != enron.pair_edge_id(b, a)


def test_an_event_per_recipient_ties_to_the_pair_edge(tmp_path: Path) -> None:
    """Catches events that do not find their summarised edge, or lose the subject and folder."""
    _put(tmp_path, "smith-a", "sent", "1.", _mail(to="bob@enron.com", cc="carol@enron.com"))
    (m,) = list(enron.read_messages(tmp_path))
    events = list(enron.to_events(m, investigation_scope="case-1", handling=HANDLING))
    assert len(events) == 2
    first = events[0]
    assert first.edge_type == "COMMUNICATED_WITH"
    assert first.edge_id == enron.pair_edge_id("alice.smith@enron.com", "bob@enron.com")
    assert first.source_id == enron.endpoint_node_id("alice.smith@enron.com")
    assert first.target_id == enron.endpoint_node_id("bob@enron.com")
    assert first.direction == "outbound"
    assert first.investigation_scope == "case-1"
    assert first.properties["subject"] == "Hello"
    assert first.properties["custodian"] == "smith-a"
    assert first.properties["kind"] == "to" and events[1].properties["kind"] == "cc"
    assert len({e.event_id for e in events}) == 2


def test_the_graph_holds_enron_addresses_and_links_between_them_only(tmp_path: Path) -> None:
    """Catches an outside address (a newsletter, a personal account) becoming a node: the graph
    is the company's own network, while every message still lands in the events."""
    _put(tmp_path, "a", "sent", "1.", _mail(message_id="<1@t>", to="bob@enron.com, spam@x.org"))
    _put(tmp_path, "a", "sent", "2.", _mail(message_id="<2@t>", to="bob@enron.com"))
    pairs = enron.summarise(enron.read_messages(tmp_path))
    nodes, edges = enron.build_graph_writes(pairs, created_by="seed", handling=HANDLING)
    assert sorted(n.properties["value_normalised"] for n in nodes) == [
        "alice.smith@enron.com",
        "bob@enron.com",
    ]
    (edge,) = edges
    assert edge.type == "COMMUNICATED_WITH"
    assert edge.interval.valid_from <= edge.interval.valid_to  # type: ignore[operator]
    assert {n.properties["endpoint_kind"] for n in nodes} == {"email"}


def test_an_edge_summarises_every_message_between_the_pair(tmp_path: Path) -> None:
    """Catches one edge per message (a hairball) or a count that misses duplicates."""
    for i in range(3):  # three different emails, not three copies of one
        _put(tmp_path, "a", "sent", f"{i}.", _mail(message_id=f"<{i}@t>", body=f"Message {i}."))
    pairs = enron.summarise(enron.read_messages(tmp_path))
    ((_, summary),) = pairs.items()
    assert summary.count == 3



def test_the_link_written_carries_the_pairs_message_count(tmp_path: Path) -> None:
    """`Edge.occurrences` is how many records a link stands for (01 §3): for Enron, the messages
    between the pair. Found ranking the busiest links (ADR-100 decision 5): every Enron link said 1,
    since the count was summarised and never written, so the busiest pair read as the quietest and
    the links' weights (§6) were computed from 1s."""
    for i in range(3):
        _put(tmp_path, "a", "sent", f"{i}.", _mail(message_id=f"<{i}@t>", body=f"Message {i}."))
    pairs = enron.summarise(enron.read_messages(tmp_path))
    _, edges = enron.build_graph_writes(pairs, created_by="seed", handling=HANDLING)
    (edge,) = edges
    assert edge.occurrences == 3


def test_a_folder_that_is_not_the_corpus_is_refused(tmp_path: Path) -> None:
    """Catches pointing the loader at the wrong folder and 'succeeding' with nothing."""
    with pytest.raises(enron.EnronFolderError):
        list(enron.read_messages(tmp_path))
