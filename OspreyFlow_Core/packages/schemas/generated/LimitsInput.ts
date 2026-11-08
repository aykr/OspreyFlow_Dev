// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RequestsPerMinute = number | null;
export type TokensPerMinute = number | null;
export type BudgetTokens = number | null;
export type BudgetPeriod = ("day" | "month") | null;

/**
 * `PUT /v1/admin/models/engines/{name}/limits`.
 */
export interface LimitsInput {
  limits: EngineLimits;
}
/**
 * An engine's limits (ADR-135 Amendment 3), applied by the model gateway to every call the
 * Conduit sends that engine. Each is optional; none set is no limit. A budget is in tokens (prompt
 * and completion together) per day or per calendar month, UTC; the call that crosses it is
 * answered and the next one refused.
 */
export interface EngineLimits {
  requests_per_minute?: RequestsPerMinute;
  tokens_per_minute?: TokensPerMinute;
  budget_tokens?: BudgetTokens;
  budget_period?: BudgetPeriod;
}
