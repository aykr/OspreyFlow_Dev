// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * LiteLLM's name for the provider: openai, anthropic, gemini, azure, bedrock…
 */
export type Name = string;
/**
 * ADR-135: the name analysts see for this engine. Default: OpenAI, Anthropic or Gemini for those three, else the provider's name capitalised.
 */
export type Label = string | null;
/**
 * The provider's address, where it is not LiteLLM's default (an Azure deployment, a proxy)
 */
export type ApiBase = string | null;
/**
 * ADR-136: true when the deployment's organisation holds a data-processing agreement with the provider covering this key. A dataset whose egress is `contracted` is sent only to a provider marked so. Default: false.
 */
export type PrivacyContract = boolean;
/**
 * ADR-136: the agreement's reference, in words (for example DPA 2026/07); never a secret. Shown beside the mark.
 */
export type ContractReference = string | null;
/**
 * ADR-135 Amendments 4 and 7: provider (a hosted provider LiteLLM knows by name), or at profile: cloud-platform only, gateway (the client's own OpenAI-compatible AI gateway, at api_base) or bedrock (Amazon Bedrock in London). Default: provider.
 */
export type Kind = "provider" | "gateway" | "bedrock";
/**
 * ADR-135 Amendments 4 and 7: key (entered in Admin › Models, kept by the model gateway alone), or at profile: cloud-platform only, iam_role (the namespace's IAM role: no key is stored). Default: iam_role for bedrock, else key.
 */
export type Auth = ("key" | "iam_role") | null;
/**
 * Bedrock's region (profile: cloud-platform): eu-west-2 (London) only, and the default for bedrock.
 */
export type Region = string | null;
export type KeyState = "set" | "none" | "lost" | "iam_role";
export type KeySetAt = string | null;
export type KeySetBy = string | null;
export type DefaultFor = string[];
export type RequestsPerMinute = number | null;
export type TokensPerMinute = number | null;
export type BudgetTokens = number | null;
export type BudgetPeriod = ("day" | "month") | null;
export type Engines = AdminEngine[];
export type LocalOnly = boolean;
export type SendableHandlingCodes = string[];
export type Source = "osprey.yaml" | "models file";
export type EngineKinds = ("provider" | "gateway" | "bedrock")[];

/**
 * `GET /v1/admin/models`.
 */
export interface ModelsAdminView {
  engines: Engines;
  defaults: Defaults;
  local_models: LocalModels;
  local_only: LocalOnly;
  sendable_handling_codes: SendableHandlingCodes;
  source: Source;
  engine_kinds?: EngineKinds;
  [k: string]: unknown;
}
/**
 * One hosted engine as *Admin › Models* shows it: its settings, its limits, and its key's state
 * and record — never the key.
 */
export interface AdminEngine {
  provider: ModelProviderConfig;
  key_state: KeyState;
  key_set_at?: KeySetAt;
  key_set_by?: KeySetBy;
  default_for?: DefaultFor;
  limits?: EngineLimits;
  [k: string]: unknown;
}
/**
 * A client's own model provider (ADR-114 decision 11, Amendment 6 point 4; ADR-135), reached
 * through the deployment's LiteLLM gateway, for material whose handling code is in
 * `models.sendable_handling_codes` only; anything else runs on the local model. Its key is never
 * here: it is `OSPREY_MODEL_KEY_<NAME>` at install (`OSPREY_MODEL_PROVIDER_KEY` for the single
 * `models.provider`), kept in the deployment's `deployment.env` and read by the gateway alone.
 */
export interface ModelProviderConfig {
  name: Name;
  label?: Label;
  roles: Roles;
  api_base?: ApiBase;
  privacy_contract?: PrivacyContract;
  contract_reference?: ContractReference;
  kind?: Kind;
  auth?: Auth;
  region?: Region;
}
/**
 * The roles it takes, each with the provider's model for it
 */
export interface Roles {
  [k: string]: string;
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
export interface Defaults {
  [k: string]: string;
}
export interface LocalModels {
  [k: string]: string | null;
}
