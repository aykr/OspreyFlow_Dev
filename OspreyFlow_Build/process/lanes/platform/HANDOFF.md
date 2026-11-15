# Platform · handoff (15 November 2026; paused at the owner's request for the move to sol)

**Paused at a clean point.** This worktree is on `lane/platform-admin-forms`, from main `cc0e898`, at `7122183`.
Everything is committed; the wip commit above it holds this file alone. **Nothing on this branch goes to main before
v0.6.0 is released** (the orchestrator), and **no server time or stack before v0.6.0's package test ends**.

## The job: v0.6.1's Admin › Models form, FIRST SLICE ONLY (the owner, 15 Nov), then STOP until the owner says

Spec: `process/lanes/admin-forms/{OWNER_PROMPT,OWNER_RULINGS}_2026-11-15.md` and `PREBUILD_FINDINGS.md` (§3.1's jobs, §5.1,
§5.3's draft Am 14). Sketches: the main checkout's `Claude outputs/ospreyflow_admin_forms_2026-11-15/model_form_simulation.html`.
The slice: the provider list, label, address shown and editable, only the provider's jobs, a **typed** model name with a
current example, the preview, the existing write-only key field, and the key plus typed name proved by one call before
Add. **Not in it:** model listing or discovery, Bedrock listing (M3), any wider role, the map form (not built until the
owner has used the model form on the demo). Estimate given: ~3.5 working days.

Stages, recorded as `v061-admin-forms` (`lanes_heartbeat.sh stages platform "v061-admin-forms" …`):
1. **done** `0884d65`: `services/api/model_catalogue.py`, the provider list (Gemini, OpenAI, Anthropic, Azure, Bedrock
   on cloud-platform alone, "Another provider or your own gateway"), jobs, address or asked, prefix, example.
2. **done** `f96ee5b`: the owner's ruling (1): your own gateway on **every** profile (`engine_kinds_offered`,
   `engine_refusal` off cloud-platform: a gateway by a token at its address alone). Bedrock and the IAM role stay
   cloud-platform's. This is Am 14's change to Amendment 7 decision 1.
3. **done** `881920b`: the check before Add. `POST /v1/admin/models/checks` (body read by hand), `POST …/checks/{id}/add`,
   `DELETE …/checks/{id}`; `ModelAdmin.check/add_checked/cancel_check`, `PendingCheck` in the models file (`checks`),
   `CHECK_LIFE` 15 min, audit actions `engine_checked`, `engine_check_cancelled`, `engine_check_expired`; a key-shaped
   label or reference refused on every profile (`label_looks_like_a_key`). Plants `7122183`: 7/7 red
   (`v061-admin-forms/plants_check.py`, `red-first.txt`).
4. **now**: the planted-key test. The Conduit's half is done (`test_model_engine_checks.py::test_the_key_appears_nowhere_it_must_not`:
   responses, headers, URLs, logs, audit, models file, gateway rows). **Left:** the browser's half, with the screen: the
   key in no `localStorage`/`sessionStorage`/IndexedDB, no URL, never auto-completed, the field cleared once sent.
5. **todo**: the screen, `apps/workspace/src/admin/sections/Models.tsx` (613 lines; today's form has JOBS at line 34, the
   key field at ~249). Both looks, every theme, axe, `keyboard.spec.ts` steps (rule 13; pass the registry literally).
   Before touching `admin.css` or Roles and People, **message admin** (it owns them; stay off its v0.6.0 branch).
6. **todo**: ADR-135 Amendment 14 cut to the slice (reserve it in `spec/ADR_RESERVATIONS.md`), with the change to
   Amendment 7 decision 1; and the guide's two corrections in both copies (`spec/10_ADMINISTRATION_GUIDE.md` ~2019 and
   ~2601-2609; `OspreyFlow_Core/docs/administration-guide.md` ~2228, ~2813-2821): "never in the Admin area" → managed
   write-only; "restarts the gateway" → nothing restarted.
7. **todo**: tell the orchestrator it is ready to read; the owner reviews the key test independently before any demo.

**The examples** (checked 15 Nov against each provider's list; keep them): Gemini `gemini-3.8-flash` (never the deprecated
`gemini-2.5-flash`, routed to `gemini-3.5-flash-lite` from 1 Dec 2026), OpenAI `gpt-6.1-sol`, Anthropic `claude-sonnet-5-5`,
Bedrock `amazon.nova-pro-v1:0`; Azure and the gateway none (the name is the client's own).

**Finding raised, with the owner now:** no current Claude model is served in-Region on Bedrock in London (AWS's model
card: Sonnet 5.5 only through `eu.`/`global.` profiles, which Amendment 7 decision 2 refuses). Bedrock's example stays
Nova Pro until the owner rules.

## After v0.6.0 (the owner's order, 15 Nov)

1. **Part 3 first**: the second demo at ospreyflow.app, ~28 h ±5, on `lane/platform-part3` (keep it as it is: named
   Smalls side by side built; the shared Ollama `models.ollama_from` WIP **kept**, since the local model stays beside
   Gemini). Left: rebase onto v0.6.0, the edge (TLS passed through by host name), DNS-01 certificates renewed by Porkbun's
   API with a deploy hook, a Gemini-only check of a Small, the test-stack proof, both fresh builds, the cutover in the
   owner's window. The owner's list: names and records, Porkbun API access and keys (entered by the owner), the Gemini
   key and model, a ruling for osprey-small (the demo lane's), a lease, the free disk, the standard demo's data.
2. **Then the rest of the forms** (M1/M2's listing, M3, the map form P1–P6), on the owner's word.

## Working rules learned this session (in memory too)

- **Beat every 30 minutes by the clock** (`date -u`), with the step's stages; clear an old step's stages first.
- **Lint from `OspreyFlow_Core`** on the diff's own files and read ruff's whole output to its count line (never `| head`);
  restore any of main's lines the formatter reflows.
- `harness.fresh_only` (v0.6.0 `rf`, merged `a048648`): v0.6.0 installs fresh; update, install-over and the cloud INSTALL
  refuse an earlier deployment in its words.
- platform-b may edit `r1_kind.sh`/`r1_kind.py` for v0.6.0's package test (agreed); platform-b is editing
  `cli/ospreyflow/images.py`, so don't touch it until that merges.
- rules-b has #10 (the GB basemap step); answered its three questions (recommended building with the Conduit stopped).
