// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: true — no hosted fallback
 */
export type LocalOnly = boolean;
/**
 * Default: none. A provider name, never a credential.
 */
export type HostedFallback = string | null;
/**
 * Default: empty. Which handling codes may leave for a hosted model.
 */
export type SendableHandlingCodes = string[];
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
 * ADR-135 Amendments 4 and 7: key (entered in Admin › Models, kept by the model gateway alone), or at profile: cloud-platform only, iam_role (the gateway's own IAM role: no key is stored). Default: iam_role for bedrock, else key.
 */
export type Auth = ("key" | "iam_role") | null;
/**
 * Bedrock's region (profile: cloud-platform): eu-west-2 (London) only, and the default for bedrock.
 */
export type Region = string | null;
/**
 * ADR-135: the providers an administrator enables; each key is OSPREY_MODEL_KEY_<NAME>, entered at install or with `ospreyflow models key`.
 */
export type Providers = ModelProviderConfig[];
/**
 * ADR-095: the local model that extracts entities from text. Default: qwen2.5:7b-instruct, the model the product ships with; with resources.gpu: nvidia and this not named, qwen2.5:14b-instruct (ADR-135 Amendment 1).
 */
export type Extraction = "qwen2.5:7b-instruct" | "qwen2.5:14b-instruct";
/**
 * ADR-095: the local model that describes an image and reads its text.
 */
export type Vision = "moondream:1.8b-v2-q4_K_M";
/**
 * ADR-095: the local model that transcribes a video's speech.
 */
export type Transcription = "Systran/faster-whisper-tiny.en";
/**
 * ADR-095: the local model that turns text into vectors.
 */
export type Embedding = "all-minilm:22m-l6-v2-fp16";
/**
 * ADR-135 Amendments 5 and 6: deep_read (the default) or, at profile: cloud-platform only, laurium (its own service, every call through the gateway).
 */
export type ExtractionEngine = "deep_read" | "laurium";

/**
 * `05_DEPLOYMENT.md` §2.1's Models screen: "Local only, or local with a named hosted fallback
 * — and if hosted, which handling codes may be sent to it. **Defaults to none**."
 *
 * The default here is that sentence, enforced rather than described: no hosted fallback, and an
 * empty set of sendable handling codes. `04_VAULT_BACKEND.md` §4's egress exception is off unless
 * something turns it on.
 */
export interface ModelsConfig {
  local_only?: LocalOnly;
  hosted_fallback?: HostedFallback;
  sendable_handling_codes?: SendableHandlingCodes;
  /**
   * ADR-114 Amendment 6: one provider, read as a one-entry `providers` whose roles default to it; its key is OSPREY_MODEL_PROVIDER_KEY. Not with `providers`.
   */
  provider?: ModelProviderConfig | null;
  providers?: Providers;
  defaults?: Defaults;
  extraction?: Extraction;
  vision?: Vision;
  transcription?: Transcription;
  embedding?: Embedding;
  extraction_engine?: ExtractionEngine;
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
 * ADR-135: each role's default engine, `local` or an enabled provider's name. A role not named runs on `local` (for the single `provider`, on it).
 */
export interface Defaults {
  [k: string]: string;
}
