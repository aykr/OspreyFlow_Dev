# Slice CO2b · CO2 · A test's token is minted when the test runs, so its result cannot depend on how long the suite takes

- **Build id:** CO2 (the fault is in CO2's test; slice id CO2b).
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing. **The owner's order (20 November): ahead of everything except a PL4 slice and SE5.** It touches no file under apps/workspace.
- **Status of this brief:** written by the conductor on 20 November 2026 on the owner's word, after he read GitHub's logs. **The cause is known; do not rerun the red GitHub runs and write no stop.**

## What the owner found

Both red GitHub runs (44730215386 and 44739376824) failed the same test, both parameters:
`OspreyFlow_Build/tests/services/api/test_auth_entra_pages.py::test_a_token_from_a_realm_client_without_the_audience_mapper_is_refused`,
with `PrincipalResolutionError: token rejected: Signature has expired`. GitHub's suite took 40 and 49 minutes; on the Mac the suite is fast, so it passes. The conductor read the test: its `@pytest.mark.parametrize("claims", [default_claims(aud="account", azp="osprey-pages"), default_claims(azp="osprey-pages")], ...)`
calls `default_claims` (OspreyFlow_Build/tests/conftest.py, about lines 253 to 266, which sets `iat` to now and `exp` to now plus 300 seconds) **while the module is imported at collection**, so the token's life starts before the first test runs and has ended by the time this test runs on a slow suite.
It is a fault in the test, not in the product and not a flake.

## What

1. **Red first, by planting the delay (the owner):** move the clock past the token's life before the assertion and show **today's test failing with the expiry message.** Design it so the proof stands in the suite: for example a conftest switch (an environment variable such as a clock skew in seconds that advances `time.time` after collection and before each test) and a new test file that runs the auth test modules in a subprocess with a skew of more than 300 seconds and asserts they pass; it must be red on main with "Signature has expired" and green after. Say in the test header which test fails if the fault returns (rule 12).
2. **The fix:** each case mints its token when it runs: parametrise with the **overrides** (or a factory, `lambda: default_claims(...)`) and call `default_claims` **inside the test**, never at import. (Or fix the clock for the test.) The result must not depend on how long the suite takes.
3. **Check every other test that signs a token or sets an expiry once per module or session, and list what you find in your report; fix the ones with the same flaw.** Where to look: the Conduit's auth tests (`OspreyFlow_Build/tests/services/api/test_auth*.py`, `tests/conftest.py`'s `sign_token`, `keypair`, `jwks_url` fixtures and any `scope="module"` or `scope="session"` token), every `default_claims(` or `sign_token(` call inside a `parametrize` decorator, a module-level constant or a module/session fixture across `OspreyFlow_Build/tests` (about 41 files use them), **PL9a's and PL10's new tests** (`OspreyFlow_Core/apps/pages/test/server/`: the fake identity provider's tokens, session lifetimes and cookie expiries; the Node tests use their own clock), and the pages service's sign-in/renewal tests. For each: the file, the line, whether the lifetime can end during a slow suite, and your fix or why it is safe.
4. **A standing guard:** a pure test that fails when a `default_claims(` or `sign_token(` call (or any `exp`/`iat` set from `time.time()` at import) appears in a `parametrize` decorator, at module level or in a module/session-scope fixture of a test file, with the allowed exceptions listed with their reason. Red first: it must name the sites it finds on main; green after your fix. **It walks the test tree: say in your report which folders it walks** (the conductor writes its scan-map row).
5. **Not in scope:** the product's token handling; the lifetimes the product sets (300 seconds is the test default).

Binding: process/CLAUDE.md rules 11, 12, 15; British English. No file under apps/workspace. You do not edit the Core Makefile, `ci.yml` or any CLAUDE.md.

## Checks

Pure only (`ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9` in every command): the auth test modules (`test_auth.py`, `test_auth_entra_pages.py`, `test_auth_entra_claims.py` and the neighbours that use `sign_token`), the new tests, ruff on every changed file in OspreyFlow_Core and the scan-map check. **Before your final report run by hand the cheap checks the conductor will run again before the merge** (ruff on changed files, the scan-map check for the guard test). A merge attempt costs 25 minutes.
