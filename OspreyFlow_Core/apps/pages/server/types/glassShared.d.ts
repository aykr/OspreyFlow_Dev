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
// The generated `TrendFigures` (`packages/schemas/generated/TrendFigures.ts`), written out here rather than imported: an import would put
// that source file into this build's program and `tsc` would write it out beside itself. `test/govuk/pack-trends.test.ts` holds this
// shape to the package's own, both ways (but for the two lists the page never reads), so a field the schema adds, drops or changes fails
// `npm run typecheck`.
export type TrendFigures = {
  definition: {
    title: string;
    source?: "events" | "alerts";
    // The two bounded lists the page never reads, as the empty list each may be (their own types are tuples up to 12 and 5 long).
    event_types?: [];
    measure?: "count" | "sum";
    measure_field?: string | null;
    interval?: "week" | "month";
    weeks?: number;
    group_by?: string | null;
    filters?: [];
    [k: string]: unknown;
  };
  result: {
    interval: "week" | "month";
    measure: "count" | "sum";
    points: { period_start: string; series?: string | null; value: number; [k: string]: unknown }[];
    series?: string[];
    total: number;
    events: number;
    unvalued?: number;
    classifications?: string[];
    handlings?: { classification: string; handling_code: string; owning_unit: string; originator: string; [k: string]: unknown }[];
    [k: string]: unknown;
  };
  as_of: string;
  window_start: string;
  marking?: string | null;
  [k: string]: unknown;
};
export const WITHHELD_ITEMS_SENTENCE: string;
export function formatDay(iso: string): string;
export function formatNumber(n: number): string;
export function periodKey(start: string): string;
export function periodsOf(figures: TrendFigures): string[];
export function trendSentence(figures: TrendFigures): string;
