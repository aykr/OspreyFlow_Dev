# Slice LR1 · PL9 · The sign-in library has its named entry in the licence register (a records-only change; no code)

- **Build id:** PL9 (the page service's sign-in; the library is the Glass's, so the build id is only the plan's nearest id). The owner's ruling of 20 November 2026 (slice D answers, addition 4): the two sign-in files stay in the workspace, **and their library's missing entry in the licence register is fixed now, as a small records-only change, not left as a backlog row: it is a dependency the product ships without its register entry.**
- **Dial setting:** balanced
- **Rounds limit:** 3
- **After:** nothing. It touches only `OspreyFlow_Build/spec/00_ARCHITECTURE.md` section 7 and one new test; nothing under `apps/workspace`, so it does not conflict with PL4.
- **Status of this brief:** written by the conductor on 20 November 2026.

## What

`oidc-client-ts` (declared in `OspreyFlow_Core/apps/workspace/package.json` about line 37, `^3.5.0`; installed at `OspreyFlow_Core/package-lock.json` `node_modules/oidc-client-ts`) has **no named entry in `OspreyFlow_Build/spec/00_ARCHITECTURE.md` section 7 (the licence register)**, although the Glass's `apps/workspace/src/auth/userManager.ts` (about line 2) says that section is its allowlist for what it relies on rather than hand-rolling. It ships in the product's workspace bundle.

1. **Read the register (`00_ARCHITECTURE.md` section 7, from the heading "## 7. Licence register") and the licence gate (`tools/licence_check.mjs`, `tools/licence_check.py`)** and find the shape of a named entry (the entries for other shipped npm packages, for instance the map and graph libraries and `graphology`, `zustand`). Add one in the same shape for `oidc-client-ts`: **its licence as the package's own metadata and licence file say (read the installed copy's `package.json` and `LICENSE` in `node_modules`; do not write it from memory)**, what it is used for (the Glass's OpenID Connect sign-in: `auth/userManager.ts`, `auth/oidcConfig.ts`), where it ships (the workspace bundle), and the date and "the owner, 20 November 2026" as the reason it was named. Do not change the allowlist's rules or any other entry.
2. **Do not add other packages' entries on a guess.** Report how many of `apps/workspace/package.json`'s runtime dependencies (and `apps/pages`' and `packages/*`'s) have no named entry, naming them, so the owner decides; add an entry only for `oidc-client-ts`.
3. **The test (rule 12):** one new pure test, `OspreyFlow_Build/tests/test_licence_register_names_oidc.py`, red first on main: it reads the register and `apps/workspace/package.json` and fails if `oidc-client-ts` is a declared dependency with no named entry, **and its rule is general enough to fail for any shipped runtime dependency of the workspace added later without an entry, with a short explicit list of the other currently unnamed ones, each with a stated reason and a date (so the list can only shrink)** — if that list is long, say so and keep the test on `oidc-client-ts` alone with the general rule noted as a proposal, and report the count. Plant (rule 15, the shape the code reads at its real call site): remove the new entry from a copy of the register; the test goes red; restore; green. Say which folders the test walks (a scan-map row may be needed).
4. **Citations:** the new text cites only paths that exist; run `tools.doc_citations_check`.

## Acceptance test

`OspreyFlow_Build/tests/test_licence_register_names_oidc.py` (red first on main; the planted fault red; green on the real register).

## Checks

Pure only: the new test; `test_doc_citations_check.py`; the licence checks (`tools.licence_check`, `licence_check.mjs` and their tests in `tests/licence_check/`); `ruff check .` in `OspreyFlow_Core`. Before your final report run ruff on the files you changed and the scan-map check by hand.

## Out of scope

Any code; `auth/userManager.ts` and `auth/oidcConfig.ts` (they stay where they are); other packages' entries; the allowlist's rules.
