# case-b · P12 part 2 · Laurium wired into the cloud-platform profile · built, 11 November 2026

**Exit.** A credential step, listed for the owner. Record: `P12p2_RED_RECORD.md`; as built: ADR-135 Amendment 9.
- **Laurium reads a real model, met** on the product's own extraction model: `qwen2.5:7b-instruct` 3 of 3 through the gateway (stack b, 18:01 UTC; `test_laurium_reads_a_real_model_live.py`), the 0.5B 0 of 3 as the control. **The client's own engine: proven at their install, 20 Nov, P12's last open item.**
- **Laurium's key scoped, never the master key, met**: no Secret in its pod (`test_laurium_render.py`, `env_file` planted red); its key made at start, older ones swept by hash, the Conduit never stopped by a failure (`test_laurium_at_start.py`, `test_laurium_start.py`, each planted red).
- **cp-policy-check on three shapes with Laurium rendered, met** (`test_laurium_cp_policy.py`, server). **Egress to the gateway alone: not yet** — P7b's rows (`P12p2_egress_paths.md`); `test_laurium_network_policy.py` strict-xfailed, failing for the right reason (read with `--runxfail`).
- The setting, cloud-platform only; **the preset Laurium (Am 5 d2), read not written**; **the review queue's extraction alone** (ruled); **Admin read-only** with Amendment 8's words, axe in three themes.

**Gates at 83b5666** (main 76980f2 + process records, a clean merge; both diffs applied; `stack_lease.sh offline case-b`; `gates/83b5666.*`): **make -k ci green.** **make test: 5 failed / 11,848 passed**: the GPU preflight (the server's); `test_admin_guide` ×2, **a real one** — the settings appendix lacked the new field, regenerated in 57789c2; two heartbeat tests, passed alone (94 of 94 with the guide's, `gates/57789c2.rerun-*`). **test-js: 1 failed**, MatrixView's budget at load, passed alone. **axe** 40 passed. **Laurium's environment**: 26 passed, 14 of 14 plants red, the xfail's 4 of 4.

**Lane-reviewer**: one round, 18 findings; all fixed, except two minors carried (friction row): `automountServiceAccountToken` (requested of platform) and two repetitions of platform's code.

**Left**: the network-policy xfails until P7b; the client's engine on 20 Nov; the owner's MORNING question on the preset.

**Commits**: 54ca87b…57789c2 and this record, on `lane/case-b-p12p2`; never pushed. **Diffs at merge**: `P12p2_platform.diff`, `P12p2_glass_models.diff`; the egress rows after P7b. **Shared hunks**: `services/api/app.py`, `services/api/review.py`.

**Requests**: correct ADR-135 Amendment 9's reservation title and mark it written; apply the two diffs. **Questions for the owner**: the preset (MORNING). **Nothing of mine is running**; no lease held.
