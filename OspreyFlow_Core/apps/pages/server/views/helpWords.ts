/**
 * The Help page's words and the view it is drawn from (slice GR2a; ADR-152 decisions 6 and 12; FUNCTIONS row `help`).
 *
 * What the page says about the places, the roles, the levels, teams and Authors and each right is `roles.ts`'s, in the shared
 * package (`packages/glass-shared/src/help/roles.ts`), imported and never written again here: the React Help page, the tips in
 * Admin and the Ingest Studio, and the guides take their wording from the same place, so they cannot drift
 * (`test/govuk/help.test.ts`, HP6, fails on a sentence of `roles.ts` found in this file or the tree's templates). What is written
 * here is the page's own: its title, its section headings (the React page's, in the same order), its table captions and column
 * names, and the two sentences that frame them. Plain words, British English.
 *
 * Nothing in this file is a call or a right: the page is the same for everyone who is signed in, so nothing here asks the Conduit
 * and nothing here is withheld (rule 7 has no count to protect on a page of static words).
 *
 * The build bundles this file with the shared package's source, so the compiled service imports no workspace package it would
 * not have at run time (`apps/pages/scripts/build.mjs`).
 */
import {
  HELP_TITLE,
  LEVEL_WORDS,
  PLACE_WORDS,
  RIGHT_WORDS,
  ROLE_WORDS,
  TEAM_WORDS,
  rightName,
  rightSays,
} from "@ospreyflow/glass-shared";

/** The name of a right, for the one other page that says it (`adminPeopleWords.ts`: the Admin People page): imported once here, with the package bundled in. */
export { rightName };

/** The page's own words, and the ids its sections are linked by. */
export const HELP_WORDS = {
  title: "Help",
  lede: `${HELP_TITLE}: what each role, level and right lets a person do.`,
  contents: "On this page",
  back: "Back to Home",
  places: { id: "help-places", heading: "The places" },
  roles: {
    id: "help-roles",
    heading: "Roles",
    caption: "The built-in roles, what each is for and the places it opens",
    columns: ["Role", "What it is for", "Places it opens"],
  },
  levels: { id: "help-levels", heading: "Your level in a case" },
  teams: { id: "help-teams", heading: "Teams, leads and Authors" },
  rights: {
    id: "help-rights",
    heading: "What each right lets you do",
    caption: "Each right, and what it lets a person do",
    columns: ["Right", "What it lets you do"],
  },
} as const;

export interface HelpView {
  places: { name: string; says: string }[];
  roles: { name: string; says: string; places: string }[];
  levels: { name: string; says: string }[];
  teams: string[];
  rights: { name: string; says: string }[];
}

/** The page's content, read from `roles.ts` each time it is asked for (the words are static: nothing here is a person's). */
export function helpView(): HelpView {
  return {
    places: Object.values(PLACE_WORDS).map((place) => ({ name: place.name, says: place.says })),
    roles: Object.values(ROLE_WORDS).map((role) => ({
      name: role.name,
      says: role.says,
      places: role.places.map((place) => PLACE_WORDS[place].name).join(", "),
    })),
    levels: Object.values(LEVEL_WORDS).map((level) => ({ name: level.name, says: level.says })),
    teams: [TEAM_WORDS.team, TEAM_WORDS.lead, TEAM_WORDS.authors],
    rights: Object.keys(RIGHT_WORDS).map((right) => ({ name: rightName(right), says: rightSays(right) })),
  };
}
