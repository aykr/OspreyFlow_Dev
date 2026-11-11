# P12: Laurium's licence check, and the owner's ruling (11 November 2026)

Done before any adapter code, as ADR-135 Amendment 5 decision 5 requires. The orchestrator's agent read metadata,
wheels and repositories only, ran no downloaded code, and resolved with `uv pip compile --only-binary :all:` on
Python 3.13 (manylinux_2_28 x86_64 and macOS arm64). The per-package table is `laurium-licences-0.6.0.tsv`;
the pinned core trees are `base-*.txt`.

**Laurium:** PyPI `laurium` 0.6.0 (6 May 2026), https://github.com/moj-analytical-services/laurium, tag v0.6.0
at 5b034471. MIT, "Copyright (c) 2025 Ministry of Justice", in its LICENSE file and in the wheel's License-File
only. PyPI's `license`, `license_expression` and classifiers carry no licence, so the gate reads it as UNKNOWN.

**Core install (121 packages):** no GPL, AGPL, LGPL, SSPL or non-commercial licence. Unclear to the gate, all MIT
on the evidence: `laurium` (file only), `arrow-pd-parser` 2.2.0 (MoJ; `LICENCE.md` inside the wheel; no metadata;
repository 404), `tiktoken` 0.14.0 (full MIT text in the License field, which the gate's parser rejects),
`en-core-web-sm` 3.8.0 (spaCy's model, MIT by Explosion's metadata, trained on OntoNotes 5 and WordNet 3.0; not on
PyPI, from explosion/spacy-models' GitHub release).

**`encoder` extra:** FAIL on Linux x86_64: 16 NVIDIA CUDA wheels, proprietary or unlicensed. LLM extraction does
not need it.

**Not a licence matter:** Laurium 0.2.0 onwards requires Python >= 3.13; OspreyFlow runs 3.12. 0.1.0 (3.12)
makes torch a hard dependency.

## The owner's ruling (11 November, about 06:00 UTC), all four on the orchestrator's recommendation

1. **Laurium runs as its own service on Python 3.13**, built only when the extraction engine Laurium is chosen.
   The Conduit keeps a thin `ModelPort.extract` adapter that calls it; every model call still goes through the
   gateway, and an image or deployment without Laurium carries no LangChain, spaCy or Laurium. This changes
   Amendment 5 decision 1 ("built into the images that serve `ModelPort.extract`"): ADR-135 Amendment 6, reserved
   for platform, records it.
2. **Recorded licence entries** for `laurium`, `arrow-pd-parser` and `tiktoken`, each pinned to its version with
   the MIT evidence above, and the MoJ copyright notices carried in the deployment's notices.
3. **`en-core-web-sm` 3.8.0 accepted as MIT** on Explosion's terms, fetched from its pinned GitHub release by hash:
   the one source beyond the public package index (the owner's 10 November instruction otherwise stands).
4. **The `encoder` extra is never installed.** Encoder models, if ever wanted, are a decision of their own, on
   CPU-only wheels.

Pin from PyPI's 0.6.0 artefacts by hash, never from the repository's main, which has moved past 0.6.0 with the
version string unchanged.
