# Route A2: a role is offered only when the giver may give it (v0.5.2)

Studio's demo research (14 November 2026) found that anyone holding `manage_people` could give the `osprey-admin`
role. **The Conduit already refused it.** `allowed_role` (`identity_admin.py`) only checks that a role's name exists.
The giver rule is `_may_give` (`app.py`), which runs on setting roles, on inviting, and on editing a custom role. It
refuses a change that newly gives an administration right its giver doesn't hold: the rights of the roles as they
would stand, less those the person's roles give now (409 `beyond_your_rights`). `test_admin_roles_routes.py` tests
it on Keycloak.

**The Glass offered the role anyway**, to every people manager, who saw the refusal only on Save. Data Engineer
was offered the same way, since it carries Operate schedules.

**What changed** (the orchestrator's plan, 14 November; reworked after the lane review):
1. **People and roles decides each change as the Conduit does.** Each role box, each custom role, the Super user
   preset (whole) and each role of an invitation is decided by the rights it would newly give, over everything the
   person holds now, single grants and older roles included. So:
   - a right the person already holds another way gives nothing new, and the role is offered;
   - a box already ticked can be unticked;
   - a box not offered stays in the Tab order (`aria-disabled`) and refuses the change.
   Each box not offered says its own why, in roles and rights, never people, outside its label (WCAG 2.5.3): "You
   cannot give Admin here: it would give Administer system and Operate schedules, which you do not hold." One line
   above the table states the rule. The giver's rights reach People from Admin's own, and follow the token when
   it renews. The Glass's list of administration rights is held to `schemas.rights.ADMINISTRATION_RIGHTS` by
   `tests/test_admin_giver_rights.py`.
2. **On the Entra backend**, a people manager alone is refused `osprey-admin` and `right:administer_system`, with
   the refusal naming the right as the screens do (W's Amendment 19, now on main). An administrator is allowed
   (`test_entra_people.py`, rule 4).
3. **Rights named in words**: in W's Amendment 19, already merged.

**Kept.**
- While the giver's rights or the roles' catalogue are not yet read, every role is offered, and the Conduit
  refuses what it must.
- The Glass's list of administration rights is a copy held by a test, not served by the Conduit. Serving it
  (from `/v1/admin/roles`) is the next step if a second screen needs it.

**Records.**
- `red_before_code.log`: A2's tests against the base. Note what is said at its foot.
- `plants.py` and `plants.log`: 10 plants, each red only in the cases it must fail. They cover:
  - the giver ignored; a right held already counted as new; the giver's own rights ignored;
  - a box not offered still taking the change;
  - the preset given whatever it carries;
  - the invitation unchecked;
  - the giver's rights never reaching People, or read only once;
  - the Conduit without `_may_give`;
  - the Glass's list short of one right.
- `registry-A2.diff`: `read-why-a-role-is-not-offered-by-keyboard` in `actionRegistry.ts`, the orchestrator's file.
  `keyboard/admin.spec.ts` proves it: Tab reaches a box not offered, its reason is read, and Space leaves it.

**Gates at the head:**
- vitest admin and help: 226.
- tsc and eslint: clean.
- Keyboard and look specs for Admin: 78 (with the registry diff applied).
- axe on every Admin harness state in the dark, light and GOV.UK looks: 112. The manage_people states draw the
  boxes not offered.
- Python: 232, the giver, roles, custom roles, sections and words tests.
