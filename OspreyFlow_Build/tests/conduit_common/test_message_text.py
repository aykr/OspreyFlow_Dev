"""The one reader of a message body (ADR-095 decision 5): every email source decodes through it.

Found on the Enron case: bodies were read with `get_payload(decode=False)`, so quoted-printable
stayed encoded and its soft line breaks split words (a name split by `=` and a line break), which extraction must find
verbatim. What a mistake would do, and the case that catches it, below. The messages are made up
here (rule 9), in the shapes real mail takes: the first is the Enron message's own header shape.
"""

from __future__ import annotations

from email import message_from_bytes

from conduit_common.message_text import body_text


def _parse(raw: str) -> object:
    return message_from_bytes(raw.encode("latin-1"))


def test_quoted_printable_is_decoded_and_its_soft_breaks_joined() -> None:
    message = _parse(
        "Subject: FW: Daily Update\n"
        "Mime-Version: 1.0\n"
        "Content-Type: text/plain; charset=us-ascii\n"
        "Content-Transfer-Encoding: quoted-printable\n\n"
        "having the Board of Directors and Dan Le=\ne personally reinvest.=20\n"
        "Come to Portland.=0AThanks\n"
    )
    text = body_text(message)  # type: ignore[arg-type]
    assert "Dan Lee personally" in text
    assert "=20" not in text and "Le=" not in text
    assert "Portland." in text


def test_base64_in_a_declared_character_set_is_decoded() -> None:
    import base64

    body = base64.b64encode("Réunion à Genève avec Zoë".encode("iso-8859-1")).decode()
    message = _parse(
        "Content-Type: text/plain; charset=iso-8859-1\n"
        f"Content-Transfer-Encoding: base64\n\n{body}\n"
    )
    assert body_text(message) == "Réunion à Genève avec Zoë"  # type: ignore[arg-type]


def test_a_multipart_message_gives_its_plain_text_part_and_not_its_attachment() -> None:
    message = _parse(
        'Content-Type: multipart/mixed; boundary="b1"\n\n'
        "--b1\nContent-Type: text/plain; charset=utf-8\n\nThe van is at Unit 4.\n"
        '--b1\nContent-Type: text/plain\nContent-Disposition: attachment; filename="a.txt"\n\n'
        "attached notes\n--b1--\n"
    )
    text = body_text(message)  # type: ignore[arg-type]
    assert "The van is at Unit 4." in text and "attached notes" not in text


def test_an_html_only_body_is_read_as_its_text() -> None:
    message = _parse(
        "Content-Type: text/html; charset=utf-8\n\n"
        "<html><body><p>Meet <b>Callum</b> at Purfleet</p><script>x()</script></body></html>\n"
    )
    text = body_text(message)  # type: ignore[arg-type]
    assert "Meet Callum at Purfleet" in " ".join(text.split())
    assert "<b>" not in text and "x()" not in text


def test_a_plain_seven_bit_body_is_unchanged() -> None:
    message = _parse("Content-Type: text/plain\n\nNothing to decode = here.\n")
    assert body_text(message).strip() == "Nothing to decode = here."  # type: ignore[arg-type]
