# Platform-b · handoff, 11 November 2026, about 08:00 UTC (the server session, the laptop still offline)

**Two steps built, neither merged nor pushed.** Both had my own lane-reviewer's round and its fixes; the
orchestrator's independent review is owed for each, then the rebase and the gates once at that head.

**P11 part 1** on `lane/platform-b-p11` (log: `SERVER_LOG.md` there; `p11/REPORT.md`): built at 8d2f18b (code)
— the client's gateway by its token and Bedrock in London by the IAM role in *Admin › Models*, no key stored
for an IAM-role engine. A credential step: two review rounds. Local branch `p11-pre-split-0383b63` keeps the
history before the schema commit was moved to the head (delete once reviewed).

**The carries** on `lane/platform-b-carries` (log: `SERVER_LOG-carries.md`; `carries/REPORT.md`): built at
96453a0 — one atomic writer for `deployment.env`, the refresh's lock, stage and pending record, every verb's
lockout words, the chart's quoting.

**Open questions (the orchestrator's):**
1. Carries Q1: CARRIES row 104 (a shell value counts as held) contradicts ADR-114 Am 39 decision 2; the code
   follows the ADR until ruled.
2. P11 Q1 (for the owner): the client's gateway by the IAM role, refused for now.
3. Amendment numbers for `p11/ADR-135-AS-BUILT-DRAFT.md` and `carries/ADR-114-AS-BUILT-DRAFT.md` (rule 11).
4. Ownership rulings (each report lists the files); `p11/shared-files-P11.diff` to apply at merge;
   `carries/DOCS_REQUEST.md` to the docs lane.

**Running:** nothing. No stack, no container of mine. **Don't redo:** either step's fixes (the red records are
`p11/RED_RECORD.md` and `plants.md`).

**Server notes:** `git switch` is refused here, `git checkout` works; heredocs holding `${…}` are refused, so
edits go through a Python script in /tmp; the keyboard usage-days case needs `LANG=en_GB.UTF-8`; the GPU
preflight case and `test_valkey_config` (the pinned `VALKEY_PORT`) fail on this server for its own reasons.
