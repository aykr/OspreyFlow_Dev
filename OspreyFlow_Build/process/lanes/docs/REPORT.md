# docs lane · report · D2c part 1, the `cloud-platform` profile in the administration guide (11 November 2026)

Brief: `process/lanes/docs/BRIEF_D2c.md`. Branch `lane/docs-d2c` from main 5a554e3 (P7 merged as c73e4f1). The previous
report (P5b's backups folder) and D2a's are in git history.

1. **Done (part 1, what P7 makes true).** Administration guide 1.74, new §6a and a pointer in §1, word for word in spec 10:
   what is rendered (`values.yaml`, `versions.lock`, `images.yaml`, `terraform/*.tf`) and what the platform gives
   instead; the platform's settings file; every pod as 10001; the one ReadWriteOnce volume until P8; requests and limits
   per component, development and production; the Terraform's files and the secrets each component reads, by name; images
   into ECR (`ospreyflow images push`, render, push, render again); the egress list and narrowing `managed_nets`; `make
   cp-policy-check`; *coming*; the platform team's questions (ADR-148 Amendment 1's "Open questions", plus the subnets
   and S3/STS networks its client file says the team must give).
2. **Where each claim comes from.** ADR-148 and Amendment 1; `harness/cloud_platform/{profile.yaml,platforms/client.yaml,
   __init__.py,terraform.py}`; `cli/ospreyflow/images.py`; `harness/render.py`'s arguments; and the render itself, made
   here from `tests/fixtures/cloud_platform/{development,production}.yaml` (no Docker): its workloads, copies, resources,
   `secretKeyRef`s and `envFrom`, our Secret's keys, `variables.tf`, the egress hosts and the Ingress. The request totals
   (27 GiB / 3.7 CPU, 70 GiB / 9.7 CPU) were recomputed from that render and agree with Amendment 1.
3. **Found, for the orchestrator.**
   - **The profile does not set the OFFICIAL-SENSITIVE ceiling.** Both fixtures render `OSPREY_HIGHEST_MARKING: SECRET`
     (`harness/site.highest_marking` falls back to the scheme's highest); ADR-148 decision 10's default for this profile
     is in Amendment 2's "Carried" list (P7, `lane/platform`), still open. The guide tells the operator to set
     `deployment.highest_marking: OFFICIAL-SENSITIVE` and marks the default *coming*.
   - **The OpenSearch domain is made but read by no pod** (`opensearch.tf`'s own comment; no workload reads
     `opensearch-output`). Said so in §6a.3.
   - **The render needs `PYTHONPATH=.:packages`** in `OspreyFlow_Core`: `python -m harness.render` alone fails with
     `No module named 'schemas'`, while `images.py`'s refusal tells the operator "python -m harness.render". The guide
     gives the working form; `images.py`'s words are platform's.
   - **No identity step runs on this profile until P10** (Amendment 1's "Left"), so the guide says it is not yet
     installable end to end.
4. **Decisions taken** (Prompt L; the owner may overrule).
   - *Where the guide goes.* Options: a standalone `cloud-platform-guide.md` (needs `tools/docs_pdf.py` and
     `tools/doc_site.py`, not docs' files), or a section of the administration guide. Chose **§6a of the administration
     guide**: it already holds every mode, is docs' own, builds to PDF and has spec 10's mirror, so no shared file
     changes. If a standalone guide is wanted for the client, the section moves out whole.
   - *The client's name.* The guide names no organisation (the profile's file is `client.yaml`); examples use the
     fixtures' synthetic account, namespace and networks.
5. **Waits (later parts).** P10's Entra ID claims; P9's backup and timed restore; P9b's volume-expansion and upgrade
   runbooks; P11 part 2 (the gateway by default); P12 part 2 (Laurium's service, its egress line and where it runs,
   and then the corrections to the page shared with the client, which shows Laurium inside the Conduit and workers);
   L1.9 part 2 (the connectors' IAM role and egress); P8 (the shared folders). Each is marked *coming* in §6a.7.
6. **Not run.** The build plan's D2c exit asks for every command in the guide run on kind or k3d. Docker is off on this
   Mac, so none was: the render was run in-process from the fixtures; `images push`, `helm install`, `tofu` and
   `make cp-policy-check` were not run here (P7's records ran the last).
7. **Gates (local, closed ports).** Docs tests 201 passed (`test_docs_pdf`, `test_admin_guide` among them); the four docs
   gates green. PDF: the administration guide's alone remade; the other three kept, their sources unchanged.
