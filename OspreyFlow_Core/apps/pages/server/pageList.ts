/**
 * The pages this service serves, in the route-module convention (`pages.ts`). A page's route module is added here by the
 * build that makes the page; `start.ts` hands the list to `createApp`, which checks it before the service listens.
 * The foundation shipped it empty and tested with a throw-away page (`test/fixtures/pages.ts`); the Studio's frame and its
 * Releases screen (slice IS5a) are the first two, the dataset map (slice IS3) the third and the Model step (slice IS2a) the fourth.
 *
 * It is the one table of both trees' pages (ADR-152 decision 7; slice GR2a): each module names the tree or trees that serve it
 * (`trees`, the Default tree's alone when left out), and the service mounts the ones that name the tree it was started with
 * (`OSPREY_PAGES_TREE`). Help (slice GR2a) is the first page of the GOV.UK tree, and has no Default twin yet; the Admin People list
 * (slice AD3a) is the second, the first section of the `admin` row; the alert monitoring figures (slice GR3a) are its third; trends shown
 * together (slice GR4a) is the fourth, the page of its own row, `reports-trends-shown-together`; the reader's cases and one case's page
 * (slice GR1a) are the fifth, the first part of the `cases-and-views` row; a case's drawing boards (slice GG4a) are the sixth, the first
 * part of the `drawing-boards` row, which also makes, shares and deletes a board (slice GG4c); the alert queue (slice RM1a)
 * is the seventh, and also has no Default twin; one document of a case in the reader (slice GG3b) is the eighth, the first part of the
 * `documents` row.
 * `tree-govuk/routes.yaml` lists the paths of the pages that name `govuk`, and `test/govuk/help.test.ts` and
 * `test/govuk/alert-queue.test.ts` hold the two in step.
 */
import type { PageModule } from "./pages.js";
import { adminPeople } from "./adminPeople.js";
import { alertMonitoring } from "./alertMonitoring.js";
import { boardsPage } from "./boards.js";
import { casesPage } from "./cases.js";
import { documentPage } from "./document.js";
import { studioDatasetMap } from "./datasetMap.js";
import { alertQueue } from "./alertQueue.js";
import { help } from "./help.js";
import { studioModel } from "./model.js";
import { packTrends } from "./packTrends.js";
import { studioFrame, studioReleases } from "./studio.js";

export const PAGES: readonly PageModule[] = [studioFrame, studioReleases, studioDatasetMap, studioModel, help, adminPeople, alertMonitoring, packTrends, casesPage, boardsPage, alertQueue, documentPage];
