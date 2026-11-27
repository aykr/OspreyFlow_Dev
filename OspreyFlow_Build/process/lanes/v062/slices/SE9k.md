# SE9k: a site's grid cells take the site's owning unit and originator

**Security part, Conduit** (the owner's ruling of 27 November 2026, about 13:45 UTC; RULINGS.md), from SE9j round 1's finding. It is cut before RL2. It does not wait for SE9j.

## The finding

`OspreyFlow_Core/recipes/site_grid.yaml` line 27 writes every grid cell and polygon with `handling: {..., originator: unit-1, owning_unit: unit-1}`, whichever unit owns the site. `sites.py` keeps the site's `owning_unit` from the uploader's `principal.org_unit`, and every site route reads through it. But the grid that `set_site_grid` (`services/api/app.py`, about line 10304) draws through the recipe engine is owned by `unit-1`. So in a deployment with more than one unit, a site's cells are owned and originated by a unit that may not be the site's.

## The rule

Each cell `Location` and its polygon written by a site's grid carry the site's own `owning_unit` as both owning unit and originator. They are set in the draw's own run defaults, so no cell is written as `unit-1` and changed afterwards. The classification and handling code stay as they are (SE9j changes the classification). A redraw writes the same unit. Say what an existing grid drawn as `unit-1` reads as, and change nothing silently: a later redraw writes the right unit, and nothing is backfilled.

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_site_grid_owning_unit.py` (new, pure). A site owned by a unit other than `unit-1` has its grid drawn, and every cell and polygon written carries that unit as owning unit and originator. **Red first:** with today's recipe default at its real call site (rule 15), the test fails on `unit-1`. An access-control case (rule 4): a reader of another unit is not sent the cells.

## Out of scope

The site's marking (SE9j), and any change to who may draw a grid or how cells are matched on a redraw.
