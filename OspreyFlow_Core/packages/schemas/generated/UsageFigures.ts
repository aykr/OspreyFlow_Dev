// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Calls = number;
export type Succeeded = number;
export type Failed = number;
export type PromptTokens = number;
export type CompletionTokens = number;
export type Tokens = number;

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
