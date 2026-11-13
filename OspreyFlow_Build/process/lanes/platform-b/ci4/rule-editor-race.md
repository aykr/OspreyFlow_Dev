# RuleEditor.test.tsx:98, the team sentence asserted before the team was offered, 13 November 2026

Branch `lane/platform-b-rule`, from main e778f85. Offline.

**Cause.** `SentenceBuilder.tsx` draws the "Alert goes to (team)" select before `listAlertTeams` answers
(`teams` starts as `[]`). The test set the select to `team:team-7` as soon as the select existed. When the
teams had not arrived yet, that option did not exist, jsdom left the value at "the case team", and
`whereAlertsGo` said "…seen by this case's team." This happened once in three full parallel runs here
on 13 November.

**Red.** This case's stub now answers `alert-teams` 100 ms late, which is the shape a slow real read
takes. Without the wait, the case fails every time with `Received: "Its alerts will appear in Alerts, seen
by this case's team."`, CI's text.

**Green.** The case waits for the option `Prison intel only` (`within(goesTo).findByRole("option", …)`)
before choosing it: 10 of 10 in the file. No other test picks a team (`value: "team:` appears once).

**Five full `npm test` runs in a row** (373 files in parallel, then the budget file alone): all five exit
0, every file passing.
