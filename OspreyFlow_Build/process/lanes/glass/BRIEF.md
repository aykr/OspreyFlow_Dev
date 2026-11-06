# Glass lane · brief L2.1 · the alerts gap map (no code)

Written by the orchestrator, 6 November 2026 (step 0). Opus, medium. Size M.

**Why.** ADR-145 N5: "map what exists against ADR-109, ADR-130 and ADR-134 before designing anything".
The owner wants an alerts journey mapped before the Glass's navigation is redesigned around it.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 14 as ADR-142 rewords it); ADR-145 (N5, and decisions
1–2 for where alerts will live: the Glass's Monitoring); ADR-109, ADR-130, ADR-133 (its amendments 1–8),
ADR-134; ADR-143 decision 12 (alerts when a load meets a drawn item) and ADR-145 decision 9 (the
promotions-overdue alert), which are new alert kinds the map must place; `spec/02_GLASS_FRONTEND.md`;
`spec/03_CONDUIT_MIDDLEWARE.md`'s alert and monitoring routes.

**Do.** Read the code as the evidence (`apps/workspace/src/alerts/**` and the monitoring screens,
read-only; `services/api`'s alert, monitoring, rule and screening modules; their tests). For every alert
kind that exists today, record: how it is **generated** (rule kind, trigger: load, schedule, list
refresh, manual), how it is **triaged** (queue, severity, team, assignment, close reasons, maker–checker),
how it is **routed** (to whom; people only, ADR-133 Amendment 7), and its **case scope** (which case and
datasets it reads, what it may name, rule 3). Then the same for the kinds ADR-143 and ADR-145 add, as
"not built". Mark each cell built / partly built / recorded only / contradicted, with the file and line
or the ADR that says so. Where the ADRs and the code disagree, the code is the evidence; say so.

**Write.** `spec/glass_redesign/ALERTS_GAP_MAP.md`: the table, a one-page journey (an analyst from an
alert to its case and back; a team lead triaging), and the gaps. End it with the open questions as
**multiple choice** (at most four per round, recommendation first) for the owner; the findings become
their own ADR afterwards (ADR-145 open question 1). Ask the orchestrator to reserve that ADR's number;
do not write the ADR yet.

**Files.** Only `spec/glass_redesign/ALERTS_GAP_MAP.md` and your friction fragment. No code, no tests:
this step changes nothing that runs. No dev stack.

**Exit.** The map in `spec/`, every existing alert kind in it with evidence, the new kinds placed, the
questions written as multiple choice; `make -C OspreyFlow_Build citation-check` and
`product-tree-link-check` green on it (cite no `process/` file from `spec/`).

**Report** (Prompt L's format, also in `process/lanes/glass/REPORT.md`): the exit criteria; the
commits; the questions for the owner; one hand check (which alert to open in the product to see the
biggest gap, with full commands); whether anything of yours is still running.
