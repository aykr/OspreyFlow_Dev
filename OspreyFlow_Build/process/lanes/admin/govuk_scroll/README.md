# GOV.UK scroll and type (the owner's screenshot of Admin › System, 15 November 2026; route row AD)

**What the owner saw.** In the GOV.UK look, Admin › System scrolled glitchily: two scrollers, the side list and the
page cut at the footer's top edge, and the top bar half off the top. The System page also set its store names, the
model column and "OspreyFlow v0.5.2" in mono, inside proportional sentences.

**Measured first.** The temporary mirror's numbers are in the orchestrator's message of 08:2xZ. The brand frame sizes
the workspace to the window less its header, and puts the footer after it (`BrandFrame.tsx`, ADR-132). So under
GOV.UK the page always scrolls by the footer's height: 995px of page in a 900px window. Scrolled to the end, the top
bar's top was at -21px. That is every GOV.UK page, not Admin alone. A second scroller appears wherever something
inside the page scrolls too: Admin's place, a drawer's body, the start overlay, the Studio's pane. Wheeling past
the inner one's end moved the page. The standard look has no footer, and nothing scrolled the page.

**The fix**, per the owner's rulings, keeping ADR-132's frame (no ADR change; DESIGN.md §11 records it):
1. **Admin under GOV.UK** (`OspreyFlow_Core/apps/workspace/src/admin/admin.css`, inside `#main-content`, where the
   real place is drawn by `AdminWithoutCase`):
   - Admin is a page that scrolls, with the document as its one scroller;
   - App's root grows to hold it, and the footer follows;
   - the side list is sticky beside the section, above 640px.
   The standard look keeps Admin's own box.
2. **Inner scrollers never move the page under GOV.UK**
   (`OspreyFlow_Core/apps/workspace/src/brand/containInnerScroll.ts`, installed by `BrandFrame`):
   - a wheel that starts in a box that scrolls, with no box on its path able to move further, is held;
   - otherwise the browser does what it always did: boxes hand off to the box around them, and a wheel over the
     page's own parts reaches the footer.
   It is a script and not `overscroll-behavior`, because in Chromium `contain` stops a scroll at a box even on an
   axis it can't scroll. Measured: a sideways table swallowed a vertical wheel, and a short list kept it from its
   drawer. The lane review found this in the first fix.
3. **The System page's fonts** (`System.tsx`, `admin.css`): the parts' names, the version, the marking ceiling and
   the converted views are in the page's face. A model's id stays in mono, through the `--mono` token
   (`.identifier`): a value to copy, as tokens.css and DESIGN.md §9 exception 3 put it.

**Harnesses** (kept): `keyboard/frame-harness`, the Glass's page as `main.tsx` and `App.tsx` draw it, with a drawer
(holding a sideways box and a short list) or the start overlay; and `keyboard/admin-harness`'s `frame=1`, the real
`AdminWithoutCase` in the real `BrandFrame`, with `serve=system`.

**Records.**
- `red_before_code.log`: the final specs against the base 0246f9b's code. 6 fail: Admin's one scroller under
  GOV.UK, the page moved by the drawer and the overlay, the names' face in all three looks. The 8 that pass on the
  base are guards: the standard look's frame and Admin box, the nested hand-offs, and the footer reached by wheel.
- `plants.py` and `plants.log`: 13 plants, each red at its own assertion, matched by message.
- `tests.log`: the gates.

**Kept, and said here** (from the lane review):
- **A short window:** on one, the sticky side list can be taller than the window (full rights, about 780px under
  GOV.UK's type), and its last items stay below until the section's end.
- **Wide tables:** under GOV.UK, Admin's place no longer scrolls sideways itself, so a table wider than the window
  widens the page.
- **Superset boards:** a wheel inside an embedded board's iframe is that document's, and the handler can't see it.
  Wheeling past a board's end can still move the page under GOV.UK.
- **Other mono words:** Admin still sets some names in mono, outside System: a role's label (Roles.tsx), a schedule's
  label (Schedules.tsx), the tips' role labels (tips.tsx), and People.tsx:763. They are the same fault class as
  System's, and a follow-up.
- **For the owner:** under GOV.UK, Admin's classification strip now scrolls away with the page, as on any GOV.UK page.
  ADR-115 decision 2 says "The strip is always shown". Whether that means always in view is the owner's to say.
- **A brand file:** `containInnerScroll.ts` and `BrandFrame.tsx` are the brand's files, not admin's; the orchestrator
  ratifies them at merge.
