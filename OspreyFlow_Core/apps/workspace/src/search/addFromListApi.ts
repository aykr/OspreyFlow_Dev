// Add many from a list (ADR-128 decision 1, B2): the Glass's side of `POST
// /v1/investigations/{id}/working-set/add-by-identifiers`. It sends the typed strings and receives
// four counts and, once the analyst confirms, the delta to draw. It is never given an identifier
// back, a source-system identifier least of all (rule 7), and what it says of a refusal carries the
// figure and says nothing was added (rule 2).
import type { WorkingSetDelta } from "../workingset/models";

/** The most identifiers one request reads; the Conduit refuses more by name. */
export const MAX_IDENTIFIERS = 5000;

export interface IdentifierCounts {
  read: number;
  found: number;
  matched_nothing: number;
  repeated: number;
}

export interface AddedFromList {
  counts: IdentifierCounts;
  delta: WorkingSetDelta;
}

/** A refusal or failure, already in words for the analyst. */
export class AddFromListError extends Error {}

const NUMBER = new Intl.NumberFormat("en-GB");

function noun(count: number, one: string, many: string): string {
  return `${NUMBER.format(count)} ${count === 1 ? one : many}`;
}

/** "40 identifiers read. 38 found. 2 matched nothing you can see. 1 repeated." */
export function countSentence(counts: IdentifierCounts): string {
  return (
    `${noun(counts.read, "identifier", "identifiers")} read. ` +
    `${NUMBER.format(counts.found)} found. ` +
    `${NUMBER.format(counts.matched_nothing)} matched nothing you can see. ` +
    `${NUMBER.format(counts.repeated)} repeated.`
  );
}

function firstCell(line: string): string {
  if (line.startsWith('"')) {
    let out = "";
    for (let i = 1; i < line.length; i += 1) {
      if (line[i] === '"') {
        if (line[i + 1] === '"') {
          out += '"';
          i += 1;
        } else {
          return out;
        }
      } else {
        out += line[i];
      }
    }
    return out;
  }
  const comma = line.indexOf(",");
  return comma === -1 ? line : line.slice(0, comma);
}

/** The list a chosen file holds: a `.csv`'s first column, a `.txt` as it is (its lines are the
 * list, and may be separated by commas or spaces too). A leading byte-order mark is dropped. */
export function listFromFile(name: string, text: string): string {
  const body = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const lines = body.split(/\r?\n/);
  const cells = name.toLowerCase().endsWith(".csv") ? lines.map(firstCell) : lines;
  return cells
    .map((cell) => cell.trim())
    .filter((cell) => cell !== "")
    .join("\n");
}

function refusal(status: number, body: Record<string, unknown>, what: string): AddFromListError {
  if (body.error === "too_many_identifiers") {
    return new AddFromListError(
      `${NUMBER.format(Number(body.received ?? 0))} identifiers is more than one request reads, which is ` +
        `${NUMBER.format(Number(body.cap ?? MAX_IDENTIFIERS))}. Nothing was added. Split the list and add it in parts.`,
    );
  }
  if (body.error === "limit_exceeded") {
    return new AddFromListError(
      `Too many for the canvas: ${NUMBER.format(Number(body.would_be ?? 0))} ${String(body.cap_kind ?? "nodes")} ` +
        `against a limit of ${NUMBER.format(Number(body.cap ?? 0))}. Nothing was added. ` +
        "You can branch the case, filter it to part, or promote the list to a batch.",
    );
  }
  if (status === 403) return new AddFromListError("Adding to this case needs Editor access.");
  return new AddFromListError(`${what} (${status}).`);
}

async function post(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  text: string,
  confirm: boolean,
  withLinks: boolean,
): Promise<{ counts: IdentifierCounts; added: { delta: WorkingSetDelta } | null }> {
  let response: Response;
  try {
    response = await fetch(
      `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/working-set/add-by-identifiers`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ identifiers: [text], confirm, with_links: withLinks }),
      },
    );
  } catch {
    throw new AddFromListError("The server could not be reached.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    throw refusal(response.status, body, confirm ? "The list could not be added" : "The list could not be read");
  }
  return (await response.json()) as { counts: IdentifierCounts; added: { delta: WorkingSetDelta } | null };
}

/** Counts a list and adds nothing. */
export async function countIdentifiers(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  text: string,
): Promise<IdentifierCounts> {
  return (await post(apiBaseUrl, bearerToken, investigationId, text, false, false)).counts;
}

/** Adds a list the analyst has seen counted: by default the nodes alone, with `withLinks` the links
 * among them and what is already drawn too. */
export async function addIdentifiers(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  text: string,
  withLinks: boolean,
): Promise<AddedFromList> {
  const answer = await post(apiBaseUrl, bearerToken, investigationId, text, true, withLinks);
  if (!answer.added) throw new AddFromListError("The list could not be added (nothing came back).");
  return { counts: answer.counts, delta: answer.added.delta };
}
