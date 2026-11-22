/**
 * The route-module convention (ADR-152 decision 6): a page is a module exporting `{ id, path, methods, handler }`.
 *
 * - `id` is the page's row in `FUNCTIONS.yaml`: the function it gives the GOV.UK tree parity with, so a page that names no
 *   row is a page nobody planned;
 * - `path` is a plain path (no pattern), not one the server owns, and claimed by no other page;
 * - `methods` are the methods the page answers, and no others (a method not listed is a page that is not there);
 * - `handler` builds the page's view model and renders its template.
 *
 * The server registers every page through `registerPages`, which checks the list when the app is made, so a mistake is a
 * refusal to start, in words, and never a route that quietly does the wrong thing. Every page route sits behind the
 * session (an unsigned request is sent to sign-in, as the home page sends it) and, being registered after the anti-forgery
 * check, behind that for every method but GET: nothing a page's author writes can leave either out.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { RequestHandler, Router } from "express";

export type PageMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface PageModule {
  id: string;
  path: string;
  methods: readonly PageMethod[];
  handler: RequestHandler;
  /**
   * The page takes a browser's file upload as a `multipart/form-data` POST (slice IS5a). Its handler must read the body
   * with `readUploadForm` (`upload.ts`), which checks the anti-forgery token as the form's first part before any file is
   * read: the check in `csrf.ts` leaves a multipart body of exactly these paths to it. Needs POST among `methods`.
   */
  upload?: boolean;
}

/** A page list that cannot be served: the message says which page and what is wrong, in words. */
export class PageRegistrationError extends Error {
  override name = "PageRegistrationError";
}

/**
 * A plain path is lower case with no trailing slash. Express matches a route ignoring case and an optional trailing slash, so
 * `/studio`, `/Studio` and `/studio/` are one route: allowing them would let two pages claim one route under two spellings (the
 * later never reached), and a page take `/Healthz`, which the health route answers first. Refusing the spellings, rather than
 * comparing paths after folding them, leaves one spelling for a path everywhere it is written (a link, a test, a log line).
 */
const PLAIN_PATH = /^\/(?:[a-z0-9._~-]+(?:\/[a-z0-9._~-]+)*)?$/;
const METHODS: readonly string[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];
/** Paths the server answers itself: a page may not take one, or sit under one (`/` is the home page). */
const OWNED = ["/session", "/healthz", "/assets/pages", "/v1"];
/** `FUNCTIONS.yaml` beside the package (`dist/FUNCTIONS.yaml` in the build, which copies it). */
const FUNCTIONS_FILE = fileURLToPath(new URL("../FUNCTIONS.yaml", import.meta.url));

/** The ids of `FUNCTIONS.yaml`'s rows: each `  - id: <slug>` line of its `functions:` list. */
export function functionIdsFromFile(file: string = FUNCTIONS_FILE): ReadonlySet<string> {
  let text: string;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    throw new PageRegistrationError(`FUNCTIONS.yaml could not be read at ${file}, so no page's id can be checked`);
  }
  const ids = new Set([...text.matchAll(/^ {2}- id: (\S+)\s*$/gm)].map((match) => match[1] as string));
  if (ids.size === 0) throw new PageRegistrationError(`FUNCTIONS.yaml at ${file} has no rows, so no page's id can be checked`);
  return ids;
}

function owned(path: string): boolean {
  return path === "/" || OWNED.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
}

/** Throws, in words, for the first fault in the list. */
function check(pages: readonly PageModule[], known: ReadonlySet<string>): void {
  const byPath = new Map<string, PageModule>();
  const byId = new Map<string, PageModule>();
  for (const page of pages) {
    const where = `the page ${JSON.stringify(page.id)} at ${JSON.stringify(page.path)}`;
    if (typeof page.id !== "string" || !known.has(page.id)) {
      throw new PageRegistrationError(
        `${where} names an id that is not a row of FUNCTIONS.yaml. A page's id is its FUNCTIONS.yaml row; add the row first.`,
      );
    }
    if (typeof page.path !== "string" || !PLAIN_PATH.test(page.path) || page.path.includes("//") || page.path.split("/").includes("..")) {
      throw new PageRegistrationError(
        `${where} has a path that is not a plain path: write it with lower-case letters, digits and hyphens, starting with a slash and ending with none.`,
      );
    }
    if (owned(page.path)) {
      throw new PageRegistrationError(`${where} takes a path the server answers itself (the home page, /session, /healthz, /assets/pages and /v1).`);
    }
    if (page.upload === true && !page.methods.includes("POST")) {
      throw new PageRegistrationError(`${where} takes an upload but does not answer POST: a file is sent by a POST.`);
    }
    if (page.methods.length === 0) throw new PageRegistrationError(`${where} lists no method: say which of GET, POST, PUT, PATCH and DELETE it answers.`);
    for (const method of page.methods) {
      if (!METHODS.includes(method)) {
        throw new PageRegistrationError(`${where} lists the method ${String(method)}, which a page cannot answer: use GET, POST, PUT, PATCH or DELETE.`);
      }
    }
    const sameId = byId.get(page.id);
    if (sameId) {
      throw new PageRegistrationError(`the id ${page.id} is used by more than one page (${sameId.path} and ${page.path}): a page is one row of FUNCTIONS.yaml.`);
    }
    const samePath = byPath.get(page.path);
    if (samePath) {
      throw new PageRegistrationError(
        `two pages claim the path ${page.path}: ${samePath.id} and ${page.id}. A path belongs to one page, whatever methods each lists.`,
      );
    }
    byId.set(page.id, page);
    byPath.set(page.path, page);
  }
}

/** The paths of the pages that take a file upload: the anti-forgery check leaves a multipart body there to the page's own reader. */
export function uploadPathsOf(pages: readonly PageModule[]): ReadonlySet<string> {
  return new Set(pages.filter((page) => page.upload === true).map((page) => page.path));
}

/** Sends a request with no session to sign-in, as the home page does, before the page's handler is reached. */
const signedIn: RequestHandler = (req, res, next) => {
  if (!req.session?.auth) {
    res.redirect(302, "/session/sign-in");
    return;
  }
  next();
};

/**
 * Checks the list now and returns the function that mounts it. The router it is given is the one behind the headers, the
 * session and the anti-forgery check.
 */
export function registerPages(pages: readonly PageModule[], known?: ReadonlySet<string>): (router: Router) => void {
  check(pages, known ?? (pages.length > 0 ? functionIdsFromFile() : new Set()));
  return (router) => {
    for (const page of pages) {
      for (const method of page.methods) {
        router[method.toLowerCase() as "get" | "post" | "put" | "patch" | "delete"](page.path, signedIn, page.handler);
      }
    }
  };
}
