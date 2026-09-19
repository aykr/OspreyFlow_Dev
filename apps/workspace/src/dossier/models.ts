// Hand-written mirror of `services/api/dossier.py`'s wire contract — B6, Phase 6a Stage 4: "message
// content renders with the entity spans... highlighted in place" (`08_ACCEPTANCE_SCENARIOS.md`).
// The same manual-sync discipline `workingset/models.ts`'s own module docstring already accepts
// for the Conduit's control-plane envelope shapes, applied to this different backend module.
//
// `ProvenanceState`'s own three values, inlined rather than imported — it isn't re-exported from
// `packages/schemas/generated/index.ts` (`workingset/models.ts`'s own precedent for the same
// situation: an identifier the drift gate doesn't actually promise to keep exported).
export type MessageProvenanceState = "asserted" | "inferred" | "unresolved";

export interface MessageSpan {
  start: number;
  end: number;
  node_id: string;
  entity_type: string;
  provenance_state: MessageProvenanceState;
}

export interface DocumentView {
  document_id: string;
  text: string;
  spans: MessageSpan[];
}
