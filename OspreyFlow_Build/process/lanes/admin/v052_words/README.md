# Route W: the People section's name, and Entra's refusal in words (ADR-148 Amendment 19)

The orchestrator's order, 14 November 2026 (v0.5.2, from docs' sweep):
1. The Conduit's refusals and the schema said "Admin › People", where the section is "People and roles". Every
   user-facing copy now uses the section's real name, and the test reads it from the one place the side list takes
   it (`apps/workspace/src/admin/sections.json`).
2. `entra_people.py`'s refusal of a value Entra sends named raw field names. It now says them in words, as the
   Guests form does.

**What changed.**
- **One constant.** `principal_auth.PEOPLE_SECTION` ("Admin › People and roles") is used in every refusal and log
  line that names the section:
  - principal_auth (guests, an unset value, an owner's unset value);
  - scheduler, list_schedule and rule_schedule (an owner not held; the people store not read);
  - monitor_schedule (a log line);
  - watch_status (the stopped reason).
- **Amendment 16's sentence shape** becomes "is not held in …" and "the people store behind … could not be read".
- **Everywhere else the name appears:**
  - the schema's descriptions, and so the generated `AddPersonInput.ts`, `OspreyConfig.ts` and `SignInKind.ts`;
  - a route's OpenAPI description (`app.py`'s sign-in route);
  - the runbook;
  - the short "in People" refusals and the Glass's own words for them;
  - both guides (admin 2.12, user 1.61; versions set at merge) and spec/10.
- **The Entra refusal** says the values Entra sends in words, with a verb that agrees, and then which are set
  here. For example: "Here a person's unit comes from Entra ID, and is changed there. Their clearance and
  handling codes are set here, with Access." The admin guide's §9 quotes it.

- **A right named in a refusal** is named as the screens name it (`schemas.rights.right_name`, held to the Glass's
  `rightName`): "you cannot give a right you do not hold: Administer system", and the forbidden pair's words. This
  is A2's point 3, folded into Amendment 19 by the orchestrator.

**Records.**
- `red_before_code.log`: the test file at the head, against main's code. 10 of its 11 cases fail. The 11th, the
  scan's self-test, plants each shape the scan reads (a refusal, an f-string, an implicit concatenation, the ASCII
  arrow, a route's docstring, a guide name split over a line, a Glass string) and what it must leave alone (a
  comment, a module or helper docstring, a version row, the new name).
- `carries_done.diff`: docs' two CARRIES rows struck as done. They aren't on main's CARRIES.md yet, so the
  orchestrator applies it at merge.
- `tests.log`: the affected directories on the branch and on main, and their difference.

Kept, and said here:
- principal_auth's owner sentence "an administrator has not set unit and handling codes for this person in …: it
  runs at its next slot once an administrator has set it" is a comma splice, with "it" for two values. It is
  platform's sentence (ADR-148 Amendment 16), and this step changes only its section name.
