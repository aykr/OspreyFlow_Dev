# case-b · P12 part 2 · the plan (11 November 2026)

Brief: `BRIEF_P12p2.md`. Working from `spec/06_DECISIONS.md` ADR-135 Amendments 5 (Laurium chosen at set-up), 6 (its own
service; decision 8, its scoped key; "making the key at start, and replacing it when the master key rotates, are part
2's") and 7 (the two engine kinds, P11 part 1); ADR-148 decisions 7 (egress denied by default) and 8 (`images push`)
and Amendment 1 (the profile as built); `spec/05_DEPLOYMENT.md` on the render. ADR-135 Amendment 8 (P11 part 2) and
ADR-148 Amendment 5 (P7b) are reserved, not written: this plan does not lean on either beyond the brief's words.

## What is there now (read, 11 November)

- The chart is generic: `templates/workloads.yaml` ranges over `.Values.workloads`, which the render makes from the
  profile's services (`harness/render.py`, `compose_services` → `harness/cloud_platform`). No per-service templates.
- `templates/networkpolicies.yaml`'s `ospreyflow-internal` lets **every** deployment pod reach every other. Policies
  are additive, so a Laurium pod under it can reach every store: "egress to the gateway alone" needs Laurium left out
  of that policy and given its own.
- **No extraction-engine setting exists** in the schemas, the Conduit or the harness: the Conduit always extracts
  through `adapters/model_litellm` (Deep read).

## The pieces, in order (profile wiring first, as the orchestrator asked)

1. **The setting** (schemas ride with the step): `models.extraction_engine: deep_read | laurium` in the deployment
   config, default `deep_read`; refused on any profile but `cloud-platform` until a local-lite render exists for it.
   Test first: the schema refuses another value; the default renders no Laurium.
2. **The render** (platform's files, as `P12p2_render.diff`): with `laurium` chosen, the service `laurium` (its
   Dockerfile, `services/laurium/Dockerfile`, in `service_images`, so in `images.yaml` and `images push`), its
   resources in `profile.yaml`, its environment (`OSPREY_LAURIUM_GATEWAY_URL=http://litellm:4000/v1`, nothing else),
   never on the egress network (`egress_needs` unchanged: it reaches the gateway inside the namespace). Not chosen:
   nothing of Laurium in any artefact (the no-LangChain check's image leg reads the same).
3. **My template, `templates/laurium-networkpolicy.yaml`**: Laurium's pods reach the gateway's pods on its port and
   DNS, nothing else; reached only by the Conduit and the workers. With a one-line change to
   `networkpolicies.yaml`'s internal policy (a `NotIn [laurium]` on its selector) **sent as a diff**: whose file it is
   is asked of the orchestrator. Red first: a render test reading the rendered policies, Laurium's effective egress
   exactly {the gateway, DNS}, planted with the internal policy's exclusion removed; `cp-policy-check` on all three
   shapes with Laurium rendered, red on a planted wider egress.
4. **The Conduit's routing**: with `laurium` chosen, `ModelPort.extract` is `ExtractLauriumAdapter` at
   `http://laurium:8000`, every other operation stays LiteLLM's; Laurium's key made at start with the deployment's
   own models and replaced when the master key rotates (decision 8; the factory's teardown hazard carried from part 1
   is fixed here: never delete a key it did not make). Access test: rule 4 does not apply (no read path), but the
   setting's change is audited behind `manage_models` (piece 5).
5. ***Admin › Models*'s setting** (P11 part 1's area): the choice, audited behind `manage_models`, sent to
   platform-b as a diff if it touches `Models.tsx` or its routes; its keyboard case in the same diff (rule 13).
6. **The pack's preset**: `cloud-platform`'s pack presets `deep_read` (Laurium is chosen, never assumed) unless the
   brief's source names otherwise; to confirm with the orchestrator.
7. **The exit's live case**: Laurium reading a conforming answer from the client's own engine, the route P11 part 2
   renders (on kind, or a stand-in that refuses what the real one refuses), leased; its own test, beside part 1's
   strict xfail, which stays.

## Asked of the orchestrator (not blocking: each built as recommended meanwhile)

- `networkpolicies.yaml`'s owner (recommended: platform's, sent as a diff).
- The pack's preset: `deep_read` (recommended) or `laurium`.
- An ADR reservation for part 2's as-built record (recommended: ADR-135 Amendment 9).
- Whether the setting may be local-lite too (recommended: no, cloud-platform alone, as P11's engine kinds are).
