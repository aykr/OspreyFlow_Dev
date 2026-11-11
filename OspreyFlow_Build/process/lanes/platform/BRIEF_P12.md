# Platform lane · brief P12 · Laurium as a second extraction engine (licence first)

Written by the orchestrator, 10 November 2026, from the owner's decision of that day, for a **fresh platform
session started after P7 merges**, from main. It does not wait for P11: prove it on `local-lite` through the
gateway's stand-in model. Read `spec/06_DECISIONS.md` **ADR-135 Amendment 5**, ADR-098 (Deep read and Quick scan),
and the licence register. Size M. Client track.

**First, and before any adapter code: the licence check.** Fetch Laurium only from its public package index, as a
pinned dependency, into a scratch environment; record the licence of Laurium's own repository and of **every**
dependency it brings (`pip-licenses` on that environment), against the register (`make licence-check`'s allowlist).
**If anything fails the register (GPL or AGPL, or no licence stated), stop and ask the owner, through the
orchestrator, before writing the adapter.** This is a hard stop, not a recommended-option decision.

**The lane, the stacks, the merge rule.** As P11's. No real data; no outside service contacted beyond the package
index for the pinned fetch.

**Build** (BUILD_PLAN P12): the shared commit first (the optional extra `ospreyflow[laurium]` and the lock file's
Laurium entries, pinned by hash); `packages/adapters/extract_laurium/` implementing `ModelPort.extract` only, built
into the images that serve it only when selected; the *extraction engine* setting (Deep read or Laurium) in the
set-up console and *Admin › Models*, audited behind `manage_models`; the `cloud-platform` pack presets Laurium;
Laurium's chat model configured with the gateway's endpoint only, any other host refused at start; the domain model
mapped to Laurium's schema and its output to `ExtractionResult`, findings *inferred* and traced.

**Exit.** The licence record in the register (or the owner's ruling); `ModelPort.extract`'s conformance suite green
on both adapters; a Laurium configuration naming another host refused (planted); Laurium's findings arrive
*inferred* with their document, accepted and rejected in the reader as Deep read's (keyboard and axe in three
themes); an image built without the extra contains no `langchain` (checked in CI); access test: no `manage_models`,
no change; a friction row.

**The licence check is done, and the owner has ruled (11 November).** Read `p12/LICENCE_CHECK.md` first: Laurium runs as its own Python 3.13 service (ADR-135 Amendment 6, reserved for you, written before the code), the three recorded licence entries, the spaCy model from its pinned GitHub release, and never the `encoder` extra. No further stop for the licence.
