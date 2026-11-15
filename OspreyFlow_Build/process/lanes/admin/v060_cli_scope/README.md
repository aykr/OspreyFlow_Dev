# v0.6.0: the CLI's token scope on Entra ID (the owner's word beside #18; ADR-148 Amendment 20 decision 4)

**The gap.** `ospreyflow run` signs the orchestrator in by client credentials (`cli/ospreyflow/conduit_client.py`,
`service_token`). It sent no `scope`. Entra ID refuses that (AADSTS1002012: a client-credentials request must name a
resource's `/.default` scope), so on `cloud-platform` the command could never sign an orchestrator in.

**The fix.**
- With `OSPREY_TOKEN_SCOPE` set, the request carries it as `scope`.
- With it unset, the request is the three fields it always was: Keycloak's, unchanged.
- Entra's refusals of a scope are said in words naming the setting: none or a bare one (1002012), and another API's
  (500011). Any other refusal keeps the old words, which never show the secret.
- The install's *What it needs* (platform's runbook, in #18's `registration_and_guide.diff`) renders the
  deployment's own values: `OSPREY_TOKEN_URL` `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token` and
  `OSPREY_TOKEN_SCOPE` `api://<api_client_id>/.default`.
- The guide's §6a.7 and its `run` row in §8 say the same, in the same diff.

**Red first** (rule 15: a fake that refuses what Entra refuses). `tests/cli/test_conduit_client.py` gains an Entra
token endpoint shaped as R1's stand-in. It refuses a missing or bare scope (1002012), another resource (500011) and
a wrong secret (7000215), and grants `api://<api>/.default`.
- `red_before_code.log`: against 97dc544's client, 6 red, each at its named assertion. The wrong secret and
  Keycloak's unchanged request pass on the base, as they should.
- `plants.py` and `plants.log`: 4 plants, each red only where it must be.
  - No scope sent (main's shape).
  - An empty scope always sent (Keycloak's request changed).
  - Each of Entra's two refusals in the generic words.
- The guide and install text have two plants of their own in `../v060_i18/plants.py`, since they travel in that
  diff.

**Not measured:** a real Entra tenant. Its refusal is modelled from Microsoft's documented AADSTS1002012, as R1's
stand-in models it. R1's live run of #18 fetches its tokens with a scope and does not run the CLI.

CARRIES: closes the note #18's README carried (the orchestrator strikes it at merge).
