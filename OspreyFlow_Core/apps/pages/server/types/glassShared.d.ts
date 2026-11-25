/**
 * What the compiled service's build is told `@ospreyflow/glass-shared` exports, for the two files that import it
 * (`server/views/helpWords.ts`, slice GR2a; `server/views/packTrendsWords.ts`, slice GR4a). `tsconfig.build.json` maps the package's name to this file, so that `tsc` checks the
 * server against these types and never reads the shared package's own source (its relative imports are written for a bundler, and
 * it uses the browser's types, which this service's build does not have). The package's real source is what runs: `apps/pages/scripts/build.mjs`
 * bundles each of the two with it after `tsc`, so the compiled service imports no workspace package at run time.
 *
 * Only what the service uses is declared. The root `npm run typecheck` reads the real package, not this file, and
 * `test/govuk/help.test.ts` and `test/govuk/pack-trends.test.ts` hold each declaration below to the package's own type (a type-level check that fails the
 * typecheck when `roles.ts` changes a shape this file still says is the old one).
 */
export type PlaceKey = "glass" | "ingest" | "rules" | "admin";

export const HELP_TITLE: string;
export const PLACE_WORDS: Readonly<Record<PlaceKey, { readonly name: string; readonly says: string }>>;
export const ROLE_WORDS: Readonly<Record<string, { name: string; says: string; places: PlaceKey[] }>>;
export const LEVEL_WORDS: Readonly<Record<"viewer" | "editor" | "author", { readonly name: string; readonly says: string }>>;
export const TEAM_WORDS: {
  readonly team: string;
  readonly lead: string;
  readonly authors: string;
  readonly through: (team: string) => string;
};
export const RIGHT_WORDS: Readonly<Partial<Record<string, string>>>;
export function rightName(right: string): string;
export function rightSays(right: string): string;

/** The shared package's words for a pack and a trend (`packages/glass-shared/src/reports/packText.ts`), for the one other server file
 * that imports the package (`server/views/packTrendsWords.ts`: trends shown together, slice GR4a), bundled with it as `helpWords.ts` is. */
export type TrendFigures = import("../../../../packages/schemas/generated/TrendFigures.js").TrendFigures;
export const WITHHELD_ITEMS_SENTENCE: string;
export function formatDay(iso: string): string;
export function formatNumber(n: number): string;
export function periodKey(start: string): string;
export function periodsOf(figures: TrendFigures): string[];
export function trendSentence(figures: TrendFigures): string;
