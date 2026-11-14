"""What Ask & Chat reads, and who will answer (`06_DECISIONS.md` ADR-098 Amendment 7, ADR-129
Amendment 4, ADR-135 Amendment 12).

- **`ReadSummary`**: what a question read, or will read, counted by the Conduit as the asker.
- **`UnusableEngine`**: an engine that cannot answer this question, and why, in words.
- **`WillRead`**: `POST /v1/investigations/{id}/questions/will-read`, the summary and the engine the
  routing will use on the question's own material, before anything is sent.

The Glass reads these as generated (`generated/`), and never counts what was read itself.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReadSummary(BaseModel):
    """What a question read, or will read (ADR-098 Amendment 7), counted as the asker from their own
    view: nothing they may not see moves a figure (rule 3). Kept with the answer, which a later
    reader is shown only if they may see every node, link and Document counted."""

    read_from: Literal["selection", "graph"]
    #: Documents in scope with text, every one read whole.
    documents: int
    #: Documents in scope with no text to read (an image, say): counted, never read.
    documents_without_text: int
    #: The other items in scope (every node that is not a Document).
    items: int
    links: int
    #: The events counted per month on the links in scope.
    events: int
    #: How many of the selected nodes and links the asker's view holds; 0 for *Everything on the
    #: graph*. A selected id they may not see is not counted, as one that does not exist is not.
    selected: int
    #: The first selected node's display name, for "About: <name> and N others".
    first_selected: str | None


class UnusableEngine(BaseModel):
    """An engine the deployment has that cannot answer this question, and why, in words."""

    name: str
    label: str
    reason: str


class WillRead(BaseModel):
    """`POST …/questions/will-read`, every field always sent: what the question would read, and the
    engine that would answer it as the routing decides (ADR-135 Amendment 12), before anything is
    sent."""

    read: ReadSummary
    #: The engine and model that will answer; `None` when no engine may (`refused` says why).
    engine: str | None
    engine_label: str | None
    model: str | None
    #: The engines that exist but cannot answer this question, each with its reason.
    unusable: list[UnusableEngine]
    refused: str | None


ALL_MODELS: tuple[type[BaseModel], ...] = (ReadSummary, UnusableEngine, WillRead)
