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

export const SRC = join(__dirname);
/** The shared package's source, where the plain modules that left the workspace live (slices PL4c to PL4d2):
 * the Conduit clients there hold copy a person is shown, so the guards read it as they read `SRC`. */
export const SHARED_SRC = join(__dirname, "..", "..", "..", "packages", "glass-shared", "src");
/** The roots the guards walk: the one list every copy guard and its reach test use. */
export const ROOTS: readonly string[] = [SRC, SHARED_SRC];

/** The files under `roots` (by default both), skipping tests, test kits and generated types. */
export function sourceFiles(roots: readonly string[] = ROOTS): string[] {
  return roots.flatMap((root) => filesUnder(root));
}

/** The path as the guards print it: relative to its own root, the shared package's marked. */
export function shown(path: string): string {
  return path.startsWith(SHARED_SRC) ? `glass-shared/${relative(SHARED_SRC, path)}` : relative(SRC, path);
}

/** The folders of the shared package the Conduit clients came from: the Ingest Studio's and Admin's (PL4d2) and the
 * reports', export's, alerts', patterns' and models' (PL4d3a), and the inspector's, link types', questions', reader's,
 * dossier's, views', working set's, boards' and analytics' (PL4d3b). One regular expression on one line, which
 * `test_glass_shared_report_clients.py` and `test_glass_shared_link_clients.py` read. */
export const MOVED_FOLDERS = /\/(ingest|admin|reports|export|alerts|patterns|models|inspector|linktypes|questions|reader|dossier|views|workingset|boards|analytics)\//;

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

/** The Conduit clients and the notice that live in the shared package: every file there under the folders the
 * clients came from, found on disc rather than named, so a client added later is walked and checked too. */
export function movedClients(): string[] {
  return sourceFiles([SHARED_SRC]).filter((path) => MOVED_FOLDERS.test(path));
}

/** A copy of the shared package in a temporary folder, with `line` appended to its file named `basename`; returns the
 * folder, that file's path relative to it, and a cleanup. For the guards' plants (rule 15): the plant sits in a real
 * moved client, and the guard's own walk and test are run over the copy. */
export function plantedCopy(basename: string, line: string): { root: string; file: string; remove: () => void } {
  const root = mkdtempSync(join(tmpdir(), "copy-guard-"));
  cpSync(SHARED_SRC, root, { recursive: true });
  const target = sourceFiles([root]).find((path) => path.endsWith(`/${basename}`));
  if (!target) throw new Error(`no ${basename} in the shared package`);
  writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  return { root, file: relative(root, target), remove: () => rmSync(root, { recursive: true, force: true }) };
}

/** A copy of the shared package with `line` appended to each of the twelve report clients; returns the folder, the files'
 * paths relative to it (in `REPORT_CLIENTS`' order), and a cleanup. The report guards' plants (rule 15): one in each. */
export function plantedReportClients(line: string): { root: string; files: string[]; remove: () => void } {
  const root = mkdtempSync(join(tmpdir(), "copy-guard-"));
  cpSync(SHARED_SRC, root, { recursive: true });
  for (const file of REPORT_CLIENTS) {
    const target = join(root, file);
    writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  }
  return { root, files: [...REPORT_CLIENTS], remove: () => rmSync(root, { recursive: true, force: true }) };
}

/** A copy of the shared package with `line` appended to each of the sixteen link clients; returns the folder, the files'
 * paths relative to it (in `LINK_CLIENTS`' order), and a cleanup. The link guards' plants (rule 15): one in each. */
export function plantedLinkClients(line: string): { root: string; files: string[]; remove: () => void } {
  const root = mkdtempSync(join(tmpdir(), "copy-guard-"));
  cpSync(SHARED_SRC, root, { recursive: true });
  for (const file of LINK_CLIENTS) {
    const target = join(root, file);
    writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  }
  return { root, files: [...LINK_CLIENTS], remove: () => rmSync(root, { recursive: true, force: true }) };
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

/** Each piece of copy in `source`: its line, its words without name-like tokens, and its raw text. */
export function copyTexts(name: string, source: string): CopyText[] {
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
