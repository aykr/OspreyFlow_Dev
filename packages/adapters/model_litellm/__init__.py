"""`ModelPort` over a LiteLLM proxy — `docs/00_ARCHITECTURE.md` §2.4, `docs/07_BUILD_PLAN.md`
Phase 6."""

from __future__ import annotations

#: The model the `ModelPort` conformance suite calls for `extract()` — `06_DECISIONS.md` ADR-020
#: pins the actual backing image/weights by digest in `deploy/compose/dev.yaml`; this is only the
#: logical name LiteLLM's own config routes to that backend. A deployment's `osprey.yaml` points
#: real extraction at whatever model it chooses — this name is conformance-only, never hardcoded
#: into a caller outside `tests/conformance`.
CONFORMANCE_MODEL = "qwen2.5:0.5b-instruct"

#: The model the conformance suite calls for `embed()` — a separate, much smaller model, since
#: embedding and extraction are different tasks with different backends even where both happen to
#: run on Ollama locally. Digest-pinned the same way, ADR-020.
CONFORMANCE_EMBED_MODEL = "all-minilm:22m-l6-v2-fp16"

#: The model the conformance suite calls for `transcribe()` — Phase 6 Stage 2. Served by a
#: faster-whisper-backed OpenAI-Whisper-compatible proxy (`deploy/compose/dev.yaml`'s `speaches`
#: service), pinned by Hugging Face commit sha rather than an Ollama manifest digest — Ollama
#: itself is not involved in this path (`06_DECISIONS.md` ADR-020's Stage 2 addendum).
CONFORMANCE_TRANSCRIBE_MODEL = "Systran/faster-whisper-tiny.en"

#: The model the conformance suite calls for `describe_image()` — Phase 6 Stage 2. Larger than the
#: text/embedding pins (a vision-language model has no smaller-still tier the way `all-minilm`
#: is for text embeddings), which is exactly why its own conformance job runs on a slower cadence
#: (`06_DECISIONS.md` ADR-020's Stage 2 addendum) rather than every PR.
CONFORMANCE_VISION_MODEL = "moondream:1.8b-v2-q4_K_M"
