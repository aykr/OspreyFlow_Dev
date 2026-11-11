# docs lane · D2c part 1, the `cloud-platform` profile (administration guide §6a) · 11 November 2026

Branch `lane/docs-d2c` on main 5a554e3: b24380c (built), then the two reviews' fixes (head: see `git log`). Nothing running.
- **Every sentence traceable, unbuilt marked *coming*: met.** §6a 1.75 (spec 10 word for word) written from ADR-148 Am 1–2,
  `harness/cloud_platform/`, `harness/cluster.py`'s blanks, `cli/ospreyflow/images.py` and a render of the guide's own example.
- **Commands run: the render ones, met** (`gates/d2c-p1-guide-commands.txt`: the example's renders, the push's dry run, and
  the refusals without `map:`, without `terraform/` and before a push). Helm, tofu, the push and cp-policy-check: not here
  (Docker off, no helm); P7b's kind run.
- **Docs gates and `test_docs_pdf`: met** (`gates/d2c-p1-docs-tests.txt`: 201 passed, four gates green). The admin PDF alone remade.
- **Version rows:** 1.74 (part 1) and 1.75 (the reviews' fixes). Friction row `friction/2026-11-11-docs-d2c-cloud-platform.md`.
- **Decision taken:** §6a of the administration guide, not a standalone guide (that needs `tools/docs_pdf.py` and `doc_site.py`,
  not docs' files). The owner may overrule; the section moves out whole.
- **For platform (code, P7b):** (1) the profile does not set the OFFICIAL-SENSITIVE ceiling (Am 2's carry); (2) `write()` does not
  make `terraform/`, so a first render into a new folder fails; (3) an unpinned render's plan copies third-party images by tag,
  never exercised by the tests' stand-in resolver; (4) `images.py:28-29` says `python -m harness.render`, which needs
  `PYTHONPATH=.:packages`; (5) no identity step on this profile until P10; (6) OpenSearch made, read by no pod. Each is in the
  guide as it stands.
- **Waits:** P10 (Entra ID), P9 (backups and restore), P9b (runbooks), P11 part 2, P12 part 2 (Laurium, where it runs, and the
  corrections to the page shared with the client), L1.9 part 2, P8: each *coming* in §6a.7.
- **No questions for the owner.** The installed `ospreyflow` on this Mac does not import (`httpx`); the worktree's CLI was used.
