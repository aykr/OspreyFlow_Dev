// One entity's own picture (ADR-105): an image Document that `DEPICTS` it, held in the case as
// evidence. This keeps, for each node in view, the small picture the canvas draws inside it, made the
// way ADR-079 makes a type's picture (`thumbnailFromFile`), so only a raster data address that passes
// the strict check is ever drawn. The server decides which pictures the analyst may see; a node it
// does not answer for has none.
import { thumbnailFromFile } from "./iconImage";

interface Held {
  documentId: string;
  dataUrl: string;
}

let pictures = new Map<string, Held>();
const listeners = new Set<() => void>();

function changed(): void {
  listeners.forEach((listener) => listener());
}

/** The picture drawn inside node `nodeId`, if it has one of its own. */
export function entityPictureFor(nodeId: string): string | undefined {
  return pictures.get(nodeId)?.dataUrl;
}

export function onEntityPicturesChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Forgets every picture, as when the case changes. */
export function forgetEntityPictures(): void {
  if (pictures.size === 0) return;
  pictures = new Map();
  changed();
}

/** For tests: holds `dataUrl` as node `nodeId`'s picture. */
export function setEntityPictureForTest(nodeId: string, dataUrl: string): void {
  pictures = new Map(pictures).set(nodeId, { documentId: `test:${nodeId}`, dataUrl });
  changed();
}

export interface PictureApi {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

function caseUrl(api: PictureApi, rest: string): string {
  return `${api.apiBaseUrl}/v1/investigations/${encodeURIComponent(api.investigationId)}${rest}`;
}

function nodeUrl(api: PictureApi, nodeId: string): string {
  return caseUrl(api, `/nodes/${encodeURIComponent(nodeId)}/picture`);
}

async function thumbnailOf(api: PictureApi, nodeId: string): Promise<string> {
  const response = await fetch(nodeUrl(api, nodeId), {
    headers: { Authorization: `Bearer ${api.bearerToken}` },
  });
  if (!response.ok) throw new Error(`picture ${response.status}`);
  const blob = await response.blob();
  return thumbnailFromFile(new File([blob], "picture", { type: blob.type }));
}

/** Asks which of `nodeIds` have a picture of their own and fetches any not already held; a node the
 * server no longer answers for loses its picture. A picture that cannot be fetched or drawn is left
 * out: the node shows its type's picture instead. */
export async function loadEntityPictures(api: PictureApi, nodeIds: readonly string[]): Promise<void> {
  if (nodeIds.length === 0) return;
  const response = await fetch(caseUrl(api, "/pictures"), {
    method: "POST",
    headers: { Authorization: `Bearer ${api.bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ node_ids: nodeIds }),
  });
  if (!response.ok) return;
  const found = (await response.json()) as { node_id: string; document_id: string }[];
  const answered = new Map(found.map((p) => [p.node_id, p.document_id]));
  const next = new Map(pictures);
  let moved = false;
  for (const nodeId of nodeIds) {
    const documentId = answered.get(nodeId);
    const held = next.get(nodeId);
    if (documentId === undefined) {
      if (held) {
        next.delete(nodeId);
        moved = true;
      }
      continue;
    }
    if (held?.documentId === documentId) continue;
    try {
      next.set(nodeId, { documentId, dataUrl: await thumbnailOf(api, nodeId) });
      moved = true;
    } catch {
      if (held) {
        next.delete(nodeId);
        moved = true;
      }
    }
  }
  if (!moved) return;
  pictures = next;
  changed();
}

async function refusal(response: Response): Promise<string> {
  let body: { error?: string; detail?: string } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // no body
  }
  if (response.status === 413) return "That picture is larger than the upload limit.";
  if (response.status === 403) return "Changing a picture needs Editor access to this case.";
  if (response.status === 415) return "That file is not a picture: png, jpeg, webp or gif.";
  if (body.error === "node_not_found") return "That entity is no longer in the view.";
  if (body.error === "picture_not_found") return "That entity has no picture of its own to remove.";
  return body.detail ?? `The picture was refused (${response.status}).`;
}

/** Sets `file` as node `nodeId`'s own picture, under `classification` and `legalBasis`. Resolves to
 * the deltas the server returned; rejects with a sentence for the analyst. */
export async function setEntityPicture(
  api: PictureApi,
  nodeId: string,
  file: File,
  classification: string,
  legalBasis: string,
): Promise<unknown[]> {
  const query = new URLSearchParams({ name: file.name, classification, legal_basis: legalBasis });
  let response: Response;
  try {
    response = await fetch(`${nodeUrl(api, nodeId)}?${query.toString()}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${api.bearerToken}`, "Content-Type": "application/octet-stream" },
      body: file,
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (!response.ok) throw new Error(await refusal(response));
  const result = (await response.json()) as { deltas: unknown[] };
  await loadEntityPictures(api, [nodeId]);
  return result.deltas;
}

/** Puts node `nodeId` back to its type's picture; its own is kept as evidence. */
export async function removeEntityPicture(api: PictureApi, nodeId: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(nodeUrl(api, nodeId), {
      method: "DELETE",
      headers: { Authorization: `Bearer ${api.bearerToken}` },
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (!response.ok) throw new Error(await refusal(response));
  if (pictures.has(nodeId)) {
    pictures = new Map(pictures);
    pictures.delete(nodeId);
    changed();
  }
  return response.json();
}
