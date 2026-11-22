/**
 * The pages this service serves, in the route-module convention (`pages.ts`). A page's route module is added here by the
 * build that makes the page; `start.ts` hands the list to `createApp`, which checks it before the service listens.
 * The foundation shipped it empty and tested with a throw-away page (`test/fixtures/pages.ts`); the Studio's frame and its
 * Releases screen (slice IS5a) are the first two.
 */
import type { PageModule } from "./pages.js";
import { studioFrame, studioReleases } from "./studio.js";

export const PAGES: readonly PageModule[] = [studioFrame, studioReleases];
