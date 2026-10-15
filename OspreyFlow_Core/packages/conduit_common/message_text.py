"""The one reader of a message body — `06_DECISIONS.md` ADR-095 decision 5.

Every source that reads email reads its body here, so a fix to decoding is a fix everywhere and no
loader keeps its own half-decoded copy (the Enron loader read bodies with
`get_payload(decode=False)`, leaving quoted-printable encoded and its soft line breaks splitting
words, a name broken by `=` and a line break, that extraction must find verbatim).

`body_text` gives the text a person reads: the transfer encoding undone (quoted-printable, base64),
the declared character set applied (an unknown one read as UTF-8, never refused), and for a
multipart message its first plain-text part that is not an attachment, or failing that its HTML
part read as text. Nothing is cut: a caller that must bound what it stores says so itself (rule 2).
"""

from __future__ import annotations

from email.message import Message
from html.parser import HTMLParser


class _Text(HTMLParser):
    """The visible text of an HTML body: no tags, no scripts or styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "br", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _is_attachment(part: Message) -> bool:
    return (part.get("Content-Disposition") or "").strip().lower().startswith("attachment")


def _decoded(part: Message) -> str:
    raw = part.get_payload(decode=True)
    if not isinstance(raw, bytes):
        payload = part.get_payload()
        return payload if isinstance(payload, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _html_text(html: str) -> str:
    reader = _Text()
    reader.feed(html)
    reader.close()
    return "".join(reader.parts)


def body_text(message: Message) -> str:
    """The body of `message` as a person reads it, decoded and whole."""
    parts = [p for p in message.walk() if not p.is_multipart() and not _is_attachment(p)]
    for part in parts:
        if part.get_content_type() == "text/plain":
            return _decoded(part)
    for part in parts:
        if part.get_content_type() == "text/html":
            return _html_text(_decoded(part))
    return ""
