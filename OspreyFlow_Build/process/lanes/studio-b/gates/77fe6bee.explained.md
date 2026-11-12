# Gates at 77fe6bee (lane/studio-b-l19p2, tree 5a7d985d635265adfac71ad8d12de129a3974470, on main 586769e), after the orchestrator's review round 1

Both shared diffs (`l1.9p2/cloud-platform-L19p2.diff` and `docs-admin-guide-L19p2.diff`) were applied in the worktree, and the admin guide's PDF was made (`tools.docs_pdf --write`), as at merge. The runs were offline on the test server through `stack_lease.sh offline studio-b`, with no lease and the closed ports.

## `make -k ci` (77fe6bee.ci.txt): exit 0

Every target passed. **cp-policy-check**, its lines unfiltered (ci.txt:2796-2801):

    development-sources.yaml: 57 manifests, 0 violation(s)
    development.yaml: 57 manifests, 0 violation(s)
    poc.yaml: 49 manifests, 0 violation(s)
    production-bedrock.yaml: 64 manifests, 0 violation(s)
    production.yaml: 64 manifests, 0 violation(s)
    cp-policy-check: 0 violation(s)

## `make test` (77fe6bee.test.txt): 2 failed, 12,250 passed, 33 skipped

Both failures are main's known ones, also in P7b's gate at 2833a66f and in this lane's at 17c243a9:
- `test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: the server has a GPU.
- `test_render_memory.py::test_opensearch_starts_with_the_rendered_heap_and_is_killed_by_one_beyond_its_memory`.

`test_docs_pdf` and `test_admin_guide` pass, and the three lane-tool tests (fixed on main at 568eaa8) pass. The branch's own suites are all inside this run, and all pass.
