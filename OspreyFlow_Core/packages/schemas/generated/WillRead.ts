// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ReadFrom = "selection" | "graph";
export type Documents = number;
export type DocumentsWithoutText = number;
export type Items = number;
export type Links = number;
export type Events = number;
export type Selected = number;
export type FirstSelected = string | null;
export type Engine = string | null;
export type EngineLabel = string | null;
export type Model = string | null;
export type Name = string;
export type Label = string;
export type Reason = string;
export type Unusable = UnusableEngine[];
export type Refused = string | null;

/**
 * `POST …/questions/will-read`, every field always sent: what the question would read, and the
 * engine that would answer it as the routing decides (ADR-135 Amendment 12), before anything is
 * sent.
 */
export interface WillRead {
  read: ReadSummary;
  engine: Engine;
  engine_label: EngineLabel;
  model: Model;
  unusable: Unusable;
  refused: Refused;
  [k: string]: unknown;
}
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
  [k: string]: unknown;
}
/**
 * An engine the deployment has that cannot answer this question, and why, in words.
 */
export interface UnusableEngine {
  name: Name;
  label: Label;
  reason: Reason;
  [k: string]: unknown;
}
