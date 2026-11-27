/**
 * A fixture Conduit for the reader page (slice GG3b): a real HTTP server on a free port that RECORDS every call and REFUSES what the
 * real routes refuse (rule 15: a fixture that only grants proves the page agrees with our hopes). Synthetic throughout (rule 9).
 *
 * What it refuses, in the real routes' order (`services/api/app.py`, `read_document_route` and `document_file_route`):
 *  - the router first, for anyone: a path it has not is 404 `{"detail": "Not Found"}`; a method the path does not serve is 405
 *    `{"detail": "Method Not Allowed"}` (the reader's and the file's paths are GET alone). Every other path under a case (the
 *    designations, the extraction, the candidates, the upload, the case's own read and the rest the real Conduit serves) is NOT modelled:
 *    500, recorded, never a 404 the real router would not give;
 *  - then who the bearer is: none is 401 `{"detail": "Not authenticated"}` (FastAPI's `HTTPBearer`; a token in the query is ignored);
 *    one it does not know is 401 with the resolver's own reason as the detail (`get_principal`: `detail=str(exc)`);
 *  - then the route-level right (`dependencies=[Depends(require_right(Right.INVESTIGATE))]`, run before the case's gate): without it,
 *    403 `{"detail": {"error": "right_required", "right": "investigate"}}`;
 *  - then the case's gate (`InvestigationViewerDep`): a case that does not exist, one of another unit and one the reader holds no level
 *    on are the same 404 `{"error": "investigation_not_found"}` (Viewer is the lowest level, so no level is too low for a read);
 *  - then the Document (`DocumentReaderService.read`, `DocumentContentService.file`): one not in this case, one above the reader's
 *    clearance, a node that is not a Document, and for the file one with no file held, are the same 404 `{"error": "document_not_found"}`.
 * What it sends, as the route's model does: `DocumentReaderView` with every field (FastAPI sends a field's default too), its spans
 * **with each span whose node the reader may not see left out** (`dossier.get_document_view`'s `narrow_to_visible`, rule 3), in the
 * order of their start (`spans.sort(key=lambda span: span.start)`); the file as its bytes with its own content type, no other header.
 * A test can make the reader's route fail (`reader_answer`, `reader_no_answer`).
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export type Level = "viewer" | "editor" | "author";
export type Provenance = "asserted" | "inferred" | "unresolved";

export interface Reader {
  token: string;
  unit: string;
  rights: string[];
  /** The reader's level on each case, by id: a case not named is one they hold no level on. */
  levels: Record<string, Level>;
  /** The highest marking they may read: a node marked above it is one they may not see (a number, for the fixture alone). */
  clearance: number;
}

export interface Span {
  start: number;
  end: number;
  node_id: string;
  entity_type: string;
  provenance_state: Provenance;
  /** The marking of the span's node; absent, every reader of the document may see it. */
  marking?: number;
}

export interface Doc {
  case_id: string;
  id: string;
  /** `Document` for a document; any other is a node the reader route refuses as no document. */
  type?: string;
  marking?: number;
  title: string | null;
  text: string;
  truncated: boolean;
  spans: Span[];
  sent_at: string | null;
  sender_id: string | null;
  recipient_id: string | null;
  edge_id: string | null;
  event_id: string | null;
  media_kind: string | null;
  has_file: boolean;
  /** The held file: absent with `has_file` true, the file is missing from the store (the route's 404). */
  file?: { bytes: Buffer; type: string };
}

export interface Case {
  id: string;
  owning_unit: string;
}

export interface Call {
  method: string;
  url: string;
  headers: IncomingHttpHeaders;
}

export interface Canned {
  status: number;
  body: unknown;
}

export interface DocumentConduitOptions {
  readers: Reader[];
  cases: Case[];
  documents: Doc[];
  reader_answer?: Canned;
  reader_no_answer?: boolean;
}

export interface DocumentConduit {
  url: string;
  calls: Call[];
  stop(): Promise<void>;
}

/** A 1x1 PNG: a real picture, so a browser can be seen to load it (synthetic: one grey pixel). */
export const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");

export const NOT_FOUND_CASE = { error: "investigation_not_found" };
export const NOT_FOUND_DOCUMENT = { error: "document_not_found" };
/** The resolver's reason for a bearer it does not know: one of its own sentences (`packages/principal_auth`), standing for all. */
export const UNKNOWN_BEARER = "token is missing required claim: subject ('sub')";
export const RIGHT_REFUSAL = { detail: { error: "right_required", right: "investigate" } };

/** What the Conduit sends for a document to this reader (`DocumentReaderView`): a span whose node they may not see is left out. */
export const readerViewOf = (d: Doc, reader: Pick<Reader, "clearance">): Record<string, unknown> => ({
  document_id: d.id,
  title: d.title,
  text: d.text,
  truncated: d.truncated,
  spans: d.spans
    .filter((s) => (s.marking ?? 0) <= reader.clearance)
    .map((s) => ({ start: s.start, end: s.end, node_id: s.node_id, entity_type: s.entity_type, provenance_state: s.provenance_state })),
  sent_at: d.sent_at,
  sender_id: d.sender_id,
  recipient_id: d.recipient_id,
  edge_id: d.edge_id,
  event_id: d.event_id,
  media_kind: d.media_kind,
  has_file: d.has_file,
});

const ROUTE = /^\/v1\/investigations\/([^/]+)\/documents\/([^/]+)\/(reader|file)$/;

export async function documentConduit(options: DocumentConduitOptions): Promise<DocumentConduit> {
  const calls: Call[] = [];
  const server: Server = createServer((req, res) => {
    const url = req.url ?? "/";
    calls.push({ method: req.method ?? "", url, headers: req.headers });
    req.on("data", () => undefined);
    req.on("end", () => answer(req, res, url));
  });
  const answer = (req: IncomingMessage, res: ServerResponse, url: string): void => {
    const send = (status: number, body: unknown): void => {
      res.statusCode = status;
      if (typeof body === "string") {
        res.setHeader("Content-Type", "text/plain");
        res.end(body);
        return;
      }
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(body));
    };
    const path = url.split("?")[0] ?? "";
    const method = req.method ?? "";
    // The router answers first, as FastAPI's does.
    const match = ROUTE.exec(path);
    if (!match) {
      if (/^\/v1\/investigations(?:\/.*)?$/.test(path)) return send(500, { detail: "the fixture Conduit does not model this route" });
      return send(404, { detail: "Not Found" });
    }
    if (method !== "GET") return send(405, { detail: "Method Not Allowed" });
    const caseId = decodeURIComponent(match[1] as string);
    const documentId = decodeURIComponent(match[2] as string);
    const route = match[3] as "reader" | "file";
    const header = req.headers["authorization"];
    const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    if (token === undefined) return send(401, { detail: "Not authenticated" });
    const reader = options.readers.find((r) => r.token === token);
    if (!reader) return send(401, { detail: UNKNOWN_BEARER });
    // The route-level right, before the case's gate.
    if (!reader.rights.includes("investigate")) return send(403, RIGHT_REFUSAL);
    // The case's gate: no such case, another unit, no level: one 404.
    const found = options.cases.find((c) => c.id === caseId);
    if (!found || found.owning_unit !== reader.unit || reader.levels[found.id] === undefined) return send(404, NOT_FOUND_CASE);
    // The Document: not in this case, above the reader, not a Document: one 404.
    const doc = options.documents.find((d) => d.case_id === caseId && d.id === documentId);
    if (!doc || (doc.marking ?? 0) > reader.clearance || (doc.type ?? "Document") !== "Document") return send(404, NOT_FOUND_DOCUMENT);
    if (route === "file") {
      if (!doc.has_file || doc.file === undefined) return send(404, NOT_FOUND_DOCUMENT);
      res.statusCode = 200;
      res.setHeader("Content-Type", doc.file.type);
      res.end(doc.file.bytes);
      return;
    }
    if (options.reader_no_answer === true) return void req.socket.destroy();
    if (options.reader_answer) return send(options.reader_answer.status, options.reader_answer.body);
    send(200, readerViewOf(doc, reader));
  };
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    stop: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}
