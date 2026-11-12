# case-b · P12 part 2 · Laurium's egress paths, for P7b's `egress.paths` (platform)

Platform's per-workload egress design (P7b, ADR-148 Amendment 5, relayed by the orchestrator on 11 November):
one Calico policy per source workload from `harness/cloud_platform/profile.yaml`'s `egress.paths`, only
`default.ospreyflow-allow-dns` on `all()`. Laurium's rows, to go in that file once P7b has written it (a diff
against P7b's file is sent then; there is no `egress.paths` to diff against before):

```yaml
egress:
  paths:
    laurium: [litellm]          # the gateway alone; DNS is allow-dns's
    api: [..., laurium]         # appended to platform's own list
```

**Applied** in `P12p2_platform.diff` against eec25d1 (12 November). Rendered only when Laurium is a workload (`models.extraction_engine: laurium`): a path naming a workload not
rendered must render nothing (asked of platform: the row's own guard, or the render's).

`tests/harness/test_laurium_network_policy.py` reads Helm's output in Calico's order: Laurium reaches litellm on
4000 and DNS, and nothing else, not ArcadeDB, ClickHouse, a managed store or an outside host. Strict-xfailed until
P7b and these rows land (it fails today: `allow-egress` admits Laurium to everything), so it fails the day it
passes and the mark is taken off. **Ingress** (only api reaches Laurium: no worker holds a model) is P7b's, derived from the same rows
(the orchestrator's ruling).
