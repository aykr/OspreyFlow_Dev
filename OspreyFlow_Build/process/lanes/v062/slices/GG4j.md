# Slice GG4j · GG4 · A board's ceiling is never told to a reader below it (a security part; the owner, 26 November 2026)

- **Build id:** GG4 (rule 3: no field tells a reader of a marking above their clearance)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GG4a
- **A security part, SE7c's shape. Never accepted narrower. Judged by the verifier, the server and the full gate.**
  The owner's ruling (26 November 2026, about 13:40 UTC, `RULINGS.md`): GG4b's question 5 (a), "cut now as its own
  security slice". It was GG4b's row 11; GG4b no longer carries it. The id GG4j is used because CHAIN_PLAN.md reserves
  GG4f to GG4i for later board parts.
- The draft is `slices/drafts_2026-11-26/GG4b.md` (its "The ceiling" finding, question 5, row 11). The away round
  `away/GG4b` stopped before any code and built none of this (its report, question B).

## The finding (re-read on main at `3fbeb50`)

`BoardsService.open()` (`OspreyFlow_Core/services/api/boards.py` about lines 437 and 447 to 449) sends
`ceiling = await self.ceiling(board.case_id)`, and `ceiling()` / `_ceiling_of()` (about lines 179 to 193) take the
strictest marking of the case's chosen datasets **with no reader filter**. Only `markings` is cut to the reader
(`markings_up_to`, about lines 330 to 335, used at about line 448). So a reader cleared below the case's ceiling is told
the name of a marking above their clearance in `BoardOpened.ceiling` (`OspreyFlow_Core/packages/schemas/boards.py` about
line 173).

## The ruling (question 5 (a))

**`ceiling` is sent as it is only to a reader whose clearance is at or above it; to anyone else it is the highest marking
that reader may hold among the case's datasets** (the highest marking both under the case's ceiling and within the
reader's clearance), so the drawing form offers the same choices as today and the reader learns nothing above
themselves. `markings` is unchanged. The write-side checks (`check_marking` against the case's real ceiling, about lines
206 to 220, 526, 590 and 705) are **not** changed: a drawing above the real ceiling is still refused, and a reader still
cannot draw above their own clearance.

1. **Find every place a case's ceiling reaches a reader** (`BoardOpened`, any other model or route that carries it, the
   generated TypeScript, the workspace and the GOV.UK board page as readers of it). List them in your report. If any path
   other than `open()` sends it, it gets the same rule in the same change; if one cannot (a write-side refusal's words, for
   instance `above_the_ceiling`'s "this case's ceiling, {ceiling}" at about line 219), **stop and say so**: the owner
   decides what a refusal may name.
2. **No decision-record text is edited.** If the rule needs an ADR-143 or ADR-152 decision 11 change, write it as a diff
   file, `OspreyFlow_Build/process/lanes/v062/GG4j_ADR_AMENDMENT.diff`, applying cleanly to main's `spec/06_DECISIONS.md`
   (`git apply --check`, said in your report), and say so at the top of your report: the merge waits for the owner's
   approval line. If none is needed, say why in one paragraph.
3. **The conformance case first (rule 1)**, then the code.

## The table of cases (each red first on main, the planted fault at the real call site; rule 15)

| # | Case | Expected | Red with |
| --- | --- | --- | --- |
| 1 | B (cleared below the case's ceiling) opens a board | `ceiling` is B's own highest marking among the case's; `markings` as today | today's code, as it stands |
| 2 | C (cleared at the ceiling) opens it | the case's real ceiling | the reader's highest sent to everyone |
| 3 | B's answer, whatever the case's real ceiling above B is | byte for byte the same `BoardOpened` shape and `ceiling` | the real ceiling's name in any field B receives |
| 4 | B tries to draw above B's clearance | refused as today | the write check given the reader's ceiling in place of the case's |
| 5 | A drawing above the case's real ceiling | refused as today (`above_the_ceiling`) | the same |
| 6 | Every other path found in step 1 | the same rule | the rule put in `open()` alone |

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_board_ceiling_for_the_reader.py` (new, pure, through the boards service with
`tests/services/api/board_fakes.py`; rows 1 to 5). Red on main, green after. Any store-backed case goes in its own file
beside the existing ones; name it and the store it needs in your report (judged by the server's early warning and the
merge's live step).

## Checks (pure; store ports pinned to 9)

The acceptance test; `tests/services/api/test_boards.py`, `test_grading_boards.py`; `make -C ../OspreyFlow_Build
schemas-check`; `ruff check .`; `mypy packages services harness`.

## Out of scope

The drawn item's source document (GG4b); C040 (backlog row 45); any page change beyond what the generated types require
(name it if one is needed); any key or address.
