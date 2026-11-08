// Case views (ADR-144; `spec/03_CONDUIT_MIDDLEWARE.md` §3.1, case views): a saved lens on one case,
// holding no data, private to its creator until shared, deleted only by its creator.
//
// It decides nothing. The Conduit answers each route with only the views this reader may see, and a
// view opened is re-read now as this reader may see the case, collapsed at the view's own threshold;
// `missing` counts what it could not show and names none. The Glass shows what it is given, and says
// a refusal in words: a view another member keeps private is "not found", exactly as one that never
// existed (rule 3), so the Glass never says which.
import type {
  CaseView,
  CaseViewOpened,
  ViewFilter,
} from "../../../../packages/schemas/generated";
import type { LimitExceeded } from "../workingset/models";

export type { CaseView, CaseViewOpened, ViewFilter };

/** What *Save as a view* sends: a name and exactly one lens, with what the reader had on screen. */
export interface ViewToSave {
  name: string;
  nodeIds?: string[];
  filter?: { entityTypes?: string[]; validFrom?: string; validTo?: string };
  layout?: Record<string, { x: number; y: number }>;
  window?: { validFrom: string; validTo: string | null } | null;
  threshold?: number | null;
}

export type Saved = { ok: true; view: CaseView } | { ok: false; message: string };
export type Done = { ok: true } | { ok: false; message: string };
export type Opened =
  | { ok: true; opened: CaseViewOpened }
  | { ok: false; kind: "limit_exceeded"; wouldBe: LimitExceeded }
  | { ok: false; kind: "not_found" }
  | { ok: false; kind: "failed"; message: string };

function viewsUrl(apiBaseUrl: string, caseId: string, tail = ""): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(caseId)}/views${tail}`;
}

async function send(url: string, bearerToken: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    ...init,
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
  });
}

async function bodyOf(response: Response): Promise<Record<string, unknown>> {
  return ((await response.json().catch(() => ({}))) ?? {}) as Record<string, unknown>;
}

function unreachable(err: unknown): string {
  return `The server could not be reached: ${err instanceof Error ? err.message : String(err)}`;
}

/** The case's views this reader may see: their own, and those shared with the case. */
export async function listViews(apiBaseUrl: string, bearerToken: string, caseId: string): Promise<CaseView[]> {
  const response = await send(viewsUrl(apiBaseUrl, caseId), bearerToken);
  if (!response.ok) throw new Error(`The views could not be loaded (${response.status}).`);
  return (await response.json()) as CaseView[];
}

/** The body `POST …/views` takes (`CaseViewInput`). */
export function viewBody(view: ViewToSave): Record<string, unknown> {
  const body: Record<string, unknown> = { name: view.name };
  if (view.nodeIds) body.node_ids = view.nodeIds;
  if (view.filter) {
    const filter: Record<string, unknown> = {};
    if (view.filter.entityTypes !== undefined) filter.entity_types = view.filter.entityTypes;
    if (view.filter.validFrom) filter.valid_from = `${view.filter.validFrom}T00:00:00Z`;
    if (view.filter.validTo) filter.valid_to = `${view.filter.validTo}T23:59:59Z`;
    body.filter = filter;
  }
  if (view.layout && Object.keys(view.layout).length > 0) body.layout = view.layout;
  if (view.window) body.window = { valid_from: view.window.validFrom, valid_to: view.window.validTo };
  if (typeof view.threshold === "number") body.threshold = view.threshold;
  return body;
}

/** *Save as a view*: private to the reader until they share it. */
export async function saveView(
  apiBaseUrl: string,
  bearerToken: string,
  caseId: string,
  view: ViewToSave,
): Promise<Saved> {
  if (!view.name.trim()) return { ok: false, message: "Give the view a name." };
  if (!view.nodeIds && !view.filter) return { ok: false, message: "Select something to save as a view." };
  if (view.nodeIds && view.nodeIds.length === 0) {
    return { ok: false, message: "Select at least one node to save as a view." };
  }
  try {
    const response = await send(viewsUrl(apiBaseUrl, caseId), bearerToken, {
      method: "POST",
      body: JSON.stringify(viewBody({ ...view, name: view.name.trim() })),
    });
    if (response.status === 201 || response.ok) return { ok: true, view: (await response.json()) as CaseView };
    if (response.status === 403) {
      return { ok: false, message: "Saving a view needs the right to work this case." };
    }
    if (response.status === 422) {
      return { ok: false, message: "The view could not be saved as it is. Check its name and what it shows." };
    }
    return { ok: false, message: `The view could not be saved (${response.status}). Nothing was saved; try again.` };
  } catch (err) {
    return { ok: false, message: unreachable(err) };
  }
}

/** *Share with the case*: every member then sees it, at their own level. Its creator only. */
export async function shareView(apiBaseUrl: string, bearerToken: string, caseId: string, viewId: string): Promise<Done> {
  try {
    const response = await send(viewsUrl(apiBaseUrl, caseId, `/${encodeURIComponent(viewId)}/share`), bearerToken, {
      method: "POST",
    });
    if (response.ok) return { ok: true };
    const body = await bodyOf(response);
    if (response.status === 403 && body.error === "not_the_views_creator") {
      return { ok: false, message: "Only the person who saved this view can share it." };
    }
    if (response.status === 404) return { ok: false, message: "That view is no longer there." };
    return { ok: false, message: `The view could not be shared (${response.status}). Try again.` };
  } catch (err) {
    return { ok: false, message: unreachable(err) };
  }
}

/** Deletes the view and nothing else: what is on the case stays on the case. Its creator only. */
export async function deleteView(apiBaseUrl: string, bearerToken: string, caseId: string, viewId: string): Promise<Done> {
  try {
    const response = await send(viewsUrl(apiBaseUrl, caseId, `/${encodeURIComponent(viewId)}`), bearerToken, {
      method: "DELETE",
    });
    if (response.ok) return { ok: true };
    const body = await bodyOf(response);
    if (response.status === 403 && body.error === "not_the_views_creator") {
      return { ok: false, message: "Only the person who saved this view can delete it." };
    }
    if (response.status === 404) return { ok: false, message: "That view is no longer there." };
    return { ok: false, message: `The view could not be deleted (${response.status}). Try again.` };
  } catch (err) {
    return { ok: false, message: unreachable(err) };
  }
}

/** Opens a view now: what this reader may see of it, and a count of what it could not show. */
export async function openView(apiBaseUrl: string, bearerToken: string, caseId: string, viewId: string): Promise<Opened> {
  try {
    const response = await send(viewsUrl(apiBaseUrl, caseId, `/${encodeURIComponent(viewId)}`), bearerToken);
    if (response.ok) return { ok: true, opened: (await response.json()) as CaseViewOpened };
    const body = await bodyOf(response);
    if (response.status === 409 && body.error === "limit_exceeded") {
      return { ok: false, kind: "limit_exceeded", wouldBe: body as unknown as LimitExceeded };
    }
    if (response.status === 404) return { ok: false, kind: "not_found" };
    return { ok: false, kind: "failed", message: `The view could not be opened (${response.status}). Try again.` };
  } catch (err) {
    return { ok: false, kind: "failed", message: unreachable(err) };
  }
}

/** How many of a view's items it could not show, in words that never say why (ADR-144 decision 2). */
export function missingNote(missing: number): string | null {
  if (missing <= 0) return null;
  return `${missing} item${missing === 1 ? "" : "s"} in this view could not be shown`;
}
