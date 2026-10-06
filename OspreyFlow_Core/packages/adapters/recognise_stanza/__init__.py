"""`RecognisePort` over HTTP to the `ner` sidecar (ADR-098 decision 2)."""

from .adapter import RecogniserConfig, RecogniseStanzaAdapter

__all__ = ["RecogniseStanzaAdapter", "RecogniserConfig"]
