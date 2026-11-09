// Drawing boards (ADR-143 decisions 4 to 7; Amendments 2 and 3; `spec/03_CONDUIT_MIDDLEWARE.md`
// §3.1c): a board is a case view with drawing on. What is drawn on it is written by the Conduit into
// the case's analyst layer (or, for a case that began as a drawing, its drawn dataset), never into a
// source.
//
// It decides nothing. Every answer is only what this reader may see; a refusal comes back in words
// (the case's ceiling, the reader's clearance, a type outside the case's model) and is shown as given.
// A board or item another member may not see is "not found", exactly as one that never existed
// (rule 3), so the Glass never says which.
import type {
  Board,
  BoardOpened,
  BoardPictures,
  DrawnItemMade,
  DrawnWatch,
  Grading,
  MatchSuggestions,
  NewDrawing,
  Withdrawn,
} from "../../../../packages/schemas/generated";

export type { Board, BoardOpened, BoardPictures, DrawnItemMade, DrawnWatch, Grading, MatchSuggestions, NewDrawing, Withdrawn };

export type Answer<T> = { ok: true; value: T } | { ok: false; message: string; code?: string };

/** What every drawn node and link is given (decision 4). */
export interface Asserted {
  label: string;
  marking: string;
  grading: Grading;
  sourceNote: string;
  /** A Document of the case this comes from (on the board), as well as or instead of a note. */
  sourceDocument?: string;
}

export interface ItemToDraw extends Asserted {
  type: string;
  properties: Record<string, string>;
  /** A display setting only (C17 c), not evidence: the type's own icon when not given. */
  icon?: string;
  x: number;
  y: number;
}

export interface LinkToDraw extends Asserted {
  type: string;
  source: string;
  target: string;
}

function caseUrl(apiBaseUrl: string, caseId: string, tail: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(caseId)}/${tail}`;
}

async function send(url: string, bearerToken: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    ...init,
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
  });
}

/** The refusal's own words, as the Conduit gave them. */
async function refusal(response: Response, fallback: string): Promise<{ message: string; code?: string }> {
  const body = ((await response.json().catch(() => ({}))) ?? {}) as Record<string, unknown>;
  const detail = body.detail;
  if (typeof detail === "string") return { message: detail, code: typeof body.error === "string" ? body.error : undefined };
  if (response.status === 404) return { message: "That is not found in this case.", code: "not_found" };
  if (response.status === 403) return { message: "You do not have the right to do that here.", code: "forbidden" };
  if (Array.isArray(detail)) return { message: "Some answers are missing or not allowed: check the form." };
  return { message: `${fallback} (${response.status}).` };
}

async function answered<T>(promise: Promise<Response>, fallback: string, empty = false): Promise<Answer<T>> {
  let response: Response;
  try {
    response = await promise;
  } catch (err) {
    return { ok: false, message: `The server could not be reached: ${err instanceof Error ? err.message : String(err)}` };
  }
  if (!response.ok) return { ok: false, ...(await refusal(response, fallback)) };
  return { ok: true, value: (empty ? null : await response.json()) as T };
}

function asserted(given: Asserted): Record<string, unknown> {
  return {
    label: given.label,
    marking: given.marking,
    grading: given.grading,
    source_note: given.sourceNote.trim() || null,
    ...(given.sourceDocument ? { source_document: given.sourceDocument } : {}),
  };
}

export const listBoards = (api: string, token: string, caseId: string) =>
  answered<Board[]>(send(caseUrl(api, caseId, "boards"), token), "The boards could not be loaded");

export const makeBoard = (
  api: string,
  token: string,
  caseId: string,
  body: { name: string; start: "blank" | "selection" | "view"; nodeIds?: string[]; viewId?: string },
) =>
  answered<Board>(
    send(caseUrl(api, caseId, "boards"), token, {
      method: "POST",
      body: JSON.stringify({
        name: body.name,
        start: body.start,
        ...(body.nodeIds ? { node_ids: body.nodeIds } : {}),
        ...(body.viewId ? { view_id: body.viewId } : {}),
      }),
    }),
    "The board could not be made",
  );

export const openBoard = (api: string, token: string, caseId: string, boardId: string) =>
  answered<BoardOpened>(send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}`), token), "The board could not be opened");

export const shareBoard = (api: string, token: string, caseId: string, boardId: string) =>
  answered<Board>(
    send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/share`), token, { method: "POST" }),
    "The board could not be shared",
  );

export const declareItem = (api: string, token: string, caseId: string, boardId: string, item: ItemToDraw) =>
  answered<DrawnItemMade>(
    send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/items`), token, {
      method: "POST",
      body: JSON.stringify({
        ...asserted(item),
        type: item.type,
        properties: item.properties,
        ...(item.icon ? { icon: item.icon } : {}),
        x: item.x,
        y: item.y,
      }),
    }),
    "The item could not be added",
  );

export const drawLink = (api: string, token: string, caseId: string, boardId: string, link: LinkToDraw) =>
  answered<DrawnItemMade>(
    send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/links`), token, {
      method: "POST",
      body: JSON.stringify({ ...asserted(link), type: link.type, source: link.source, target: link.target }),
    }),
    "The link could not be drawn",
  );

export const moveItems = (
  api: string,
  token: string,
  caseId: string,
  boardId: string,
  positions: Record<string, { x: number; y: number }>,
) =>
  answered<null>(
    send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/layout`), token, {
      method: "PUT",
      body: JSON.stringify({ positions }),
    }),
    "The board's layout could not be kept",
    true,
  );

export const editItem = (
  api: string,
  token: string,
  caseId: string,
  itemId: string,
  change: Partial<Asserted> & { properties?: Record<string, string>; icon?: string },
) =>
  answered<DrawnItemMade>(
    send(caseUrl(api, caseId, `board-items/${encodeURIComponent(itemId)}`), token, {
      method: "PATCH",
      body: JSON.stringify({
        ...(change.label !== undefined ? { label: change.label } : {}),
        ...(change.marking !== undefined ? { marking: change.marking } : {}),
        ...(change.grading !== undefined ? { grading: change.grading } : {}),
        ...(change.sourceNote !== undefined ? { source_note: change.sourceNote } : {}),
        ...(change.sourceDocument ? { source_document: change.sourceDocument } : {}),
        ...(change.properties !== undefined ? { properties: change.properties } : {}),
        ...(change.icon ? { icon: change.icon } : {}),
      }),
    }),
    "The item could not be changed",
  );

export const withdrawItem = (api: string, token: string, caseId: string, itemId: string) =>
  answered<Withdrawn>(
    send(caseUrl(api, caseId, `board-items/${encodeURIComponent(itemId)}/withdraw`), token, { method: "POST" }),
    "The item could not be withdrawn",
  );

export const matchSuggestions = (api: string, token: string, caseId: string, boardId: string) =>
  answered<MatchSuggestions>(
    send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/matches`), token),
    "The suggestions could not be loaded",
  );

export const decideMatch = (
  api: string,
  token: string,
  caseId: string,
  boardId: string,
  decision: { drawn: string; loaded: string; same: boolean },
) =>
  answered<{ edge_id: string }>(
    send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/matches`), token, {
      method: "POST",
      body: JSON.stringify(decision),
    }),
    "The decision could not be kept",
  );

export const boardPictures = (api: string, token: string, caseId: string, boardId: string) =>
  answered<BoardPictures>(
    send(caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/pictures`), token),
    "The pictures could not be loaded",
  );

export function pictureUrl(api: string, caseId: string, boardId: string, nodeId: string): string {
  return caseUrl(api, caseId, `boards/${encodeURIComponent(boardId)}/nodes/${encodeURIComponent(nodeId)}/picture`);
}

export async function uploadPicture(
  api: string,
  token: string,
  caseId: string,
  boardId: string,
  nodeId: string,
  file: File,
  marking: string,
  sourceNote: string,
): Promise<Answer<DrawnItemMade>> {
  const query = new URLSearchParams({ name: file.name, marking, source_note: sourceNote.trim() });
  return answered<DrawnItemMade>(
    fetch(`${pictureUrl(api, caseId, boardId, nodeId)}?${query.toString()}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/octet-stream" },
      body: file,
    }),
    "The picture could not be added",
  );
}

/** C17 (b): a picture the case already holds (an image Document on the board), linked in the layer. */
export const choosePicture = (
  api: string,
  token: string,
  caseId: string,
  boardId: string,
  nodeId: string,
  choice: { documentId: string; marking: string },
) =>
  answered<DrawnItemMade>(
    send(pictureUrl(api, caseId, boardId, nodeId), token, {
      method: "POST",
      body: JSON.stringify({ document_id: choice.documentId, marking: choice.marking }),
    }),
    "The picture could not be chosen",
  );

/** *New drawing board* with no case: a drawn dataset, its home case and the board, in one step. */
export const startDrawing = (
  api: string,
  token: string,
  body: { name: string; highestMarking: string; pack: "fibo" | "niem" | "stix" | null },
) =>
  answered<NewDrawing>(
    send(`${api}/v1/drawings`, token, {
      method: "POST",
      body: JSON.stringify({ name: body.name, highest_marking: body.highestMarking, pack: body.pack }),
    }),
    "The drawing could not be started",
  );

export const drawnWatches = (api: string, token: string, caseId: string) =>
  answered<DrawnWatch[]>(send(caseUrl(api, caseId, "drawn-watches"), token), "The watches could not be loaded");
