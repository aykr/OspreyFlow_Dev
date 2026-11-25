// For the copy guards only (`copyWords.test.ts`, `copyNoClient.test.ts`): never imported by the app.
//
// What is read: every string literal, template literal and line of JSX text in the Glass's source, by
// the TypeScript parser, so identifiers, imports and comments are never read as copy. A token holding a
// slash, a hyphen or an underscore (a route, a path, `oidc-client`, `client_id`) is a name, not a word on
// screen, and is dropped from the text. Tests and generated types are not on screen and are skipped.
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";

import ts from "typescript";
import { beforeAll } from "vitest";

export const SRC = join(__dirname);
/** The shared package's source, where the plain modules that left the workspace live (slices PL4c to PL4d2):
 * the Conduit clients there hold copy a person is shown, so the guards read it as they read `SRC`. */
export const SHARED_SRC = join(__dirname, "..", "..", "..", "packages", "glass-shared", "src");
/** The roots the guards walk: the one list every copy guard and its reach test use. */
export const ROOTS: readonly string[] = [SRC, SHARED_SRC];

/** The walks made so far, by the roots walked (PL4h). Each guard file used to walk and read the whole source again in
 * every test (seven calls a file, 1.5 to 2 s alone and 5.4 to 7 s under a loaded server, past vitest's 5 s): a list of
 * roots is now walked once per file and its list shared. Nothing is kept across test files: each vitest file has its
 * own module, so each pays the walk once, in the hook below. */
const walks = new Map<string, readonly string[]>();

/** `walk` made once for each list of roots: the first call walks, every later call returns a copy of the list it found.
 * Only the roots' own listing is kept: what a test writes into a folder after its first walk is not listed again. */
function walkedOnce(walk: (roots?: readonly string[]) => string[]): (roots?: readonly string[]) => string[] {
  return (roots = ROOTS) => {
    const key = roots.join("\0");
    let found = walks.get(key);
    if (!found) {
      found = walk(roots);
      walks.set(key, found);
    }
    return [...found];
  };
}

/** The files under `roots` (by default both), skipping tests, test kits and generated types: the walk, made once for
 * each list of roots (`walkedOnce`). */
export const sourceFiles = walkedOnce(function sourceFiles(roots: readonly string[] = ROOTS): string[] {
  return roots.flatMap((root) => filesUnder(root));
});

/** A fresh walk of `dir` on disc, never the shared one: for the tests that hold the shared one to what the disc says. */
export function walkOnDisc(dir: string): string[] {
  return filesUnder(dir);
}

// The one walk of the two real roots, and the one reading and parsing of every file in them, are paid here, in a hook of
// their own, not inside whichever test runs first. Its timeout is explicit and explained (never raised for the suite
// or the config): the walk and the parse read and parse two folders of a few hundred files (1.5 to 2 s alone), and a
// loaded server has made the same work take 5.4 to 7 s, so a minute is far past the slowest figure seen and still
// ends a walk that hangs. Every test after it reads the walk and the parsed texts from memory.
beforeAll(() => {
  for (const path of sourceFiles()) copyTexts(path, readFileSync(path, "utf-8"));
}, 60_000);

/** The path as the guards print it: relative to its own root, the shared package's marked. */
export function shown(path: string): string {
  return path.startsWith(SHARED_SRC) ? `glass-shared/${relative(SHARED_SRC, path)}` : relative(SRC, path);
}

/** The folders of the shared package the Conduit clients came from: the Ingest Studio's and Admin's (PL4d2) and the
 * reports', export's, alerts', patterns' and models' (PL4d3a), and the inspector's, link types', questions', reader's,
 * dossier's, views', working set's, boards' and analytics' (PL4d3b), and the assessment's, connections', explore's, map's,
 * metrics', ownership's, search's, site's, strength's and watches' (PL4d3c), and the roles' (`help`), Home's (`home`) and the
 * entity pictures' (`canvas`) (PL4d3e). One regular expression on one line, which
 * `test_glass_shared_report_clients.py`, `test_glass_shared_link_clients.py` and `test_glass_shared_plain_clients.py` read. */
export const MOVED_FOLDERS = /\/(ingest|admin|reports|export|alerts|patterns|models|inspector|linktypes|questions|reader|dossier|views|workingset|boards|analytics|assessment|connections|explore|map|metrics|ownership|search|site|strength|watches|investigation|time|help|home|canvas)\//;

/** The twelve clients and words PL4d3a moved: a folder, then each file's stem. Never written as a path (the old-path scan in
 * `test_glass_shared_report_clients.py` reads this file too, and only the package's own place may name them). */
const REPORT_STEMS: Record<string, readonly string[]> = {
  reports: ["api", "caseHttp", "dashboards", "trendsApi", "packsApi", "packText"],
  export: ["api"],
  alerts: ["api", "names", "closingReasons"],
  patterns: ["api"],
  models: ["modelDeadline"],
};
/** Their places under the shared package. A guard that plants in each of them reads this list, so a file that moved back or
 * went missing fails the plant, not only the walk. */
export const REPORT_CLIENTS: readonly string[] = Object.entries(REPORT_STEMS).flatMap(([folder, stems]) =>
  stems.map((stem) => `${folder}/${stem}.ts`),
);

/** The sixteen clients PL4d3b moved: a folder, then each file's stem. Never written as a path, as above. */
const LINK_STEMS: Record<string, readonly string[]> = {
  inspector: ["emailDocuments", "linkChangeApi", "linkEventsApi", "linkNotesApi"],
  linktypes: ["http", "linkTypesApi", "modelProposalsApi"],
  questions: ["questionsApi", "graphFacts"],
  reader: ["readerApi"],
  dossier: ["api", "models"],
  views: ["viewsApi"],
  workingset: ["batchExpansionApi"],
  boards: ["promotionsApi"],
  analytics: ["api"],
};
/** Their places under the shared package, for the guards that plant in each of them. */
export const LINK_CLIENTS: readonly string[] = Object.entries(LINK_STEMS).flatMap(([folder, stems]) =>
  stems.map((stem) => `${folder}/${stem}.ts`),
);

/** The twelve clients PL4d3c moved: a folder, then each file's stem. Never written as a path, as above. */
const PLAIN_STEMS: Record<string, readonly string[]> = {
  assessment: ["api"],
  boards: ["boardsApi"],
  connections: ["connectionsApi"],
  explore: ["exploreApi"],
  map: ["providers"],
  metrics: ["api"],
  ownership: ["api"],
  search: ["addFromListApi"],
  site: ["api", "bilinear"],
  strength: ["api"],
  watches: ["api"],
};
/** Their places under the shared package, for the guards that plant in each of them. */
export const PLAIN_CLIENTS: readonly string[] = Object.entries(PLAIN_STEMS).flatMap(([folder, stems]) =>
  stems.map((stem) => `${folder}/${stem}.ts`),
);

/** The seven files PL4d3d added: a folder, then each file's stem. Never written as a path, as above. */
const CASE_STEMS: Record<string, readonly string[]> = {
  investigation: ["cases"],
  time: ["utcStamp"],
  "admin/needsYou": ["needsYouApi", "openings"],
  "ingest/studio": ["datasets", "packs"],
  "ingest/runs": ["externalOrchestrationApi"],
};
/** Their places under the shared package, for the guards that plant in each of them. */
export const CASE_CLIENTS: readonly string[] = Object.entries(CASE_STEMS).flatMap(([folder, stems]) =>
  stems.map((stem) => `${folder}/${stem}.ts`),
);

/** The six files PL4d3e added: a folder, then each file's stem. Never written as a path, as above. */
const ADMIN_STEMS: Record<string, readonly string[]> = {
  help: ["roles"],
  admin: ["api"],
  home: ["guides", "homeData"],
  reports: ["ruleGroup"],
  canvas: ["entityPictures"],
};
/** Their places under the shared package, for the guards that plant in each of them. */
export const ADMIN_CLIENTS: readonly string[] = Object.entries(ADMIN_STEMS).flatMap(([folder, stems]) =>
  stems.map((stem) => `${folder}/${stem}.ts`),
);

/** The Conduit clients and the notice that live in the shared package: every file there under the folders the
 * clients came from, found on disc rather than named, so a client added later is walked and checked too. */
export function movedClients(): string[] {
  // From the walk of both roots every test already shares, not a walk of the shared package alone (a second list of roots
  // would be a second walk, PL4h): the shared package's files are the ones of that walk under `SHARED_SRC`.
  return sourceFiles()
    .filter((path) => path.startsWith(SHARED_SRC))
    .filter((path) => MOVED_FOLDERS.test(path));
}

/** A temporary copy of the shared package, walked on disc once when it is made and that list entered in `walks`, so a
 * plant's own walk and tests read the copy's files as the disc lists them, and a cleanup that forgets it. */
function copySharedPackage(): { root: string; remove: () => void } {
  const root = mkdtempSync(join(tmpdir(), "copy-guard-"));
  cpSync(SHARED_SRC, root, { recursive: true });
  walks.set(root, filesUnder(root));
  return {
    root,
    remove: () => {
      walks.delete(root);
      rmSync(root, { recursive: true, force: true });
    },
  };
}

/** A copy of the shared package in a temporary folder, with `line` appended to its file named `basename`; returns the
 * folder, that file's path relative to it, and a cleanup. For the guards' plants (rule 15): the plant sits in a real
 * moved client, and the guard's own walk and test are run over the copy. */
export function plantedCopy(basename: string, line: string): { root: string; file: string; remove: () => void } {
  const { root, remove } = copySharedPackage();
  const target = sourceFiles([root]).find((path) => path.endsWith(`/${basename}`));
  if (!target) throw new Error(`no ${basename} in the shared package`);
  writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  return { root, file: relative(root, target), remove };
}

/** A copy of the shared package with `line` appended to each of the twelve report clients; returns the folder, the files'
 * paths relative to it (in `REPORT_CLIENTS`' order), and a cleanup. The report guards' plants (rule 15): one in each. */
export function plantedReportClients(line: string): { root: string; files: string[]; remove: () => void } {
  const { root, remove } = copySharedPackage();
  for (const file of REPORT_CLIENTS) {
    const target = join(root, file);
    writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  }
  return { root, files: [...REPORT_CLIENTS], remove };
}

/** A copy of the shared package with `line` appended to each of the sixteen link clients; returns the folder, the files'
 * paths relative to it (in `LINK_CLIENTS`' order), and a cleanup. The link guards' plants (rule 15): one in each. */
export function plantedLinkClients(line: string): { root: string; files: string[]; remove: () => void } {
  const { root, remove } = copySharedPackage();
  for (const file of LINK_CLIENTS) {
    const target = join(root, file);
    writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  }
  return { root, files: [...LINK_CLIENTS], remove };
}

/** A copy of the shared package with `line` appended to each of the twelve plain clients; returns the folder, the files'
 * paths relative to it (in `PLAIN_CLIENTS`' order), and a cleanup. The plain guards' plants (rule 15): one in each. */
export function plantedPlainClients(line: string): { root: string; files: string[]; remove: () => void } {
  const { root, remove } = copySharedPackage();
  for (const file of PLAIN_CLIENTS) {
    const target = join(root, file);
    writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  }
  return { root, files: [...PLAIN_CLIENTS], remove };
}

/** A copy of the shared package with `line` appended to each of the seven case files; returns the folder, the files'
 * paths relative to it (in `CASE_CLIENTS`' order), and a cleanup. The case guards' plants (rule 15): one in each. */
export function plantedCaseClients(line: string): { root: string; files: string[]; remove: () => void } {
  const { root, remove } = copySharedPackage();
  for (const file of CASE_CLIENTS) {
    const target = join(root, file);
    writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  }
  return { root, files: [...CASE_CLIENTS], remove };
}

/** A copy of the shared package with `line` appended to each of the six admin and home files; returns the folder, the files'
 * paths relative to it (in `ADMIN_CLIENTS`' order), and a cleanup. The guards' plants (rule 15): one in each. */
export function plantedAdminClients(line: string): { root: string; files: string[]; remove: () => void } {
  const { root, remove } = copySharedPackage();
  for (const file of ADMIN_CLIENTS) {
    const target = join(root, file);
    writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  }
  return { root, files: [...ADMIN_CLIENTS], remove };
}

function filesUnder(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "generated" || entry.name === "node_modules" ? [] : filesUnder(path);
    return /\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec)\./.test(entry.name) && !/TestKit\.ts$/.test(entry.name)
      ? [path]
      : [];
  });
}

export type CopyText = { line: number; words: string; raw: string };

const parsed = new Map<string, CopyText[]>();

/** Each piece of copy in `source`: its line, its words without name-like tokens, and its raw text. Parsed once for each
 * source and kind of file (`.tsx` or not) and shared (PL4h): the guards' plants copy a package whose files are mostly
 * the very text already parsed, and the name does not change the reading but for the kind of file. */
export function copyTexts(name: string, source: string): CopyText[] {
  const key = `${name.endsWith(".tsx") ? "tsx" : "ts"}\0${source}`;
  let found = parsed.get(key);
  if (!found) {
    found = parseCopyTexts(name, source);
    parsed.set(key, found);
  }
  return found;
}

function parseCopyTexts(name: string, source: string): CopyText[] {
  const tree = ts.createSourceFile(
    name,
    source,
    ts.ScriptTarget.Latest,
    true,
    name.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const found: CopyText[] = [];
  const visit = (node: ts.Node): void => {
    let raw: string | null = null;
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) raw = node.text;
    else if (ts.isTemplateExpression(node))
      raw = [node.head.text, ...node.templateSpans.map((span) => span.literal.text)].join("");
    else if (ts.isJsxText(node)) raw = node.text;
    const quoted = node.parent && (ts.isImportDeclaration(node.parent) || ts.isExportDeclaration(node.parent));
    if (raw !== null && !quoted) {
      const words = raw
        .split(/\s+/)
        .filter((token) => token && !/[/_]/.test(token) && !/\w-\w/.test(token))
        .join(" ");
      found.push({ line: tree.getLineAndCharacterOfPosition(node.getStart()).line + 1, words, raw });
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return found;
}
