# The Glass page's panels and menus on the page's type scale (the owner's exception, 14 November 2026)

The owner saw it in the GOV.UK look: the right-hand panel's view names, its "Private" tags and its links far larger
than the rest of the page, and the panel that opens from More views looking wrong the same way.

**The cause, measured** (views-harness at 1280px). The workspace keeps its 13px base under GOV.UK
(`OspreyFlow_Build/spec/design/DESIGN.md` §9 exception 1; `tokens.css` remaps GOV.UK's scale only for the welcome,
home and Admin pages). Two things broke that:
- **A panel drawn with GOV.UK Frontend's classes took the Design System's own sizes.** In the saved views panel the
  names were 19px bold, the tags 19px and the links 16px, beside the drawer's 13px case tree.
- **A menu that sets no size inherited the row it opens from.** Under GOV.UK the case line is a notification banner
  at 19px by design, so the case switcher's New case form drew its label and options at 19px.

Also, in every look: a panel heading drawn as `h2.label` or `h3.label` took the browser's size (19.5px or 15.21px),
since `.label` sets no size. That covers the saved views panel's "Views in this case" and the Save as a view form.

**The fix: CSS only, by container and GOV.UK's own classes** (`OspreyFlow_Core/apps/workspace/src/design/panelType.css`,
imported by `primitives.css`; recorded in DESIGN.md §11). The containers are a drawer, a canvas menu, the top bar's
and the case line's menus, the strip over the canvas, and the Save as a view form. Each:
- sets the page's body size itself;
- draws a `.label` heading at the body size;
- under GOV.UK, gives GOV.UK Frontend's type classes the page's tokens: body, headings, links, buttons and fields at
  `--fs-13`; small text, hints, captions and tags at `--fs-12` (§9's floor).

The case line itself, the GOV.UK-scale pages, and GOV.UK's header, footer and phase banner keep their sizes.
tokens.css is unchanged. case and case-b own the markup; the rule selects by neither lane's component classes.

**The spec** (`OspreyFlow_Core/apps/workspace/keyboard/glass-panels-look.spec.ts`) has nine panels, each in the dark,
light and GOV.UK looks. It reads the scale from the page's body:
- text at `--fs-12` or `--fs-13`; a tag, meta or caption may also be `--fs-11`; a heading at `--fs-12`, `--fs-13` or
  `--fs-16`;
- a container it cannot find fails the case;
- the saved views case waits for the views themselves, not the loading state;
- the narrow More case checks that Build a report is among what it measures.

**Kept, and said here.**
- The owner's second complaint, the panel from More views, is not reproduced in any harness: More's menu measures on
  the scale on main, in the Glass's frame and folded at 760px. Its menu now sets the body size itself, so it can't
  inherit a larger row, and the menu cases are shown red by a synthetic plant. If the owner meant another panel, it
  needs naming.
- The search results page (`SearchResults.tsx`) fills the Glass's main area with GOV.UK's own classes at GOV.UK's
  size. It's a page, not a panel, so it is outside this order.
- The narrowed heading rule (`.label` headings only): a wider rule on every bare h2–h6 in a drawer or menu made
  `keyboard/ingest-studio.spec.ts`'s expert-mode save miss its 5s wait. That was 3 of 3 runs with it and 4 of 4
  without, the file alone, on this Mac, with no lease. The cause wasn't found.
- `views.css`'s comment on `.case-views__link` ("GOV.UK's small type, 16 px") is now always overridden. That file is
  case's, so the note is for them.

**Records.**
- `red_before_code.log`: the spec at the head with the sheet unloaded, which is main's CSS. 8 of 27 cases fail: the
  saved views panel and the Save as a view form in all three looks, the strip under GOV.UK, and the New case form
  under GOV.UK. The other 19 pass on main by design, since nothing was off the scale there.
- `plants.py` and `plants.log`: 9 plants, each red only in the cases it must fail. Seven are in a real shape. Two are
  synthetic, an off-scale menu item and an off-scale drawer body, and show the cases that pass on main can fail.

**Gates at the head:** see `tests.log`.
