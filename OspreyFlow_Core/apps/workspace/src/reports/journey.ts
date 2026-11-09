// The Reports Viewer's journey (ADR-145 Amendment 4 decision 10): from an alert on Home, *Open in
// its case* enters the alert's case on its Figures, the panel the alert concerns outlined, under
// "From ‹the alert› · ← Back to your alerts"; *Open the dashboard* opens the Alert monitoring board
// filtered to the alert's rule and period. They never work an alert: neither opens its address.
//
// Opening a case is a reload (`investigation/cases.ts`'s `openCase`), which may pass through the
// sign-in round trip, so the journey is noted in this tab's session storage beside the case, as a
// case's view is (`rememberCaseView`), and taken once when that case is open. It grants nothing:
// the Figures and the board are read from the Conduit as the reader, as any other time.
import { typologyLabel } from "../alerts/names";
import { caseUrl } from "../investigation/cases";
import { INVESTIGATION_ID_SESSION_KEY } from "../investigation/investigationId";
import type { RuleGroup } from "./figureParts";
import { PERIODS } from "./ReportsView";

export const JOURNEY_KEY = "ospreyflow.alertJourney";

export type JourneyTo = "figures" | "board";

export interface AlertJourney {
  to: JourneyTo;
  caseId: string;
  alertId: string;
  rule: RuleGroup;
  /** The period the board and the Figures open on: the shortest that holds the alert. */
  weeks: number;
}

/** The shortest period offered that still holds an alert raised at `createdAt`. */
export function weeksFor(createdAt: string, now: Date = new Date()): number {
  const weeks =
    (now.getTime() - new Date(createdAt).getTime()) / (7 * 86_400_000);
  return PERIODS.find((p) => p > weeks) ?? PERIODS[PERIODS.length - 1]!;
}

/** The alert in words, for the banner: "the structuring alert", "the hotlist alert". Its rule
 * group and typology only, never its own words (which the address would hold). */
export function journeyWords(rule: RuleGroup): string {
  if (rule.label === "hotlists") return "the hotlist alert";
  if (rule.label === "monitors") return "the monitor alert";
  return `the ${typologyLabel(rule.typology || "other").toLowerCase()} alert`;
}

/** Notes the journey and opens its case (a reload, as every case switch is). */
export function startJourney(
  journey: AlertJourney,
  go: (url: string) => void = (url) => window.location.assign(url),
  storage: Storage = sessionStorage,
): void {
  try {
    storage.setItem(INVESTIGATION_ID_SESSION_KEY, journey.caseId);
    storage.setItem(JOURNEY_KEY, JSON.stringify(journey));
  } catch {
    /* a tab that refuses storage opens the case on its usual view */
  }
  go(caseUrl(journey.caseId));
}

function isJourney(value: unknown): value is AlertJourney {
  const j = value as Partial<AlertJourney> | null;
  return (
    !!j &&
    (j.to === "figures" || j.to === "board") &&
    typeof j.caseId === "string" &&
    typeof j.alertId === "string" &&
    typeof j.weeks === "number" &&
    typeof j.rule?.label === "string" &&
    typeof j.rule?.typology === "string"
  );
}

/** The journey noted for `caseId`, once: the note is cleared whatever it holds. A note for another
 * case, or one this code did not write, is dropped. */
export function takeJourney(
  caseId: string,
  storage: Storage = sessionStorage,
): AlertJourney | null {
  let noted: unknown = null;
  try {
    const raw = storage.getItem(JOURNEY_KEY);
    storage.removeItem(JOURNEY_KEY);
    noted = raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
  return isJourney(noted) && noted.caseId === caseId ? noted : null;
}
