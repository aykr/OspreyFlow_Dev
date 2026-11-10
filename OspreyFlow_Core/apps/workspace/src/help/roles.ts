// *Roles, teams and Authors* in one set of words (ADR-145 Amendment 4 decision 12): the tips in Admin
// and the Ingest Studio, the help page, and the guides' sections (Lane 4) all take their wording from
// here, so they cannot drift. Each right's words are written here, and every right worded when L2.12
// was built must keep them (`roles.test.ts` pins the list); a right another lane adds in
// `packages/schemas/rights.py` before its words are is said by its name (`rightSays`) in Admin's tips,
// red nowhere, and is missing from the help page's list until worded (the Glass holds no runtime list
// of rights to draw it from). `roles.test.ts` refuses words for a right `rights.py` no longer declares.
//
// Plain words, British English; what a role or right lets a person do, never how it is checked.
import type { BuiltInRole } from "../../../../packages/schemas/generated";
import BY_ROLE from "../shell/placesByRole.json";

export type Right = BuiltInRole["rights"][number];

/** The four places (ADR-145 Amendment 4 decision 1). */
export const PLACE_WORDS = {
  glass: { name: "The Glass", says: "Investigate a case: search, expand, map, read its figures and its boards." },
  ingest: { name: "Ingest Studio", says: "Bring data in: sources, pipelines, the domain model, held rows and releases." },
  rules: { name: "Rules and Monitoring", says: "Work the alerts that rules and watches raise, in one queue, and see what raises them." },
  admin: { name: "Admin", says: "Run the deployment: people, roles, teams, datasets, models, maps and operations." },
} as const;

/** The built-in roles (ADR-112 and its Amendment 5), and the Super user preset. Which places each
 * opens is read from `shell/placesByRole.json`, the record `test_place_routes.py` holds to the routes,
 * never copied here. */
const SAID_ROLES: Record<string, { name: string; says: string }> = {
  analyst: { name: "Analyst", says: "Investigates cases, works alerts and keeps watches. Reads figures and boards." },
  data_engineer: { name: "Data Engineer", says: "Builds and runs pipelines, reviews promotions into a dataset and decides held rows." },
  "osprey-admin": { name: "Administrator", says: "Looks after people, roles, teams, datasets and the deployment. Does not investigate by being one." },
  reports_viewer: { name: "Reports Viewer", says: "Reads a case's figures and the dashboards, and sees the alerts on cases they can read. Never works an alert." },
  rule_author: { name: "Rule author", says: "Writes the rules that raise alerts, and works the alerts in the queue." },
  super: { name: "Super user", says: "Analyst, Data Engineer and Rule author together, given as three roles. Still never the second person on their own work." },
};  // prettier-ignore

type PlaceKey = keyof typeof PLACE_WORDS;
const RECORDED = (BY_ROLE as { roles: Record<string, { places: string[] }> }).roles;

export const ROLE_WORDS: Record<string, { name: string; says: string; places: PlaceKey[] }> = Object.fromEntries(
  Object.entries(SAID_ROLES).map(([key, role]) => [
    key,
    { ...role, places: (RECORDED[key]?.places ?? []).filter((p): p is PlaceKey => p in PLACE_WORDS) },
  ]),
);

/** Each right, in plain words: what it lets a person do. */
export const RIGHT_WORDS: Partial<Record<Right, string>> = {
  create_case: "Start a case.",
  share_case: "Give people a level in a case.",
  remove_case: "Remove a case they are an Author of.",
  export: "Export from a case, through the export checks.",
  export_override: "Export an item that asks its originator first, with a reason.",
  investigate: "Search, expand, follow paths and filter in a case.",
  edit_graph: "Add and change entities and links in a case.",
  confirm_inferred: "Confirm what a model suggested, so it is no longer inferred.",
  extract_files: "Add files to a case, run extraction and decide its findings.",
  resolve_entities: "Say two entities are the same, or not.",
  record_assessment: "Record judgements, gaps and assumptions.",
  ask_model: "Ask the model a question about a case.",
  run_analysis: "Run analyses such as communities and centrality.",
  propose_link_type: "Propose a new type of link.",
  draw_on_boards: "Draw on a case's boards.",
  promote_to_dataset: "Propose a drawn item for the dataset.",
  propose_types: "Propose a new entity type.",
  read_alert_queue: "See the alerts in a case's queue.",
  triage_alerts: "Claim, close and hand back alerts.",
  deploy_rules: "Turn rules on and off for a case.",
  read_rule_audit: "Read who changed which rule, and when.",
  read_held_rows: "See rows a load held back for review.",
  decide_held_rows: "Release or reject held rows.",
  trace_ownership: "Trace ownership and neighbourhood risk.",
  keep_watches: "Keep watches and hotlists.",
  load_screening_lists: "Load and refresh licensed screening lists.",
  author_rules: "Write the rules that raise alerts.",
  manage_strength_influencers: "Change what makes a link strong.",
  edit_pipelines: "Build and change pipelines.",
  verify_pipelines: "Test a pipeline against its sample.",
  publish_pipelines: "Deploy a pipeline.",
  run_pipelines: "Run a pipeline.",
  schedule_pipelines: "Put a pipeline on a schedule.",
  add_ingest_files: "Add files for a pipeline to load.",
  revert_loads: "Take back a load.",
  edit_target_model: "Change a dataset's domain model.",
  review_promotions: "Review items proposed for a dataset.",
  accept_types: "Accept a proposed type into a domain model.",
  merge_datasets: "Merge a drawn dataset into another.",
  read_reports: "Read a case's figures and the dashboards.",
  read_report_feed: "Download a case's figures for a dashboard.",
  read_data_feeds: "See the data feeds a case's pipelines send.",
  administer_system: "Change how the deployment runs.",
  manage_people: "Add people and give them roles.",
  manage_dashboards: "Register dashboards.",
  operate_schedules: "Pause and resume schedules.",
  manage_ontology: "Change the deployment's ontology.",
  manage_geospatial: "Choose the maps the deployment shows.",
  read_audit: "Read the audit log.",
  read_export_ledger: "Read the record of what left the deployment.",
  manage_models: "Choose the models and their keys.",
};

/** A right whose id is not its name on screen: the screens say "domain model", the code keeps
 * `TargetModel` (ADR-140 Amendment 9 decision 1; L1.8). `rightNames.test.ts` holds every right's name
 * to the screens' words. */
const RIGHT_NAMES: Partial<Record<Right, string>> = {
  edit_target_model: "Edit domain model",
};

/** A right's name in words: `review_promotions` reads "Review promotions". Admin's labels take it from
 * here (`admin-tips.patch` makes `admin/sections/Roles.tsx`'s `rightWords` this function). */
export function rightName(right: string): string {
  const named = RIGHT_NAMES[right as Right];
  if (named) return named;
  const words = right.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** What a right lets a person do: its own words, or, for a right added before its words were, its name. */
export function rightSays(right: string): string {
  return RIGHT_WORDS[right as Right] ?? `${rightName(right)}.`;
}

/** The levels a person holds in a case (ADR-052). */
export const LEVEL_WORDS = {
  viewer: { name: "Viewer", says: "Reads the case. Changes nothing in it." },
  editor: { name: "Editor", says: "Works the case: adds, links, confirms and works its alerts, as their role allows." },
  author: { name: "Author", says: "Answers for the case: gives levels, and may remove it. A dataset's Authors are its home case's Authors." },
} as const;

/** Teams, leads and a dataset's Authors (ADR-112 Amendment 5; ADR-145 Amendment 4 decision 3). */
export const TEAM_WORDS = {
  team: "A team is a set of people. A level or a rule's alerts given to a team reach every member while they are in it, and not after.",
  lead: "A team's lead may give a team alert to a named member, take one back, and hold one until a date. A lead may name someone to cover while away.",
  authors: "A dataset's Authors answer for it: they are the Authors of its home case. Owning is not acting: reviewing a promotion or accepting a type also needs that right.",
  through: (team: string) => `through ${team}`,
} as const;

const RECORDED_RIGHTS = (BY_ROLE as { roles: Record<string, { rights?: string[] }> }).roles;

/** The roles that hold `right`, by name, read from `shell/placesByRole.json` (the record
 * `test_place_routes.py` holds to the routes, never copied here): each built-in role these words name
 * (`ROLE_WORDS`), never one said by its id (the Studio's older roles, which ADR-112 folded into the Data
 * Engineer, are not offered), and never the Super user preset, which is given as three roles. A custom
 * role is an administrator's, and not named here. */
export function rolesHolding(right: Right): string[] {
  return Object.entries(RECORDED_RIGHTS)
    .filter(([key, role]) => key !== "super" && key in SAID_ROLES && role.rights?.includes(right))
    .map(([key]) => SAID_ROLES[key]!.name)
    .sort((a, b) => a.localeCompare(b));
}

/** Why a person cannot take an action, and which roles can (decision 12 as the owner ruled it on
 * 9 November 2026, ADR-145 Amendment 7: the roles that hold the right, never the people, so no one
 * learns who holds a right). */
export function whyNotByRole(right: Right): string {
  const need = `You need ${rightName(right)}`;
  const roles = rolesHolding(right);
  if (roles.length === 0) return `${need}; no built-in role has it. Ask an administrator.`;
  if (roles.length === 1) return `${need}; the ${roles[0]!} role has it. Ask an administrator to give it to you.`;
  const named = `${roles.slice(0, -1).join(", ")} and ${roles.at(-1)!}`;
  return `${need}; the ${named} roles have it. Ask an administrator to give you one.`;
}

export const HELP_TITLE = "Roles, teams and Authors";
