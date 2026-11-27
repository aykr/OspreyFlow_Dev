/**
 * The pages this service serves, in the route-module convention (`pages.ts`). A page's route module is added here by the
 * build that makes the page; `start.ts` hands the list to `createApp`, which checks it before the service listens.
 * The foundation shipped it empty and tested with a throw-away page (`test/fixtures/pages.ts`).
 *
 * It is the one table of both trees' pages (ADR-152 decision 7; slice GR2a): each module names the tree or trees that serve it
 * (`trees`, the Default tree's alone when left out), and the service mounts the ones that name the tree it was started with
 * (`OSPREY_PAGES_TREE`). `tree-govuk/routes.yaml` lists the paths of the pages that name `govuk`, and `test/govuk/help.test.ts`
 * (HP9) holds the two in step. Which slice made a page, and where it sits in its tree, is said by the page's own module and
 * scenario, not here.
 *
 * Git merges this file with its union merge (the repository's `.gitattributes`), so two pages built side by side both stay.
 * That is safe only while a page adds lines and edits none: its import, on a line of its own, and its module, on a line of its
 * own in `PAGES`. Nothing here counts or names the pages. `tests/glass_trees/test_page_lists_merge.py` checks what union could
 * leave (a page listed or imported twice, one listed and not imported), and the type check holds the rest.
 */
import type { PageModule } from "./pages.js";
import { adminPeople } from "./adminPeople.js";
import { alertMonitoring } from "./alertMonitoring.js";
import { boardsPage } from "./boards.js";
import { casesPage } from "./cases.js";
import { studioDatasetMap } from "./datasetMap.js";
import { alertQueue } from "./alertQueue.js";
import { help } from "./help.js";
import { studioModel } from "./model.js";
import { packTrends } from "./packTrends.js";
import { studioFrame, studioReleases } from "./studio.js";

export const PAGES: readonly PageModule[] = [
  studioFrame,
  studioReleases,
  studioDatasetMap,
  studioModel,
  help,
  adminPeople,
  alertMonitoring,
  packTrends,
  casesPage,
  boardsPage,
  alertQueue,
];
