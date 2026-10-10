# The prompt that starts the ADR-109 build session (paste it whole)

Written 10 October 2026, alongside ADR-109 (PROPOSED) in `spec/06_DECISIONS.md`. Paste the block
below as the first message of a fresh Claude Code session started in the repository root.

---

Read `OspreyFlow_Build/process/CLAUDE.md` first — its fifteen rules bind every session. Then read,
in order: `spec/06_DECISIONS.md`'s **ADR-109 (PROPOSED)** at the end of the file, ADR-108 with its
four amendments (the shape this programme follows), ADR-036/037 (the change-stream evaluation path
you will build on), ADR-100 (the pattern machinery), and `process/FDE_HANDOVER.md` §6.0 for the
deployment's current state. Confirm rule 14 before touching anything: `ListAgents`, and treat
"handed back a report" as distinct from "stopped running".

You are building ADR-109: preventive AML/EDD — the typology rules engine on the existing
change-stream evaluation chassis, alert triage with explainable alerts, UBO tracing with
cumulative ownership, the no-code typology builder, and contextual risk propagation.

**Process, in this order, and do not start coding early:**

1. **Design review first.** Take me through ADR-109's decision points D1–D7 as choice batches
   (AskUserQuestion), exactly as ADR-108's Q1–Q7 were taken. Where the recorded recommendation and
   my answer differ, say so and record my ruling. Record all rulings into ADR-109 (flipping it
   from PROPOSED to accepted) before any code.
2. **Phase the build A→E** as ADR-109 proposes, one phase per stretch, each phase exiting green
   (unit, store, route, keyboard, lints, mypy) before the next begins. Red-first throughout: every
   gate shown red before it is trusted (rule 15), every rule-fires case paired with a
   rule-refuses case, every new read path with an access-control test (rule 4), every new Glass
   surface with its own keyboard walkthrough registry (rule 13).
3. **Spec as you go** (rule 11): each phase lands with its ADR-109 amendment and any spec-09/02
   section it changes, in the same commit series — never answered only in chat.
4. **Build on what exists; name any duplication you are about to create and stop.** The streaming
   engine is the change-stream evaluation path plus `services/ingest/typologies.py` (which has no
   production caller — wiring it is phase A, not writing new detectors). The builder extends the
   pattern language. Alerts extend the alert store unless D2 is ruled otherwise. FIBO's
   `BENEFICIAL_OWNER_OF`/`CONTROLS` with `percent` are live in the deployment ontology
   (ADR-108 Amendment 4); Operation Ledger is the seeded synthetic case to grow.
5. **Demo data discipline (rule 9 — do not negotiate this in code):** everything committed or in
   CI is synthetic. ICIJ Offshore Leaks and OpenSanctions may only ever be used through my local
   `real_data_exceptions.yaml` on my machine, and OpenSanctions' CC-BY-NC licence gets a register
   entry before any local use. If a phase seems to need real data committed, stop and say so.

Cautions that stand from previous sessions: never run the whole test tree (`make
dev-up`/unit-suite wipes the real deployment — use the throwaway stack in
`process/FDE_HANDOVER.md`/memory); never stage `OspreyFlow_Core/osprey.yaml` or
`OspreyFlow_Core/data/`; commit with Conventional Commits ending "record <previous short hash>";
never push — I push. `make refresh` you may run yourself after committed changes; a refresh signs
me out, so batch it and tell me when a sign-in is needed. I will answer the design review and then
leave the session to complete the ruled phases without waiting for approvals.

---

**Model/effort note for the owner (not part of the paste):** run the design review and phases A,
D and E at default or high effort; fast mode is fine throughout (it keeps Opus quality). Low
effort is not recommended for this programme's gate and access-control work.
