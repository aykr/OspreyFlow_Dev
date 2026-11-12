# Docs lane · brief D2c part 4 · the model route on the cloud-platform profile (P11), then D2c closes (S)

Written by the orchestrator, 12 November 2026, at the owner's request, for a **fresh docs session on `sol`**, from
**main** (`git fetch`, branch `lane/docs-d2c4` from `main`). Read BRIEF_D2c.md, ADR-135 Amendments 4, 7 and 8
(P11 parts 1 and 2 as built), and the guide's §6a, §10.1 and Appendix A first. Opus, medium. Size S.

**Why:** P11 merged on 11 November, but §6a has no section on the model route: it shows only in Appendix A
(1.77), §10.1 (1.78), the gateway's line in §6a.1 and 1.80's alignment. The owner wants it written now, so the
Client install view shows only what is truly left. P8's section is a step of its own after the client's install
(D2e), not part of this one.

**Write, in both copies (OspreyFlow_Core/docs/administration-guide.md §6a, and spec/10_ADMINISTRATION_GUIDE.md word
for word):** a new §6a subsection, *The model route*, before *Coming*, as built and in an operator's words:
- the model gateway (LiteLLM), always rendered; how the namespace reaches the client's own approved gateway, or
  Bedrock by the namespace's IAM role (no key stored anywhere), with the settings (`models.provider(s).kind`,
  `auth`, `region`) and the region answer;
- the Terraform it renders for Bedrock (the role's statements), and what the platform team applies;
- the egress rows the route needs, and what Admin › Models allows and refuses on this profile (§10.1's refusal
  words, with the render-again, `helm upgrade`, Terraform order the guide now gives);
- Laurium's key on the gateway, as already said in §6a.1, cross-referenced rather than repeated;
- what is not yet tried against the client's own gateway or account (the live checks), said as such.
Check every claim against the code on main (harness/cloud_platform/*, services/api/model_admin.py, packages/schemas/
deployment.py), with the file and line in your report. Remove anything about the model route from §6a.9 *Coming*
that is now built.

Version row 1.88, in an operator's words, with ADR references only (no P-numbers or lane names), ending
"PDF made by the orchestrator at merge". Docs gates on the Mac: test_admin_guide; test_docs_pdf red for the admin
PDF alone. One lane-reviewer round, then send "ready". Not pushed; the orchestrator merges.

**Never.** osprey-small (the owner's demo, being rebuilt tonight by the demo lane) is never touched. Nothing of yours
runs on the server from 12:00 UK on Friday 13 November.
