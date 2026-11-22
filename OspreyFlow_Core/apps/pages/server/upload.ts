/**
 * A browser's file upload to a page route, scripts off (slice IS5a): a `multipart/form-data` POST read by the page itself.
 *
 * It is the page-route counterpart of the forwarder's form reader (`forward.ts`), and keeps its discipline: the anti-forgery
 * token must be the form's FIRST part and right, or nothing is read (`csrf.ts` leaves a multipart body of an `upload` page to
 * this reader); every field must come before the first file; and before a byte of the first file is read a hook the route
 * gives is asked, so a person without the right is refused without their file being taken in. Files are held in memory up to
 * a cap, never written to disk, and never passed to a log. What it refuses it refuses with an `UploadRefusal`: a status and
 * words.
 */
import type { Request } from "express";

import { BodyStalled, untilStalled } from "./bodyStall.js";
import { CSRF_REFUSED, tokensMatch } from "./csrf.js";
import { MultipartRefusal, boundaryOf, readMultipart } from "./multipart.js";
import type { FileSink } from "./multipart.js";
import type { SessionRecord } from "./sessionPolicy.js";

export class UploadRefusal extends Error {
  constructor(
    readonly status: 403 | 408 | 413 | 422,
    readonly words: string,
    /** The refusal is the anti-forgery check's: the form is not shown again, its words are the general ones. */
    readonly token: boolean = false,
  ) {
    super(words);
    this.name = "UploadRefusal";
  }
}

export interface UploadedFile {
  /** The name the browser sent: for a folder, its relative path (`bundle/pipelines/a.yaml`). */
  filename: string;
  data: Buffer;
}

export interface UploadedForm {
  fields: Record<string, string>;
  files: UploadedFile[];
}

export interface UploadOptions {
  auth: SessionRecord;
  /** The most file bytes, over all the files. */
  maxBytes: number;
  /** The most files. */
  maxFiles: number;
  stallMs: number;
  /** The words for a form that is over `maxBytes`. */
  tooLarge: string;
  /** The words for a form that has more than `maxFiles` files. */
  tooMany: string;
  /** Asked once the fields are in and before the first file's first byte: throw an `UploadRefusal` to refuse the upload. */
  beforeFiles?: (fields: Readonly<Record<string, string>>) => Promise<void>;
}

const UNREADABLE = "The form could not be read. Go back and send it again.";

/** Reads the form, or throws an `UploadRefusal`. The request's body is read here and nowhere else. */
export async function readUploadForm(req: Request, options: UploadOptions): Promise<UploadedForm> {
  const boundary = boundaryOf(req.headers["content-type"]);
  if (boundary === undefined) throw new UploadRefusal(422, UNREADABLE);
  const declared = req.headers["content-length"];
  // A declared length well over the cap is refused before a byte is read (the form's own envelope is small).
  if (declared !== undefined && /^\d+$/.test(declared) && Number(declared) > options.maxBytes + 1024 * 1024) {
    throw new UploadRefusal(413, options.tooLarge);
  }
  const fields: Record<string, string> = {};
  const files: UploadedFile[] = [];
  let parts = 0;
  let verified = false;
  let filesStarted = false;
  let size = 0;
  let finish: (() => void) | undefined;
  try {
    await readMultipart(untilStalled(req.iterator({ destroyOnReturn: false }) as AsyncIterable<Buffer>, options.stallMs), boundary, {
      field(name, value) {
        const first = parts === 0;
        parts += 1;
        if (name === "_csrf") {
          if (!verified) {
            if (!first || !tokensMatch(value, options.auth.csrfToken)) throw new MultipartRefusal(403, CSRF_REFUSED);
            verified = true;
          }
          return;
        }
        if (!verified) throw new MultipartRefusal(403, CSRF_REFUSED);
        if (filesStarted) throw new MultipartRefusal(422, "The form's fields must come before its files. Go back and send it again.");
        fields[name] = value;
      },
      async file(_name, filename): Promise<FileSink> {
        // No proof, no upload: before a byte of any file is read.
        if (!verified) throw new MultipartRefusal(403, CSRF_REFUSED);
        if (!filesStarted) {
          filesStarted = true;
          try {
            await options.beforeFiles?.(fields);
          } catch (error) {
            if (error instanceof UploadRefusal) throw new MultipartRefusal(error.status === 403 ? 403 : 422, error.words);
            throw error;
          }
        }
        if (files.length >= options.maxFiles) throw new MultipartRefusal(413, options.tooMany);
        const chunks: Buffer[] = [];
        finish = (): void => {
          files.push({ filename, data: Buffer.concat(chunks) });
        };
        return {
          async write(chunk) {
            size += chunk.length;
            if (size > options.maxBytes) throw new MultipartRefusal(413, options.tooLarge);
            chunks.push(chunk);
          },
        };
      },
      fileEnd() {
        // The file's last byte has gone to its sink: it is kept whole.
        finish?.();
        finish = undefined;
      },
    });
  } catch (error) {
    if (error instanceof MultipartRefusal) throw new UploadRefusal(error.status, error.detail, error.detail === CSRF_REFUSED);
    if (error instanceof UploadRefusal) throw error;
    if (error instanceof BodyStalled) throw new UploadRefusal(408, "The form stopped arriving, so it was ended. Nothing was changed. Go back and send it again.");
    throw error;
  }
  if (!verified) throw new UploadRefusal(403, CSRF_REFUSED, true);
  return { fields, files };
}

/** After a refusal: take what the browser is still sending, up to a limit and a time, so that it can read the answer. */
export function drainBody(req: Request): void {
  let seen = 0;
  req.on("data", (chunk: Buffer) => {
    seen += chunk.length;
    if (seen > 1024 * 1024) req.destroy();
  });
  req.resume();
  const timer = setTimeout(() => req.destroy(), 5000);
  timer.unref();
  req.once("close", () => clearTimeout(timer));
}
