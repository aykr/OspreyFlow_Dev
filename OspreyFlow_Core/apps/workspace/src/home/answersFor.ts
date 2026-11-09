// Home's *What you can do, and what you answer for* (ADR-145 Amendment 4 decision 12; L2.7), worked out
// for the person signed in from what they may already see: their own rights (`/v1/me/rights`), their
// own roles, their own cases (`/v1/investigations`, each with their level) and their own *Needs you*
// (`/v1/me/needs-you`, gated in the Conduit). Home adds no read of its own, so nothing listed here is
// beyond the reader. The words are `help/roles.ts`'s, the one source the tips and the help page use.
// Where no source exists yet (a team's lead and cover, a watch's owner and expiry, a level given
// through a team, which the case list does not carry) Home says nothing rather than invent it.
import type { NeedsYou } from "../admin/needsYou/needsYouApi";
import { RIGHT_GROUPS } from "../admin/sections/Roles";
import { LEVEL_WORDS, PLACE_WORDS, ROLE_WORDS, rightName, rightSays, rolesHolding, type Right } from "../help/roles";
import type { CaseListing } from "../investigation/cases";
import { placesFor } from "../shell/places";

export interface CanDo {
  right: string;
  name: string;
  says: string;
  /** *Why can I do this?*: the role or grant of this person's behind it, by name. */
  why: string;
}

export type Opens =
  | { to: "case"; caseId: string }
  | { to: "model"; datasetId: string }
  | { to: "operations" }
  | { to: "none" };

export interface AnswerLine {
  text: string;
  why: string;
  opens: Opens;
}

export interface AnswersFor {
  places: { key: string; name: string; says: string }[];
  can: { group: string; rights: CanDo[] }[];
  levels: { caseId: string; name: string; level: string }[];
  answers: AnswerLine[];
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The roles of this person that give `right`, by name: a built-in role whose rights hold it, a right
 * given singly, or a custom role (whose name Home is not told). */
export function whyHeld(right: string, roles: readonly string[]): string {
  const holding = new Set(rolesHolding(right as Right));
  const named = roles.map((r) => ROLE_WORDS[r]?.name).filter((n): n is string => !!n && holding.has(n));
  const reasons = [...named.map((n) => `your ${n} role`)];
  if (roles.includes(`right:${right}`)) reasons.push("a right given to you alone");
  if (reasons.length === 0 && roles.some((r) => r.startsWith("role:"))) reasons.push("a role your administrator made");
  if (reasons.length === 0) return "Given by your roles.";
  return `Given by ${reasons.join(" and ")}.`;
}

export function answersFor(input: {
  rights: ReadonlySet<string>;
  roles: readonly string[];
  cases: readonly CaseListing[];
  needs: NeedsYou | null;
}): AnswersFor {
  const { rights, roles, cases, needs } = input;
  const places = placesFor(rights).map((key) => ({ key, ...PLACE_WORDS[key as keyof typeof PLACE_WORDS] }));
  const can = RIGHT_GROUPS.map((g) => ({
    group: g.label,
    rights: g.rights
      .filter((r) => rights.has(r))
      .map((r) => ({ right: r, name: rightName(r), says: rightSays(r), why: whyHeld(r, roles) })),
  })).filter((g) => g.rights.length > 0);
  const levels = cases.map((c) => ({ caseId: c.id, name: c.name, level: LEVEL_WORDS[c.level]?.name ?? c.level }));

  const answers: AnswerLine[] = [];
  for (const c of cases.filter((c) => c.level === "author")) {
    answers.push({ text: `Author of ${c.name}`, why: LEVEL_WORDS.author.says, opens: { to: "case", caseId: c.id } });
  }
  for (const p of needs?.promotions_overdue ?? []) {
    answers.push({
      text: `Reviewer of promotions: ${p.words}`,
      // An Author holding Review promotions, or the dataset's unit's administrator (decision 11).
      why: whyHeld(rights.has("review_promotions") ? "review_promotions" : "administer_system", roles),
      opens: rights.has("operate_schedules") ? { to: "operations" } : { to: "none" },
    });
  }
  for (const p of needs?.proposals ?? []) {
    // A proposal above the reader's clearance is said to exist, never counted (ADR-143 Amendment 4).
    if (p.to_decide > 0) {
      answers.push({
        text: `Data engineer of ${p.dataset_name}: ${plural(p.to_decide, "proposed link type", "proposed link types")} to decide`,
        why: whyHeld("accept_types", roles),
        opens: { to: "model", datasetId: p.dataset_id },
      });
    }
    if (p.above_clearance) {
      answers.push({
        text: `Data engineer of ${p.dataset_name}: a proposed link type above your clearance`,
        why: "Someone cleared to its dataset's highest marking decides it; you are told only that it waits.",
        opens: { to: "none" },
      });
    }
  }
  return { places, can, levels, answers };
}
