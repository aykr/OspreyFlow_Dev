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
 * ADR-135 Amendment 4: provider (a hosted provider LiteLLM knows by name), gateway (the client's own OpenAI-compatible AI gateway, at api_base) or bedrock (Amazon Bedrock in London). Default: provider.
 */
export type Kind = "provider" | "gateway" | "bedrock";
/**
 * ADR-135 Amendment 4: key (entered in Admin › Models, kept by the model gateway alone) or iam_role (the namespace's IAM role: no key is stored). Default: iam_role for bedrock, else key.
 */
export type Auth = ("key" | "iam_role") | null;
/**
 * Bedrock's region: eu-west-2 (London) only, and the default for bedrock.
 */
export type Region = string | null;

/**
 * An engine added or edited. Validated as `ModelProviderConfig` is.
 */
export interface EngineInput {
  provider: ModelProviderConfig;
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
