/**
 * The pages this service serves, in the route-module convention (`pages.ts`). A page's route module is added here by the
 * build that makes the page; `start.ts` hands the list to `createApp`, which checks it before the service listens.
 * Empty until the first page (the Studio's frame, slice IS5a) is built: the foundation ships no page of its own, and its
 * tests use a throw-away one (`test/fixtures/pages.ts`).
 */
import type { PageModule } from "./pages.js";

export const PAGES: readonly PageModule[] = [];
