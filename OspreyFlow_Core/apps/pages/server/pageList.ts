/**
 * The pages this service serves, in the route-module convention (`pages.ts`). A page's route module is added here by the
 * build that makes the page; `start.ts` hands the list to `createApp`, which checks it before the service listens.
 * The foundation shipped it empty and tested with a throw-away page (`test/fixtures/pages.ts`); the Studio's frame and its
 * Releases screen (slice IS5a) are the first two, the dataset map (slice IS3) the third and the Model step (slice IS2a) the fourth.
 *
 * It is the one table of both trees' pages (ADR-152 decision 7; slice GR2a): each module names the tree or trees that serve it
 * (`trees`, the Default tree's alone when left out), and the service mounts the ones that name the tree it was started with
 * (`OSPREY_PAGES_TREE`). Help (slice GR2a) is the first page of the GOV.UK tree, and has no Default twin yet.
 * `tree-govuk/routes.yaml` lists the paths of the pages that name `govuk`, and `test/govuk/help.test.ts` holds the two in step.
 */
import type { PageModule } from "./pages.js";
import { studioDatasetMap } from "./datasetMap.js";
import { help } from "./help.js";
import { studioModel } from "./model.js";
import { studioFrame, studioReleases } from "./studio.js";

export const PAGES: readonly PageModule[] = [studioFrame, studioReleases, studioDatasetMap, studioModel, help];
