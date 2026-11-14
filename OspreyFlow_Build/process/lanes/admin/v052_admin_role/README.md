# Route A2: the Admin role is offered only to who may give it (v0.5.2)

Studio's demo research (14 November 2026) found that anyone holding `manage_people` could give the `osprey-admin`
role. **The Conduit already refused it.** `allowed_role` (`identity_admin.py`) only checks that a role's name exists;
the giver rule is `_may_give` (`app.py`), which runs on setting roles, on inviting, and on editing a custom role.
It refuses any administration right newly given by someone who doesn't hold it (409 `beyond_your_rights`), and
`test_admin_roles_routes.py` tests it on Keycloak.

**The Glass offered the role anyway.** People and roles drew the Admin box, and every role carrying an
administration right, to every people manager, who saw the refusal only on Save. Data Engineer is one such role:
it carries Operate schedules.

**What changed** (the orchestrator's plan, 14 November):
1. People and roles offers only what the giver may give. A role the person doesn't hold yet, carrying an
   administration right the giver lacks, is drawn not offered. That covers the person rows, the custom roles and
   the invite form. One line above the table says why, for each such role: "You cannot give Admin: it carries
   Administer system and Read audit, which you do not hold." Each box not offered is described by that line. A
   role the person already holds stays offered, since taking it away gives nothing (the Conduit counts only
   rights newly given). The giver's rights reach People from Admin's own (`SCREENS`). The Glass's list of
   administration rights is held to `schemas.rights.ADMINISTRATION_RIGHTS` by `tests/test_admin_giver_rights.py`.
2. On the Entra backend, a people manager alone is refused `osprey-admin` and `right:administer_system`, and an
   administrator is allowed (`test_entra_people.py`, rule 4). The route is shared, so this holds on main already;
   the plant that removes `_may_give` shows it red.
3. Rights named in words: folded into route W's ADR-148 Amendment 19 by the orchestrator.

**Records.**
- `red_before_code.log`: A2's tests against main's code. The two Glass cases that withhold fail. The two that
  check nothing is withheld wrongly pass by design, and the plants show them red.
- `plants.py` and `plants.log`: 7 plants, each red only in the tests it must fail.

**Gates at the head:**
- vitest for admin passes (214), and tsc and eslint are clean.
- The keyboard and look specs pass for Admin (77), and axe passes on every Admin harness state (112).
- The touched test files pass (36 in `test_admin_giver_rights.py` and `test_admin_sections.py`, 73 in
  `test_entra_people.py`).
