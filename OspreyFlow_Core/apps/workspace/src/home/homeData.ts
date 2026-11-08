// Home's figures (ADR-115 E3, `design/handoff/OspreyFlow Home.dc.html`): read from the routes each
// place already has, case by case, each counting as its reader (rule 3) — Home adds no read path of
// its own, so it adds no access-control surface. A case or a service that could not be read is said,
// never counted as nothing. Where no source exists yet (the last sign-in, a changelog, who granted
// what) Home says nothing rather than invent it; the build plan's E3 row lists each.
import { typologyLabel } from "../alerts/names";
import type { CaseListing } from "../investigation/cases";

export type Unreadable = "unreadable";
export type Tone = "ok" | "warn" | "error" | "info";
export type Place = "glass" | "ingest" | "rules" | "admin";

export interface QueuedAlertLite {
  alert: { id: string; status: string; assignee: string | null; typology?: string | null; created_at: string };
  summary: string;
}
export interface AlertQueueCountsLite {
  open: number;
  claimed: number;
  closing: number;
}
export interface HeldRowLite {
  id: string;
  status: string;
  reason: string;
  held_at: string;
}
export interface RecipeLite {
  status: string;
}
export interface DashboardLite {
  client_id: string;
  last_failure: string | null;
  failed_at: string | null;
}

export interface CaseFigures {
  alerts?: QueuedAlertLite[] | Unreadable;
  /** The queue as counts alone, for a reader refused its rows (ADR-146 Amendment 2 point 3). */
  alertCounts?: AlertQueueCountsLite | Unreadable;
  held?: HeldRowLite[] | Unreadable;
  recipes?: RecipeLite[] | Unreadable;
  entities?: number | Unreadable;
}

export interface HomeInputs {
  /** The reader's subject, as an alert's assignee names it. */
  me: string;
  now: Date;
  cases: CaseListing[] | Unreadable;
  lastCaseId: string | null;
  perCase: Record<string, CaseFigures>;
  /** Absent where the reader may not read it. */
  system?: { components: { name: string; ok: boolean; notice?: string | null }[] } | Unreadable;
  dashboards?: DashboardLite[] | Unreadable;
}

export interface Fact {
  tone: Tone;
  text: string;
}
export interface AttentionRow {
  place: Place;
  tone: Tone;
  title: string;
  detail: string;
  at: string;
  caseId?: string;
  /** An alert's row opens the alert at its address (ADR-146 decision 6), not its case. */
  alertId?: string;
}
export interface RecentCase {
  id: string;
  name: string;
  level: string;
  entities: number | null;
  created: string;
}
export interface HomeSummary {
  glass: Fact[];
  /** Rules and Monitoring's: the alerts in the reader's queues (ADR-146 decision 2). */
  rules: Fact[];
  studio: Fact[];
  admin: Fact[];
  attention: AttentionRow[];
  recent: RecentCase[];
  /** The Admin panel's picture: each component and whether it answered; `null` where not read. */
  services: { name: string; ok: boolean; notice?: string | null }[] | null;
  /** Rows still held across the reader's cases, for the Studio panel's picture. */
  held: number | null;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const LEVELS: Record<string, string> = { author: "Author", editor: "Editor", viewer: "Viewer" };

function readable<T>(value: T | Unreadable | undefined): value is T {
  return value !== undefined && value !== "unreadable";
}

/** Whether an alert is still in the queue: open, claimed, or proposed for closing and waiting for a
 * second person (ADR-146 decision 6, G9: a proposed close counts as open everywhere). */
export function isOpenInQueue(status: string): boolean {
  return status === "open" || status === "claimed" || status === "closing";
}

/** The alerts in a case's team queue still open (ADR-109; Home and the switcher's Rules and
 * Monitoring count). */
export function openInQueue(queue: readonly { alert: { status: string } }[]): number {
  return queue.filter(({ alert }) => isOpenInQueue(alert.status)).length;
}

export function summariseHome(input: HomeInputs): HomeSummary {
  const cases = readable(input.cases) ? input.cases : [];
  const names = new Map(cases.map((c) => [c.id, c.name]));
  const figures = cases.map((c) => ({ id: c.id, ...(input.perCase[c.id] ?? {}) }));

  const glass: Fact[] = [];
  const rules: Fact[] = [];
  const attention: AttentionRow[] = [];
  const queues = figures.filter((f) => f.alerts !== undefined);
  if (queues.length > 0) {
    let inQueue = 0;
    let mine = 0;
    let unread = 0;
    for (const f of queues) {
      if (!readable(f.alerts)) {
        unread += 1;
        continue;
      }
      for (const { alert, summary } of f.alerts) {
        const open = alert.status === "open";
        const claimed = alert.status === "claimed";
        if (isOpenInQueue(alert.status)) inQueue += 1;
        const own = claimed && alert.assignee === input.me;
        if (own) mine += 1;
        if (open || own) {
          attention.push({
            place: "rules", tone: "warn", at: alert.created_at, caseId: f.id, alertId: alert.id,
            title: `${typologyLabel(alert.typology)} alert in ${names.get(f.id)}`,
            detail: own ? `${summary} Claimed by you.` : summary,
          }); // prettier-ignore
        }
      }
    }
    rules.push({ tone: inQueue > 0 ? "warn" : "ok", text: `${plural(inQueue, "alert", "alerts")} in your team's queue, ${mine} claimed by you` });
    if (unread > 0) rules.push({ tone: "error", text: `The queue of ${plural(unread, "case", "cases")} could not be read` });
  }
  // A reader refused the rows is told how many alone, with no alert listed (ADR-146 Amendment 2 point 3).
  const counted = figures.filter((f) => f.alerts === undefined && f.alertCounts !== undefined);
  if (counted.length > 0) {
    let open = 0;
    let unread = 0;
    for (const f of counted) {
      if (!readable(f.alertCounts)) unread += 1;
      else open += f.alertCounts.open + f.alertCounts.claimed + f.alertCounts.closing;
    }
    rules.push({ tone: open > 0 ? "warn" : "ok", text: `${plural(open, "alert", "alerts")} open in your cases' queues` });
    if (unread > 0) rules.push({ tone: "error", text: `The queue of ${plural(unread, "case", "cases")} could not be read` });
  }
  if (readable(input.cases)) {
    const last = input.lastCaseId ? names.get(input.lastCaseId) : undefined;
    glass.push({ tone: "info", text: `${plural(cases.length, "case", "cases")} open to you${last ? `, last worked on ${last}` : ""}` });
  } else {
    glass.push({ tone: "error", text: "Your cases could not be read" });
  }

  const studio: Fact[] = [];
  let heldTotal: number | null = null;
  const helds = figures.filter((f) => f.held !== undefined);
  if (helds.length > 0) {
    heldTotal = 0;
    let unread = 0;
    for (const f of helds) {
      if (!readable(f.held)) {
        unread += 1;
        continue;
      }
      const still = f.held.filter((h) => h.status === "held");
      heldTotal += still.length;
      if (still.length > 0) {
        const newest = still.reduce((a, b) => (a.held_at > b.held_at ? a : b));
        attention.push({
          place: "ingest", tone: "warn", at: newest.held_at, caseId: f.id,
          title: `${plural(still.length, "row", "rows")} held for review in ${names.get(f.id)}`,
          detail: newest.reason,
        }); // prettier-ignore
      }
    }
    studio.push({ tone: heldTotal > 0 ? "warn" : "ok", text: heldTotal > 0 ? `${plural(heldTotal, "row", "rows")} held for review` : "No rows held for review" });
    if (unread > 0) studio.push({ tone: "error", text: `The held rows of ${plural(unread, "case", "cases")} could not be read` });
  }
  const recipeSets = figures.filter((f) => f.recipes !== undefined);
  if (recipeSets.length > 0) {
    const flagged = recipeSets.reduce((n, f) => n + (readable(f.recipes) ? f.recipes.filter((r) => r.status === "flagged").length : 0), 0);
    if (flagged > 0) studio.push({ tone: "warn", text: `${plural(flagged, "recipe", "recipes")} flagged after an ontology change` });
    const unread = recipeSets.filter((f) => !readable(f.recipes)).length;
    if (unread > 0) studio.push({ tone: "error", text: `The recipes of ${plural(unread, "case", "cases")} could not be read` });
  }

  const admin: Fact[] = [];
  let services: HomeSummary["services"] = null;
  if (input.system !== undefined) {
    if (readable(input.system)) {
      services = input.system.components.map(({ name, ok, notice }) => (notice ? { name, ok, notice } : { name, ok }));
      const healthy = services.filter((s) => s.ok).length;
      admin.push({ tone: healthy === services.length ? "ok" : "warn", text: `${healthy} of ${services.length} services healthy` });
      // ADR-114 Amendment 36: what Admin -> System says to do (the Conduit's credential refused).
      for (const s of services) if (!s.ok && s.notice) admin.push({ tone: "error", text: s.notice });
    } else {
      admin.push({ tone: "error", text: "The services could not be asked" });
    }
  }
  if (input.dashboards !== undefined) {
    if (readable(input.dashboards)) {
      const failing = input.dashboards.filter((d) => d.last_failure);
      if (failing.length > 0) admin.push({ tone: "error", text: `report-sync: ${plural(failing.length, "dashboard pull", "dashboard pulls")} failing` });
      for (const d of failing) {
        attention.push({
          place: "admin", tone: "error", at: d.failed_at ?? input.now.toISOString(),
          title: `${d.client_id} is not updating`, detail: `report-sync could not pull: ${d.last_failure}.`,
        }); // prettier-ignore
      }
    } else {
      admin.push({ tone: "error", text: "The dashboards could not be read" });
    }
  }

  attention.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
  const recent = [...cases]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .map((c) => {
      const entities = input.perCase[c.id]?.entities;
      return {
        id: c.id,
        name: c.name,
        level: LEVELS[c.level] ?? c.level,
        entities: readable(entities) ? entities : null,
        created: c.created_at,
      };
    });
  return { glass, rules, studio, admin, attention, recent, services, held: heldTotal };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A time as the hour today, "yesterday", or the day — in the reader's own time zone. */
export function whenLabel(iso: string, now: Date): string {
  const at = new Date(iso);
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(now) - day(at)) / 86_400_000);
  if (days === 0) return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
  if (days === 1) return "yesterday";
  return `${at.getDate()} ${MONTHS[at.getMonth()]}`;
}

/** Reads Home's figures, only from routes the reader's rights open. A route that refuses this case
 * (403: the reader's level there does not reach it) is left out; any other failure is said. */
export async function loadHome(args: {
  apiBaseUrl: string;
  bearerToken: string;
  rights: ReadonlySet<string>;
  me: string;
  lastCaseId: string | null;
  now?: Date;
  fetcher?: typeof fetch;
}): Promise<HomeInputs> {
  const fetcher = args.fetcher ?? ((input, init) => fetch(input, init));
  const get = async <T>(path: string): Promise<T | Unreadable | undefined> => {
    try {
      const response = await fetcher(`${args.apiBaseUrl}${path}`, { headers: { Authorization: `Bearer ${args.bearerToken}` } });
      if (response.status === 403) return undefined;
      if (!response.ok) return "unreadable";
      return (await response.json()) as T;
    } catch {
      return "unreadable";
    }
  };
  const may = (right: string) => args.rights.has(right);
  const cases = (await get<CaseListing[]>("/v1/investigations")) ?? "unreadable";
  const perCase: Record<string, CaseFigures> = {};
  if (readable(cases)) {
    await Promise.all(
      cases.map(async (c) => {
        const at = `/v1/investigations/${encodeURIComponent(c.id)}`;
        const [alerts, held, recipes, counts] = await Promise.all([
          may("read_alert_queue") ? get<QueuedAlertLite[]>(`${at}/alert-queue`) : undefined,
          may("read_held_rows") ? get<HeldRowLite[]>(`${at}/held-rows`) : undefined,
          may("edit_pipelines") ? get<RecipeLite[]>(`${at}/ingest/recipes`) : undefined,
          may("investigate") ? get<{ nodes: Record<string, number> }>(`${at}/explore/counts`) : undefined,
        ]);
        // Refused the rows (the place not offered), the queue is read as counts alone.
        const alertCounts =
          may("read_alert_queue") && alerts === undefined ? await get<AlertQueueCountsLite>(`${at}/alert-queue/counts`) : undefined;
        perCase[c.id] = {
          alerts,
          ...(alertCounts !== undefined ? { alertCounts } : {}),
          held,
          recipes,
          entities: readable(counts) ? Object.values(counts.nodes).reduce((a, b) => a + b, 0) : counts,
        };
      }),
    );
  }
  const [system, dashboards] = await Promise.all([
    may("administer_system") ? get<{ components: { name: string; ok: boolean; notice?: string | null }[] }>("/v1/admin/system") : undefined,
    may("manage_dashboards") ? get<DashboardLite[]>("/v1/admin/dashboards") : undefined,
  ]);
  return { me: args.me, now: args.now ?? new Date(), cases, lastCaseId: args.lastCaseId, perCase, system, dashboards };
}
