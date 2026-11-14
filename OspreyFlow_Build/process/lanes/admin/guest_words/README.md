# The Guests form's words under the administrator fallback (ADR-148 Amendment 17, a line added)

Queued on 4b's merge, until platform-b's 4c (ADR-148 Amendment 15) landed. Branch `lane/admin-guest-words`, from main.

Admitted, a guest signs in as anyone does. Where the deployment sets a value itself (`administrator: true`), a
guest's value is the one set with **Access** in People, never their token's. The form used to say "the same
clearance, unit and codes from their token" in every case. It now says which values come from People and which
come from the token, built from what `GET /v1/admin/sign-in` serves as `administrator_sets` (`guestAdmissionWords`
in `sections/People.tsx`).

| File | What it is |
| --- | --- |
| `form-words-red.log` | The *Guests words* test as first written, before the change: all 8 subsets red |
| `ui_plants.py`, `ui-plants.log` | The words' plants, after the lane review. Each is planted alone in `People.tsx`, and the tree is restored from git. Red only when the tests that fail are exactly the ones the plant must fail: the verb chosen by count alone, the old token clause kept, the values listed in served order. 3 of 3 red |
| `plants.py`, `backend-plants.log` | The backend plants, in `principal_auth`, each red only when every failure stops at the assertion it names: a guest's token values kept where the deployment sets them; a guest refused in words of its own when a value set here is unset. 2 of 2 red, each across the 3 values. An earlier plant, a guest skipping the values set here, was caught first by `principal_auth`'s own assert (line 874), not by the test, so it does not count |
| `lint.log`, `vitest-full.log`, `pytest.log` | The gates, each naming the head it ran at |

**The lane review** (14 November) found the following, all fixed:
- the verb chosen by count, so handling codes alone read "is";
- a test of part-sentences that a wrong verb or a longer list passed;
- the backend test held through `principal_from_claims` alone, for clearance alone, its refusal half never shown red;
- logs with no head;
- the module docstring and point 3's lead still saying "from their token" without exception.

The words now choose the verb by the noun. People's own words (`entraPeopleWords`) share the list, in `EVERY_FIELD`'s
order. Every sentence is asserted whole. The backend test runs through `resolve_principal` for each value.

**Seen, not changed** (principal_auth is the platform lane's): its refusal says "your handling codes has not been set".
