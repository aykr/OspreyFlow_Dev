// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ReadFrom = "selection" | "graph" | "case";
export type Documents = number;
export type DocumentsWithoutText = number;
export type Items = number;
export type Links = number;
export type Events = number;
export type Selected = number;
export type FirstSelected = string | null;
export type Found = number;
export type Passages = number;
export type LimitedReason = string | null;
export type CountsExact = boolean;
export type More = boolean;

/**
 * What a question read, or will read (ADR-098 Amendment 7), counted as the asker from their own
 * view: nothing they may not see moves a figure (rule 3). Kept with the answer, which a later
 * reader is shown only if they may see every node, link and Document counted.
 */
export interface ReadSummary {
  read_from: ReadFrom;
  documents: Documents;
  documents_without_text: DocumentsWithoutText;
  items: Items;
  links: Links;
  events: Events;
  selected: Selected;
  first_selected: FirstSelected;
  found: Found;
  passages: Passages;
  limited_reason: LimitedReason;
  counts_exact: CountsExact;
  more: More;
  [k: string]: unknown;
}
