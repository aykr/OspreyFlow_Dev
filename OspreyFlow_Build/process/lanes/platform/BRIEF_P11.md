# Platform lane · brief P11 · the model route on the cloud-platform profile

Written by the orchestrator, 10 November 2026, from the owner's decision of that day, for a **fresh platform
session started after P7 merges**, from main. Read `spec/06_DECISIONS.md` **ADR-135 Amendment 4** (and Amendments 2
and 3, which built model administration), ADR-148 decisions 7 and 12. Size M. Client track.

**The lane, the stacks, the merge rule.** As P7's: stacks on the server only, Docker never started on this Mac; ask
for a stack, a local slot, or the server's Docker for kind; `make test` through `stack_lease.sh offline platform`;
a live check through `stack_lease.sh live platform`. Never stop on a question: the strict option for access,
logged. Your own lane-reviewer, then the gates. Report **by message**. No real data; no outside service contacted
(engines are proven against recorded fixtures).

**Build** (BUILD_PLAN P11): the LiteLLM gateway rendered by default on the `cloud-platform` profile; an engine type
for the client's own OpenAI-compatible AI gateway (base URL; a token or the namespace's IAM role) and Bedrock by IAM
role, no stored key, London only; the route's host the only model host in the profile's allow list, and only while
an engine using it is enabled.

**Exit.** P1/P2's access and key tests on both engine kinds against recorded fixtures; no key stored for the IAM-role
kinds; the allow list gains the host only when an engine is enabled (red first); `cp-policy-check` green; a friction
row.
