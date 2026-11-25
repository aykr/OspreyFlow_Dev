# Slice AD1e · AD1 · No database role's password is ever sent to PostgreSQL in plain text: a client-made SCRAM verifier for every role the render's database steps set (the owner's ruling of 25 November 2026)

- **Build id:** AD1 (it extends AD1c's fix for the gateway token reader to every role)
- **Dial setting:** balanced
- **Rounds limit:** 8
- **After:** AD1c (it uses AD1c's way of making the verifier and its private-database test helper). **Not started
  until AD1c has merged.**

## What

The owner's ruling (25 November 2026, `RULINGS.md`): **a security finding, never accepted narrower.** AD1c's round 6
found that the render's database steps send role passwords to PostgreSQL in plain text: psql substitutes `:'pw'` into
the SQL text, and PostgreSQL logs the full text of a statement it refuses (the bundled container's `docker logs`, a
managed server's provider log). Confirmed on main before AD1c: `harness/render.py` about line 1617
(`ALTER ROLE keycloak WITH LOGIN PASSWORD :'pw';`) and about line 1655 (`ALTER ROLE litellm WITH LOGIN PASSWORD
:'pw';`). AD1c made the gateway token reader's role take a **SCRAM-SHA-256 verifier made on the client** (in the pinned
`postgres` image) so psql, the command line and the server see only the verifier.

1. **Find every role password the render sets** in any database step, every profile, both brands (grep the render and
   the cluster chart for `PASSWORD`, `ALTER ROLE`, `CREATE ROLE`, `\password`; read each step whole). Say each in your
   report, with file and line.
2. **Each takes a client-made SCRAM-SHA-256 verifier, the way AD1c's reader does** (one shared way to make it, not a
   copy per role). No plaintext password in any SQL text sent to the server, on success or on a refused statement; no
   password on any command line or in the step's own output.
3. **On a managed PostgreSQL the steps behave as AD1c's does:** no attribute a non-superuser may not set is named;
   a step that cannot set a password says so on its error output and never stops the service that waits on it, unless
   that service cannot start without it, in which case it stops in words naming the role (never the password).
4. **The roles still log in** with their passwords after the change, on PostgreSQL 14, 15 and the pinned version.

## Acceptance test

`OspreyFlow_Build/tests/harness/test_role_passwords_never_reach_the_log.py` (new), red first: for **every** role step
the render writes, run on a private PostgreSQL started through AD1d's helper with `log_statement = 'all'` and
`log_min_error_statement = error`, as a superuser and as a managed (non-superuser, database-owning) login: after a
normal run **and** after a refused statement, no line of the server's log and nothing the step printed contains the
password. Red against today's Keycloak and gateway steps. **A census:** a test fails if the render gains a role step
the acceptance does not cover (it reads the rendered steps, not a list written by hand). The log check is shown able
to fail (a plant that puts the password in a statement turns it red: rule 15).

## Checks

The acceptance; AD1c's real-database and render tests; `tests/harness/test_render.py`, `test_reference_render.py`
(regenerate the reference render from its source if the steps change), `test_cloud_platform_render.py`;
`test_doc_citations_check.py`; `ruff check .`.

## Out of scope

Any other secret's handling; the demo (nothing changes there: no render, no migration); the owner's deployment. **If a
role's password cannot be kept out of every statement on both the bundled and a managed PostgreSQL, stop and say
why: that is the owner's.**
