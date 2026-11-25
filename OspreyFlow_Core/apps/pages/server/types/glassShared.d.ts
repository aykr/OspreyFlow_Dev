/**
 * What the compiled service's build is told `@ospreyflow/glass-shared` exports, for the one file that imports it
 * (`server/views/helpWords.ts`; slice GR2a). `tsconfig.build.json` maps the package's name to this file, so that `tsc` checks the
 * server against these types and never reads the shared package's own source (its relative imports are written for a bundler, and
 * it uses the browser's types, which this service's build does not have). The package's real source is what runs: `apps/pages/scripts/build.mjs`
 * bundles `helpWords.ts` with it after `tsc`, so the compiled service imports no workspace package at run time.
 *
 * Only what the service uses is declared. The root `npm run typecheck` reads the real package, not this file, and
 * `test/govuk/help.test.ts` holds each declaration below to the package's own type (a type-level check that fails the
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

/*
 * For the cases page's words (`server/views/casesWords.ts`; slice GR1a): a level's name is `LEVEL_WORDS` above; a domain pack's label,
 * the core model's name and the case picker's untitled name are `investigation/cases.ts`'s, and a moment is written by
 * `time/utcStamp.ts`. `test/govuk/cases.test.ts` holds each to the package's own type.
 */
export type DomainPack = "fibo" | "niem" | "stix";
export const DOMAIN_PACKS: readonly { name: DomainPack; label: string }[];
export const POLE_LABEL: string;
export function domainLabels(domains: readonly DomainPack[]): string;
export function caseLabel(entry: { name: string; created_at: string }): string;
export function utcStampOf(iso: string): string;
