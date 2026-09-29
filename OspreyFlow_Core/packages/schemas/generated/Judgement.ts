// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type JudgementId = string;
export type InvestigationId = string;
export type Statement = string;
export type ProbabilityBand = string;
export type Supporting = string[];
export type Contradicting = string[];
export type PrincipalId = string;
export type CreatedAt = string;
export type FlaggedForReview = boolean;
export type FlagReason = string | null;

/**
 * `01_DOMAIN_MODEL.md` §5, `06_DECISIONS.md` ADR-046 (accepted), Phase 8 Stage 4b. "A
 * judgement cannot be saved without at least one supporting reference" (§5) — enforced by
 * `services/api/assessments.py::save_judgement`, not by this model alone (a `Field(min_length=1)`
 * constraint would also reject an *update* that legitimately removes the last supporting item
 * while adding a replacement in the same call — the store's own validation composes the two
 * lists correctly; this model only shapes the row).
 *
 * `supporting`/`contradicting` are references, never copies (`06_DECISIONS.md` ADR-046, following
 * ADR-039) — a `NodeId | EdgeId | DocumentId`, collapsed to `str` here the same way the domain
 * model's own illustrative type union already is (all three are opaque ULID-shaped strings with
 * no structural way to tell them apart). **Disclosed limitation, not fixed here:**
 * `GraphPort` has no `get_edge`, and no document store exists yet
 * (a disclosed gap, not fixed here) — only a `NodeId`
 * citation can be positively confirmed visible today; an `EdgeId`/`DocumentId` citation is always
 * treated as unreadable by `services/api/assessments.py`'s own access check, the same fail-closed
 * default this codebase already applies everywhere else it cannot positively confirm access.
 *
 * `flagged_for_review`/`flag_reason` are not in `01_DOMAIN_MODEL.md` §5's own illustrative
 * Pydantic snippet — grown past it the same way `GraphPort`, `SAME_AS`'s own properties and
 * `Subgraph.filtered_count` each already grew past their own doc's illustrative sketch
 * (`00_ARCHITECTURE.md` §2.1, `01_DOMAIN_MODEL.md` §4, §8.2's own precedent) — the review-flag
 * loop (§5: "every judgement resting on it is flagged for review") needs somewhere to persist
 * that state, and the spec names the behaviour without naming a field for it.
 */
export interface Judgement {
  id: JudgementId;
  investigation_id: InvestigationId;
  statement: Statement;
  probability_band: ProbabilityBand;
  supporting?: Supporting;
  contradicting?: Contradicting;
  resolved_citations?: ResolvedCitations;
  author: PrincipalId;
  created_at: CreatedAt;
  flagged_for_review?: FlaggedForReview;
  flag_reason?: FlagReason;
  [k: string]: unknown;
}
export interface ResolvedCitations {
  [k: string]: string;
}
