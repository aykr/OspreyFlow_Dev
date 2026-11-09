# Platform lane · brief P7 · the `cloud-platform` profile (ADR-148)

Written by the orchestrator, 9 November 2026, from the owner's client decision (ADR-148, ACCEPTED (design)), for
a **fresh platform session on the default account** (`ayan`), opened **after P5 merges** (it replaces BRIEF.md
then). Read `spec/06_DECISIONS.md` ADR-148 first (decisions 1–5, 7, 8, 12 and 14 are this step), then
`process/BUILD_PLAN_PARALLEL_LANES.md`'s P7 row and merge-order items 19–21. Opus, medium. Size L.

**No client access is needed or wanted.** P7 proves itself on a local **kind or k3d cluster on the owner's test
server** (`ospreyflow-test`, which has Docker), set up to the platform's rules: the Calico deny-egress policy and no
ReadWriteMany storage class. Never create anything on the client's GitHub or AWS: every client-side change is a pull
request the owner's team raises once access is granted. The *live on the platform* exit is recorded later, when the
client's namespaces exist. No real data, ever (rule 9).

**The lane, the stacks, the merge rule.** Platform's row, plus ADR-148's ownership lines: the harness's
`cloud-platform` profile files, `deploy/generated/cloud-platform/`, `deploy/helm/ospreyflow/templates/ingress.yaml`
(remove its citation-allowlist line when you write it), the policy check and `ospreyflow images push`. **Shared,
first and alone:** the numeric UID `10001` in every `Dockerfile`'s `USER` line, as its own small commit, which the
orchestrator merges ahead of the rest (merge order 20). **The owner's files:** `make cp-policy-check`'s Makefile
target and `ci.yml` job go in `process/lanes/platform/P7_ci_makefile.diff` (merge order 21). The kind or k3d cluster
runs on the server: ask the orchestrator for the server's Docker, as for P5's image work. Name your images and
cluster `osprey-p7-*`, never touch `osprey-small` or the `osprey-test-*` stacks, and tear it all down after. `make
test` runs on the server through `stack_lease.sh offline platform -- …`. Ask before make -k ci or Playwright here.
Report by message.

**Build:** P7's row: the profile rendering Helm values into an existing namespace and the namespace's Terraform for
RDS, ElastiCache, OpenSearch, S3, ECR and IRSA in the environments repository's shape; the chart's optional Ingress;
UID 10001, `runAsNonRoot`, no privilege escalation, capabilities dropped on every rendered pod; the managed stores in
place of ours, their connection details from the platform's secrets; ArcadeDB ×3, ClickHouse ×2 and Keeper ×3 as
StatefulSets on `gp2-expand` with PodDisruptionBudgets (one each in development); the Calico deny and allow policies
from the settings ADR-135 Am 2 and ADR-147 gate; `ospreyflow images push --registry`; the Conduit built without Java
on this profile (a build argument), with *Admin › Maps*' Build saying so (pending the owner's ruling on ADR-148
question 3; build to the recommended answer); `make cp-policy-check`.

**Exit** (P7's row): `make cp-policy-check` green on the render and red on each planted fault (a root pod, a named
UID, an RWX claim, a hostPath, a port below 1024, a foreign registry, no deny-egress); ArcadeDB, ClickHouse and Keeper
each shown to start as UID 10001 (or a thin image of ours, in the licence register); the acceptance scenarios green on
the kind/k3d cluster; `local-lite`, `small` and `cluster` renders unchanged except the UIDs; a friction row.
