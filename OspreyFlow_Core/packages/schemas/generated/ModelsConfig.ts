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
 * ADR-095: the local model that extracts entities from text. Default: qwen2.5:7b-instruct, the model the product ships with.
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
  extraction?: Extraction;
  vision?: Vision;
  transcription?: Transcription;
  embedding?: Embedding;
}
