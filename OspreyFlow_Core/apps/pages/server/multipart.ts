/**
 * A streaming reader for a `multipart/form-data` body (RFC 7578), for the browser's form upload with scripts
 * off (ADR-152 decision 5, F1; slice PL10). Written here rather than taken from a package: it is one state
 * machine, it needs no dependency (so nothing new enters the licence register), and every case of it is in
 * `test/server/forward.test.ts`.
 *
 * It never holds more than one chunk and a boundary's length of the file: the file part's bytes go to the
 * handler's sink as they arrive, with the sink's backpressure honoured. A field is held whole (it is small, and
 * capped). What it refuses, it refuses with a `MultipartRefusal` carrying the status and the words:
 * a body that is not multipart, a part with no name, a header block or a field over its cap, a body that ends
 * before its closing boundary.
 */

const MAX_HEADER_BYTES = 16 * 1024;
const MAX_FIELD_BYTES = 8 * 1024;
const MAX_FIELDS = 64;
const MAX_NAME_CHARS = 200;

export class MultipartRefusal extends Error {
  constructor(
    readonly status: 413 | 422,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "MultipartRefusal";
  }
}

export interface FileSink {
  write(chunk: Buffer): Promise<void>;
}

export interface MultipartHandler {
  /** A field of the form, whole. Throws a `MultipartRefusal` to refuse the form. */
  field(name: string, value: string): void;
  /** The start of a file part. Throws a `MultipartRefusal` to refuse the form. */
  file(name: string, filename: string): FileSink | Promise<FileSink>;
  /** The file part's last byte has gone to its sink. */
  fileEnd(): void;
}

const unreadable = (): MultipartRefusal => new MultipartRefusal(422, "The form could not be read. Go back and send it again.");

/** The boundary a `Content-Type` of `multipart/form-data` names, or undefined when it has none a body could use. */
export function boundaryOf(contentType: string | undefined): string | undefined {
  if (contentType === undefined) return undefined;
  const found = /;\s*boundary\s*=\s*(?:"([^"]{1,70})"|([^\s;"]{1,70}))/i.exec(contentType);
  const boundary = found?.[1] ?? found?.[2];
  // RFC 2046: 1 to 70 characters of a small set, not ending in a space.
  if (boundary === undefined || !/^[0-9A-Za-z'()+_,\-./:=? ]{1,70}$/.test(boundary) || boundary.endsWith(" ")) return undefined;
  return boundary;
}

interface Disposition {
  name: string;
  filename?: string;
}

function decodeExtended(value: string): string | undefined {
  // RFC 5987: charset'language'percent-encoded. Only UTF-8 is read.
  const found = /^([A-Za-z0-9-]+)'[^']*'(.*)$/.exec(value.trim());
  if (!found || found[1]?.toLowerCase() !== "utf-8") return undefined;
  try {
    return decodeURIComponent(found[2] ?? "");
  } catch {
    return undefined;
  }
}

function parseDisposition(head: string): Disposition {
  let value: string | undefined;
  for (const line of head.split("\r\n")) {
    const colon = line.indexOf(":");
    if (colon > 0 && line.slice(0, colon).trim().toLowerCase() === "content-disposition") value = line.slice(colon + 1);
  }
  if (value === undefined || !/^\s*form-data\s*(;|$)/i.test(value)) throw unreadable();
  const param = (key: string): string | undefined => {
    const found = new RegExp(`;\\s*${key}\\s*=\\s*(?:"((?:[^"\\\\]|\\\\.)*)"|([^;\\s]*))`, "i").exec(value);
    if (!found) return undefined;
    return found[1] !== undefined ? found[1].replace(/\\(.)/g, "$1") : (found[2] ?? "");
  };
  const name = param("name");
  if (name === undefined || name === "" || name.length > MAX_NAME_CHARS) throw unreadable();
  const extended = /;\s*filename\*\s*=\s*([^;]+)/i.exec(value);
  const filename = (extended?.[1] === undefined ? undefined : decodeExtended(extended[1])) ?? param("filename");
  return filename === undefined ? { name } : { name, filename };
}

type State = "preamble" | "after" | "headers" | "body" | "done";

/**
 * Reads `source` (the request's body, in chunks) as a multipart body with this `boundary`. Resolves when the
 * closing boundary has been read; rejects with `MultipartRefusal` for a form it will not carry, or with the
 * source's own error (a browser that went away).
 */
export async function readMultipart(source: AsyncIterable<Buffer>, boundary: string, handler: MultipartHandler): Promise<void> {
  const delimiter = Buffer.from(`\r\n--${boundary}`);
  const keep = delimiter.length - 1;
  // The first boundary has no CRLF before it unless there is a preamble: treat the body as if one were there.
  let buf: Buffer = Buffer.from("\r\n");
  let state: State = "preamble";
  let field: { name: string; chunks: Buffer[]; size: number } | undefined;
  let sink: FileSink | undefined;
  let fields = 0;

  const emit = async (data: Buffer): Promise<void> => {
    if (data.length === 0) return;
    if (sink) {
      await sink.write(data);
    } else if (field) {
      field.size += data.length;
      if (field.size > MAX_FIELD_BYTES) throw new MultipartRefusal(422, "A field of the form is too long.");
      field.chunks.push(data);
    }
  };

  const endPart = (): void => {
    if (field) {
      handler.field(field.name, Buffer.concat(field.chunks).toString("utf8"));
      field = undefined;
    } else if (sink) {
      sink = undefined;
      handler.fileEnd();
    }
  };

  const step = async (): Promise<void> => {
    for (;;) {
      if (state === "preamble") {
        const at = buf.indexOf(delimiter);
        if (at < 0) {
          buf = buf.subarray(Math.max(0, buf.length - keep));
          return;
        }
        buf = buf.subarray(at + delimiter.length);
        state = "after";
      } else if (state === "after") {
        if (buf.length < 2) return;
        if (buf[0] === 0x2d && buf[1] === 0x2d) {
          state = "done";
          buf = Buffer.alloc(0);
          return;
        }
        const crlf = buf.indexOf("\r\n");
        if (crlf < 0) {
          if (buf.length > 1024) throw unreadable();
          return;
        }
        // Only blank padding may sit between a boundary and its line's end: anything else is a longer boundary.
        if (!/^[ \t]*$/.test(buf.subarray(0, crlf).toString("latin1"))) throw unreadable();
        buf = buf.subarray(crlf + 2);
        state = "headers";
      } else if (state === "headers") {
        const end = buf.indexOf("\r\n\r\n");
        if (end < 0) {
          if (buf.length > MAX_HEADER_BYTES) throw unreadable();
          return;
        }
        if (end > MAX_HEADER_BYTES) throw unreadable();
        const disposition = parseDisposition(buf.subarray(0, end).toString("utf8"));
        buf = buf.subarray(end + 4);
        if (disposition.filename !== undefined) {
          sink = await handler.file(disposition.name, disposition.filename);
        } else {
          fields += 1;
          if (fields > MAX_FIELDS) throw new MultipartRefusal(422, "The form has too many fields.");
          field = { name: disposition.name, chunks: [], size: 0 };
        }
        state = "body";
      } else if (state === "body") {
        const at = buf.indexOf(delimiter);
        if (at >= 0) {
          await emit(buf.subarray(0, at));
          endPart();
          buf = buf.subarray(at + delimiter.length);
          state = "after";
          continue;
        }
        const safe = buf.length - keep;
        if (safe > 0) {
          await emit(buf.subarray(0, safe));
          buf = buf.subarray(safe);
        }
        return;
      } else {
        buf = Buffer.alloc(0);
        return;
      }
    }
  };

  for await (const chunk of source) {
    buf = buf.length === 0 ? chunk : Buffer.concat([buf, chunk]);
    await step();
  }
  if ((state as State) !== "done") throw new MultipartRefusal(422, "The form ended before it was complete. Go back and send it again.");
}
