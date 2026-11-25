/**
 * The Admin People page's words and the view it is drawn from (slice AD3a; ADR-152 decisions 5, 6 and 12; FUNCTIONS row `admin`;
 * scenario AP). Nothing here is a call or a right: a word, or a function from what the Conduit answered to the rows the template draws.
 *
 * What the page says of a right is the Help page's (`helpWords.ts`, which has the shared package's `roles.ts` bundled in): the name
 * of a right is imported and never written again here. A role is said by what the Conduit's own catalogue calls it
 * (`GET /v1/admin/roles`): a built-in role by its label, a custom role by its name. The identifier of a role or a right is never
 * drawn, and a grant the catalogue does not hold is said as an older grant, in those words and no others.
 *
 * The view keeps every person the Conduit sent, in the order it sent them: nothing here removes, cuts, sorts or counts (decision 5;
 * rule 3 stays with the Conduit and its adapters). A list or a catalogue that is not the shape the page draws from is not a view
 * (`undefined`): a partial table is never drawn (rule 2). Plain words, British English.
 */
import { rightName } from "./helpWords.js";

export const ADMIN_PEOPLE_WORDS = {
  title: "Admin: People",
  lede: "The people the service lists, the roles each one holds and the state of each account. This page only shows them.",
  caption: "People and their roles",
  columns: ["Person", "Roles", "State"],
  noRoles: "No roles",
  olderGrant: "Older grant",
  right: (name: string): string => `Right: ${name}`,
  enabled: "Enabled",
  disabled: "Disabled",
  invited: "Invited — must set a password",
  organisation: "Signs in through the organisation",
  guest: "Guest: homed outside this organisation's Entra ID; signs in only while guest accounts are admitted",
  empty: "There are no people to list.",
  unreadable: "The people could not be read just now. Nothing is shown, and nothing has changed. Try again in a few minutes.",
  help: "What each role and right lets a person do",
  back: "Back to Home",
} as const;

export interface PersonRow {
  name: string;
  roles: string[];
  state: string[];
}

export type PeopleView = { kind: "empty" } | { kind: "table"; rows: PersonRow[] };

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === "string";

/** `GET /v1/admin/roles`: the built-in roles' labels and the custom roles' names, by id; `undefined` when it is not a catalogue. */
export function catalogueOf(body: unknown): { builtIn: Map<string, string>; custom: Map<string, string> } | undefined {
  if (!isObject(body) || !Array.isArray(body["built_in"]) || !Array.isArray(body["custom"])) return undefined;
  const builtIn = new Map<string, string>();
  const custom = new Map<string, string>();
  for (const role of body["built_in"] as unknown[]) {
    if (!isObject(role) || !isText(role["id"]) || !isText(role["label"])) return undefined;
    builtIn.set(role["id"], role["label"]);
  }
  for (const role of body["custom"] as unknown[]) {
    if (!isObject(role) || !isText(role["id"]) || !isText(role["name"])) return undefined;
    custom.set(role["id"], role["name"]);
  }
  return { builtIn, custom };
}

/** One grant, in words: never its identifier. */
export function roleWords(role: string, catalogue: NonNullable<ReturnType<typeof catalogueOf>>): string {
  const built = catalogue.builtIn.get(role);
  if (built !== undefined) return built;
  if (role.startsWith("role:")) return catalogue.custom.get(role.substring("role:".length)) ?? ADMIN_PEOPLE_WORDS.olderGrant;
  if (role.startsWith("right:")) return ADMIN_PEOPLE_WORDS.right(rightName(role.substring("right:".length)));
  return ADMIN_PEOPLE_WORDS.olderGrant;
}

/** The state of an account, in words: the React section's (`People.tsx`), the organisation's sign-in beside it and, for a guest (B2B)
 * account, the mark that it signs in only while guest accounts are admitted (`PersonAccount.guest`, ADR-148 Amendment 17). */
export function stateWords(enabled: boolean, mustSetPassword: boolean, organisationLinked: boolean, guest: boolean): string[] {
  const first = !enabled ? ADMIN_PEOPLE_WORDS.disabled : mustSetPassword ? ADMIN_PEOPLE_WORDS.invited : ADMIN_PEOPLE_WORDS.enabled;
  const words = organisationLinked ? [first, ADMIN_PEOPLE_WORDS.organisation] : [first];
  return guest ? [...words, ADMIN_PEOPLE_WORDS.guest] : words;
}

/** What the page draws from the two answers, or `undefined` when either is not the shape the page draws from (said as a failure). */
export function peopleView(people: unknown, roles: unknown): PeopleView | undefined {
  const catalogue = catalogueOf(roles);
  if (catalogue === undefined || !Array.isArray(people)) return undefined;
  const rows: PersonRow[] = [];
  for (const person of people as unknown[]) {
    if (!isObject(person) || !isText(person["name"]) || !isText(person["username"]) || typeof person["enabled"] !== "boolean") return undefined;
    const held = person["roles"];
    if (!Array.isArray(held) || !(held as unknown[]).every(isText)) return undefined;
    const roleList = held as string[];
    rows.push({
      name: person["name"].trim() === "" ? person["username"] : person["name"],
      roles: roleList.length === 0 ? [ADMIN_PEOPLE_WORDS.noRoles] : roleList.map((role) => roleWords(role, catalogue)),
      state: stateWords(person["enabled"], person["must_set_password"] === true, person["organisation_linked"] === true, person["guest"] === true),
    });
  }
  return rows.length === 0 ? { kind: "empty" } : { kind: "table", rows };
}
