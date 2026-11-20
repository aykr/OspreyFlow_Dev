# Slice SE8 · SE8 · Every access, export and model call is attributable (sign-in events; every model call with who, which case and which engine in one record; every export writes its ledger row)

- **Build id:** SE8 (in the plan: "Attribution: sign-in events recorded; every model call recorded with who asked, for which case and to which engine in one record; every export writes its ledger row").
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing in the plan, but **the owner's order (20 November): it does not start ahead of PL4, PL9 or PL10 work.** It touches no file under apps/workspace.
- **Status of this brief: HELD, written by the conductor on 20 November 2026 from DC1a's constraint-4 scout (`slices/DOC1A_REPORT.md`); it is not started.** The scout's line numbers are unchecked: the builder re-reads. The owner's words: the words "every access, export and model call must be attributable"
  stay in the paragraph and the gap is closed by this build; the guides state what "access" covers (every read and write of case data, with the reference reads that carry none, the type list and the map tiles, named as outside it) and say "coming" until this merges.

## What DC1a found (read, not measured)

- The audit is the Postgres table audit_log (services/api/audit.py: recorded_at, principal_id, action, investigation_id, resolved_query, result_cardinality, justification, org_unit); about 300 audit call sites across 429 routes.
- **Sign-in:** neither the pages service nor the Conduit records a sign-in or session event; only admin actions on sign-in are audited (set_guest_sign_in, reset_person_sign_in). The identity provider holds the events.
- **Model calls:** ask, extraction, email extraction, document designation and patterns-ask write an audit row with the person and the case; **ask does not record the engine**; the gateway's usage record (packages/adapters/model_litellm/usage.py) is per engine and job per day with no person or case; transcribe, describe-image and embed (services/api/model_routing.py) write no audit row; background workers were not checked.
- **Exports:** the export ledger (table export_ledger, services/api/export.py) is written by submit_export, the pack export and the report feed. Audit row only, no ledger row: the dataset release export, the rule file export and the source file read. Neither: services/api/platform_backup.py and services/api/object_transfer.py.
- **No test** fails when a model call is not recorded, or when an export skips the ledger.

## What

1. **A single record for a model call:** every call through the model port (ask, extract, embed, NER, vision, transcribe, patterns and any worker path) writes one record with who asked (the person, or the named service identity for a background job), for which case (or "none"), and to which engine (the engine name and the model, as the Admin sees them), in the audit store; no content of the call, no key. Decide where the single write sits (the model routing layer, so no caller can skip it) and say so in the report. A fake gateway must refuse what the real one refuses (rule 15).
2. **Every export writes its ledger row:** the dataset release export, the rule file export, the source file read as an export, and any other path that sends case data out of the deployment (list them by reading: the backup and the object transfer are operator actions: say whether the ledger or the audit records them, and what they carry; do not invent a case for them).
3. **Sign-in events recorded:** a sign-in, a refused sign-in and a sign-out, by the page service and the Glass's sign-in, are recorded with who, when and the outcome, without a token. The page service (apps/pages) has the session; the Conduit receives the person's token on each call. Choose the smallest place that sees both (say where), and keep the pages service's token out of every log.
4. **Tests, red first:** a test per behaviour that fails when the write is removed (rule 12), at the real call site: each model path writes the record with the engine; each export path writes a ledger row; the sign-in events appear. A planted fault for each. A route-walk or registry test that fails when a new model path or a new export path exists without its record, if one can be written cheaply.
5. **Not in scope:** making the audit table tamper-evident (a separate row); the Admin audit screen's display of the new fields (a later screen slice); the reference reads that carry no audit (type list, map tiles).

Binding: process/CLAUDE.md rules 3, 4, 11, 12, 15; the owner's key rules (never log a key); ADR-135 and the audit ADRs; British English. No file under apps/workspace. The owner's order: this does not start ahead of PL4, PL9 or PL10 work.
