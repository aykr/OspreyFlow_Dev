"""Connectors as validated profiles — `docs/07_BUILD_PLAN.md` Phase 2,
following the map-provider pattern (ADR-016): adding a source shape is a
file, not a release. Only the generic CSV connector lands this phase; JSON
and other generic delimited formats follow the same
`Iterable[Mapping[str, str]]` row shape and are additive.
"""
