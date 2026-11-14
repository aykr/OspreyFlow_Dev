# The Guests form's words under the administrator fallback (ADR-148 Amendment 17, a line added)

Queued on 4b's merge, until platform-b's 4c (ADR-148 Amendment 15) landed. Branch `lane/admin-guest-words`, from main.

Admitted, a guest signs in as anyone does. Where the deployment sets a value itself (`administrator: true`), a
guest's value is the one set with **Access** in People, never their token's. The form used to say "the same
clearance, unit and codes from their token" in every case. It now says which values come from People and which
come from the token, built from what `GET /v1/admin/sign-in` serves as `administrator_sets` (`guestAdmissionWords`
in `sections/People.tsx`).

| File | What it is |
| --- | --- |
| `form-words-red.log` | `PeopleEntraAdministrator.test.tsx`'s *Guests words* before the change. All 8 subsets of `administrator_sets` red, served sorted as the Conduit sorts them. The empty set is red only for the rewording "codes" → "handling codes" |
| `backend-plants.log` | `test_entra_guests.py::test_an_admitted_guest_takes_a_value_the_deployment_sets_from_people_never_from_their_token`, against two plants. In the first, a guest skips the values set here: it is red, but at `principal_auth`'s own assert, which refuses that state first. In the second, a guest's token clearance is used where the deployment sets it: red at the test's own assertion |

Checks after the change, offline:
- vitest 3462 passed;
- tsc clean, eslint clean;
- the guide, guest and administrator-access pytest files: 233 passed;
- `adr_reservations_check` clean.

Administration guide §6a.7 gains a sentence (version 2.09, set at merge), and spec/10 is mirrored.
