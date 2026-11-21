/**
 * The built browser assets (ADR-152 decision 7): `apps/pages/scripts/assets.mjs` writes one stylesheet and the client modules, each
 * under a content-hashed name, and a manifest saying which file is which. This serves that folder at `/assets/pages/*`
 * and nothing else.
 *
 * Served with no session, mounted before the session is read: a sign-in page needs its stylesheet, and an asset is the
 * same for everyone. Every refusal is a plain 404 that names nothing, so a probe learns nothing about the folder.
 * Only GET and HEAD are answered; any other method is 405. A file is served only if
 *   - its path, once decoded, is made of plain segments: no `..`, no empty segment, no segment that starts with a dot, no
 *     backslash or NUL (so a `..%2f`, a `%2e%2e` or a dotfile is refused before the disk is touched), and
 *   - it is a regular file whose real path is inside the folder (a link out of it is refused), and
 *   - its name carries a content hash (`name-ABCD1234.css`, or a folder named by one), because only a file named for its
 *     content may be cached for a year as immutable, and
 *   - its type is one the build writes (a stylesheet, a script, a font, an image).
 * The build's own `manifest.json` has no hash and is not served.
 */
import { existsSync, readFileSync, realpathSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, sep } from "node:path";
import type { RequestHandler } from "express";

export type AssetManifest = Readonly<Record<string, string>>;

export interface AssetsSetting {
  /** The folder `apps/pages/scripts/assets.mjs` wrote. */
  dir: string;
  /** Logical name (`pages.css`, `modules/<name>.ts`) to the hashed file name inside `dir`. */
  manifest: AssetManifest;
}

export const ASSETS_PREFIX = "/assets/pages";
export const IMMUTABLE = "public, max-age=31536000, immutable";

const TYPES: Readonly<Record<string, string>> = {
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

const HASH = "[A-Z0-9]{8}";
const HASHED_NAME = new RegExp(`-${HASH}\\.[a-z0-9]+$`);
const HASHED_FOLDER = new RegExp(`^${HASH}$`);

/** True when a decoded relative path names a file by its content. */
export function isHashed(relative: string): boolean {
  const parts = relative.split("/");
  const name = parts[parts.length - 1] ?? "";
  return HASHED_NAME.test(name) || parts.slice(0, -1).some((part) => HASHED_FOLDER.test(part));
}

/** The decoded segments of a path, or `undefined` for one that is not plain. */
function plainSegments(rest: string): string[] | undefined {
  let decoded: string;
  try {
    decoded = decodeURIComponent(rest);
  } catch {
    return undefined;
  }
  if (decoded.includes("\0") || decoded.includes("\\")) return undefined;
  const segments = decoded.split("/").filter((_, index, all) => !(index === 0 && all[0] === ""));
  if (segments.length === 0) return undefined;
  if (segments.some((s) => s === "" || s.startsWith("."))) return undefined;
  return segments;
}

function notFound(res: Parameters<RequestHandler>[1]): void {
  res.status(404).type("text/plain").send("Not found");
}

/** The handler for everything under `/assets/pages`, mounted with `app.use(ASSETS_PREFIX, ...)`. */
export function assetsHandler(dir: string): RequestHandler {
  const root = realpathSync(resolve(dir));
  return (req, res) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.set("Allow", "GET, HEAD").status(405).type("text/plain").send("Method not allowed");
      return;
    }
    const segments = plainSegments(req.url.split("?")[0] ?? "");
    const relative = segments?.join("/");
    const extension = relative === undefined ? null : /\.[A-Za-z0-9]+$/.exec(relative);
    const type = extension ? TYPES[extension[0].toLowerCase()] : undefined;
    if (relative === undefined || type === undefined || !isHashed(relative)) {
      notFound(res);
      return;
    }
    const wanted = resolve(root, relative);
    if (!wanted.startsWith(root + sep) || !existsSync(wanted)) {
      notFound(res);
      return;
    }
    const real = realpathSync(wanted);
    if (!real.startsWith(root + sep) || !statSync(real).isFile()) {
      notFound(res);
      return;
    }
    // The page headers say `no-store` for a person's page; an asset is the opposite, so both are set here, whole.
    res.set("Cache-Control", IMMUTABLE).type(type);
    res.sendFile(real, { dotfiles: "deny", cacheControl: false, lastModified: false }, (error) => {
      if (error && !res.headersSent) notFound(res);
    });
  };
}

/** The URL of a built asset, for the layout and a page's script tag. A name the build did not make is an error, never an empty link. */
export function assetUrl(manifest: AssetManifest | undefined, name: string): string {
  const file = manifest?.[name];
  if (file === undefined) {
    throw new Error(`the page asks for the built asset "${name}", which the asset build did not make (run npm run build)`);
  }
  return `${ASSETS_PREFIX}/${file}`;
}

/** Reads the build's manifest from a folder, or `undefined` when there is none. */
export function loadAssets(dir: string): AssetsSetting | undefined {
  const file = resolve(dir, "manifest.json");
  if (!existsSync(file)) return undefined;
  const manifest = JSON.parse(readFileSync(file, "utf8")) as AssetManifest;
  return { dir: resolve(dir), manifest };
}

/**
 * Where the built assets are for this process: beside the compiled server (`dist/assets`, from `dist/server`) or, running from
 * the sources, in `dist/assets` of the package. `undefined` when the assets have not been built.
 */
export function defaultAssets(): AssetsSetting | undefined {
  for (const relative of ["../assets", "../dist/assets"]) {
    const found = loadAssets(fileURLToPath(new URL(relative, import.meta.url)));
    if (found) return found;
  }
  return undefined;
}
