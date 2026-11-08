// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Start = string;
export type End = string;
export type Engine = string;
export type EngineLabel = string;
export type Job = string;
export type Calls = number;
export type Succeeded = number;
export type Failed = number;
export type PromptTokens = number;
export type CompletionTokens = number;
export type Tokens = number;
export type Rows = UsageRow[];

/**
 * `GET /v1/admin/models/usage`: the gateway's own records over the period, by engine and job.
 * The period is whole days, UTC, both ends included.
 */
export interface ModelUsageView {
  start: Start;
  end: End;
  rows: Rows;
  by_engine: ByEngine;
  by_job: ByJob;
  total: UsageFigures;
  [k: string]: unknown;
}
/**
 * One engine and one job over the period.
 */
export interface UsageRow {
  engine: Engine;
  engine_label: EngineLabel;
  job: Job;
  figures: UsageFigures;
  [k: string]: unknown;
}
/**
 * Counts only (ADR-135 Amendment 3 decision 3): never a prompt, an answer, a key, a person or
 * a source-system identifier. `calls` counts every call the gateway recorded, refused ones
 * included; tokens are those the engine reported.
 */
export interface UsageFigures {
  calls?: Calls;
  succeeded?: Succeeded;
  failed?: Failed;
  prompt_tokens?: PromptTokens;
  completion_tokens?: CompletionTokens;
  tokens?: Tokens;
  [k: string]: unknown;
}
export interface ByEngine {
  [k: string]: UsageFigures;
}
export interface ByJob {
  [k: string]: UsageFigures;
}
