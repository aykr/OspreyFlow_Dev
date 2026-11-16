# v0.6.0 stage 4 · Superset's roles, probed on R1 (16 November 2026)

On the package test's install of candidate `38fafb8` (R1's kind cluster on the test server, synthetic data only,
nothing of any demo's), at the owner's ruling after row 3 found a Reports Viewer saving a dashboard. Read-only
but for each person's own test chart and one synthetic mart row, planted and removed.

**What was asked:** can a Reports Viewer's own chart, over a dataset it reaches, return rows beyond its
row-level access? Compared with a builder's and an administrator's reads of the same data.

**How:** the mart (`osprey_reports.figures`) held the report sync's rows for `r1-board`'s dashboard identity
(`dddddddd-eeee-4fff-8000-000000000002`) and one row planted for another identity counted at SECRET
(`r1-another-identity-counted-at-secret`, the dashboards check's own control, removed afterwards: 0 left). In R1's
api pod, beside `superset_pod.py` and with each person's Superset session: the administrator's dataset and chart
on the mart; that chart's data read by each person; then the builder and the reader each made their own chart
on the dataset and read it, and asked the dataset's rows directly (`probe_reader.py`, beside this file).

**Found** (the probe's output, below):

- **The Reports Viewer (Superset's Gamma then) reads nothing of the mart**: its own chart was saved (201), but
  every read was refused 403: its own chart's data, the administrator's chart's, and the dataset asked directly.
  Gamma holds no access to the mart's schema. So the breach was writes alone: fixed in v0.6.0 by `OspreyReader`
  (`OspreyFlow_Core/deploy/superset/osprey_roles.py`, `tests/test_superset_reader_role.py`).
- **A builder (Superset's Alpha) reads the whole mart** in their own session: both identities' rows, through the
  administrator's chart, their own chart and the dataset directly, whatever their level on the other identity's
  case or its clearance. The mart's row-level rule is carried by the guest token alone (the embedded path).
  Stated in v0.6.0 and scoped in v0.6.1: ADR-148 Amendment 21. The dashboards check records it on every run
  (`RECORD a builder's own Superset session reads the whole mart …`).
- The administrator reads the whole mart, as Admin does by design.

Also read from the running image: Superset's Gamma holds `can_write` on Dashboard and Chart (and twelve more
writes: `tests/fixtures/superset/gamma_permissions.txt`, its whole table as `superset init` makes it in this
image), and Flask-AppBuilder 5.0.2 adds `AUTH_USER_REGISTRATION_ROLE` to every account at every sign-in
(`_oauth_calculate_user_roles`).

## The probe's output

    INSERT 0 1
    mart dashboards: dddddddd-eeee-4fff-8000-000000000002, r1-another-identity-counted-at-secret
    {
     "admin chart": {
      "status": 201,
      "dataset": 1,
      "chart": 1
     },
     "chartdata session admin@r1.test": {
      "status": 200,
      "dashboards": [
       "dddddddd-eeee-4fff-8000-000000000002",
       "r1-another-identity-counted-at-secret"
      ]
     },
     "chartdata session builder@r1.test": {
      "status": 200,
      "dashboards": [
       "dddddddd-eeee-4fff-8000-000000000002",
       "r1-another-identity-counted-at-secret"
      ]
     },
     "chartdata session reader@r1.test": {
      "status": 403
     },
     "own chart builder@r1.test": {
      "made": 201,
      "said": "{\"id\":2,\"result\":{\"datasource_id\":1,\"datasource_type\":\"table\",\"params\":\"{\\\"viz_type\\\": \\\"table\\\", \\\"groupby\\\": [\\\"dashboard\\\"], \\\"metrics\\\": [\\\"count\\\"], \\\"row_",
      "read": {
       "status": 200,
       "dashboards": [
        "dddddddd-eeee-4fff-8000-000000000002",
        "r1-another-identity-counted-at-secret"
       ]
      },
      "dataset direct": {
       "status": 200,
       "dashboards": [
        "dddddddd-eeee-4fff-8000-000000000002",
        "r1-another-identity-counted-at-secret"
       ]
      }
     },
     "own chart reader@r1.test": {
      "made": 201,
      "said": "{\"id\":3,\"result\":{\"datasource_id\":1,\"datasource_type\":\"table\",\"params\":\"{\\\"viz_type\\\": \\\"table\\\", \\\"groupby\\\": [\\\"dashboard\\\"], \\\"metrics\\\": [\\\"count\\\"], \\\"row_",
      "read": {
       "status": 403
      },
      "dataset direct": {
       "status": 403,
       "dashboards": []
      }
     }
    }
    DELETE 1
    removed: 0 left
