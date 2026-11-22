/**
 * The Ingest Studio's frame and its Releases screen, as server-rendered pages of the Default tree (slice IS5a; ADR-152
 * decisions 5, 7 and 12; ADR-140 Amendment 9 decision 4). The routes, and the view models their templates draw:
 *
 *   GET  /studio            the frame: the dataset switch, the readiness strip, the Needs-you reminder, the five places
 *   GET  /studio/releases   the frame with Releases in it: export (a GET form), its files and each file's download
 *   POST /studio/releases   the import's steps, each a form: `upload` (the folder, multipart), `check`, `import`
 *
 * Every read and write is made as the person (`conduit.ts`: their bearer, the Conduit's own address) and the Conduit
 * authorises each (rules 3 and 4). The page's checks of a right are words, and they are made again on every POST so that a
 * person without the right gets the words and no data. A refusal says the same for a dataset that is not the person's and a
 * right they do not hold. The release folder is held between steps by `staging.ts` and nowhere else: never rendered into a
 * page or its data block, never in a URL, a cookie or a log line.
 */
import type { Request, Response } from "express";

import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Conduit } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import { formKind } from "./csrf.js";
import type { PageModule } from "./pages.js";
import type { SessionStore } from "./sessionStore.js";
import { MAX_FOLDER_BYTES, MAX_FOLDER_FILES, StagedTooLarge, heldBy } from "./staging.js";
import type { Held, Staged } from "./staging.js";
import { UploadRefusal, drainBody, readUploadForm } from "./upload.js";
import type { UploadedForm } from "./upload.js";
import {
  NEEDS_YOU_WORDS,
  PLACES,
  RELEASE_WORDS,
  STUDIO_WORDS,
  bundlePath,
  caseForDataset,
  currentDataset,
  downloadName,
  isDeployed,
  placeHref,
  planView,
  refusalWords,
  releaseName,
  rightName,
  stripItems,
  studioDatasets,
  whyNot,
} from "./views/studioWords.js";
import type { CaseListing, Pipeline, Plan, PlanView, Run, Source, StudioPlace } from "./views/studioWords.js";

interface Studio {
  forward: ForwardSettings | undefined;
  store: SessionStore;
  clock: () => number;
  log: (message: string) => void;
  bodyStallMs: number;
}

const studioOf = (req: Request): Studio => req.app.locals["studio"] as Studio;

/** A query or form value that is one string, else undefined: an array or an object is not what a page's own form sends. */
function one(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

const MAX_ID_CHARS = 200;

// -------------------------------------------------------------------------------------------------- what is read

interface NeedsYou {
  proposals: { dataset_id: string; to_decide: number }[];
}

/** Everything the frame draws, read as the person. */
interface Frame {
  path: string;
  place: StudioPlace | "frame";
  caseId: string | null;
  conduit: Conduit | undefined;
  /** The words for a case list that could not be read (or for a session that has ended); null when it was read. */
  casesProblem: string | null;
  cases: CaseListing[];
  servingCase: CaseListing | undefined;
  datasets: { id: string; name: string; selected: boolean }[];
  datasetId: string | null;
  datasetName: string;
  switchProblem: string | null;
  openingNote: string | null;
  rights: ReadonlySet<string> | null;
  roles: string[] | null;
  proposed: number;
  needsUnread: boolean;
  strip: string[] | null;
  pipelinesProblem: boolean;
  tabs: { id: string; label: string; href: string; current: boolean }[];
  reminder: { text: string; tip: string; href: string } | null;
}

/** A read the page makes, or `undefined` when it did not work: a failed read is never an empty answer (rule 2), the caller says so. */
async function read(conduit: Conduit, path: string, query?: Record<string, string>): Promise<unknown> {
  try {
    const reply = await conduit({ path, ...(query ? { query } : {}) });
    return reply.status === 200 ? reply.json : undefined;
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

const asList = (value: unknown): unknown[] | undefined => (Array.isArray(value) ? value : undefined);

function needsOf(value: unknown): NeedsYou | undefined {
  const body = value as { proposals?: unknown; promotions_overdue?: unknown } | undefined;
  if (!body || !Array.isArray(body.proposals) || !Array.isArray(body.promotions_overdue)) return undefined;
  return { proposals: body.proposals as NeedsYou["proposals"] };
}

/** Says the Studio cannot be shown, in words, with no answer from the Conduit in it. */
function unavailable(res: Response, status = 503): void {
  res.status(status).render("error", {
    title: "The Studio is not available",
    message: "The Studio cannot reach the service just now. Nothing has changed. Try again in a few minutes.",
  });
}

/**
 * Reads what the frame draws for `caseId` and answers a dataset switch. Returns the frame, or `"sent"` when it has already
 * answered (a switch to another case is a redirect; the service being unreachable is a page of words).
 */
async function loadFrame(
  req: Request,
  res: Response,
  options: { path: string; place: Frame["place"]; caseId: string | undefined; wantsDataset?: string; opening?: string },
): Promise<Frame | "sent"> {
  const st = studioOf(req);
  const auth = req.session.auth;
  if (!auth || !st.forward) {
    unavailable(res);
    return "sent";
  }
  const caseId = options.caseId !== undefined && options.caseId !== "" && options.caseId.length <= MAX_ID_CHARS ? options.caseId : null;
  const empty: Frame = {
    path: options.path,
    place: options.place,
    caseId,
    conduit: undefined,
    casesProblem: null,
    cases: [],
    servingCase: undefined,
    datasets: [],
    datasetId: null,
    datasetName: "this dataset",
    switchProblem: null,
    openingNote: null,
    rights: null,
    roles: null,
    proposed: 0,
    needsUnread: false,
    strip: null,
    pipelinesProblem: false,
    tabs: [],
    reminder: null,
  };
  if (caseId === null) return empty;
  let conduit: Conduit;
  try {
    conduit = await conduitFor(st.forward, auth, st.log);
  } catch {
    st.log("pages: studio: the person's access could not be prepared (502)");
    unavailable(res, 502);
    return "sent";
  }
  const [casesReply, rightsRaw, meRaw, needsRaw] = await Promise.all([
    conduit({ path: v1("investigations") }).catch((error: unknown) => {
      if (error instanceof ConduitUnreachable) return undefined;
      throw error;
    }),
    // (the cases are read for their status too: an ended session is said as one, not as an unreadable list)
    read(conduit, v1("me", "rights")),
    read(conduit, v1("me")),
    read(conduit, v1("me", "needs-you")),
  ]);
  const cases = casesReply?.status === 200 ? (asList(casesReply.json) as CaseListing[] | undefined) : undefined;
  const rightsList = asList((rightsRaw as { rights?: unknown } | undefined)?.rights);
  const rights = rightsList ? new Set(rightsList.filter((r): r is string => typeof r === "string")) : null;
  const rolesList = asList((meRaw as { roles?: unknown } | undefined)?.roles);
  const roles = rolesList ? rolesList.filter((r): r is string => typeof r === "string") : null;
  const needs = needsOf(needsRaw);
  const frame: Frame = {
    ...empty,
    conduit,
    rights,
    roles,
    needsUnread: needs === undefined,
    casesProblem: cases !== undefined ? null : casesReply?.status === 401 ? refusalWords(401, undefined, "") : STUDIO_WORDS.casesUnreadable,
  };
  if (cases !== undefined) {
    frame.cases = cases;
    frame.servingCase = cases.find((c) => c.id === caseId);
    frame.datasetId = currentDataset(cases, caseId);
    frame.datasets = studioDatasets(cases, caseId).map((d) => ({ ...d, selected: d.id === frame.datasetId }));
    frame.datasetName = frame.datasets.find((d) => d.id === frame.datasetId)?.name ?? "this dataset";
    // The dataset switch (and a Needs-you request for a dataset): the case that serves it, or words.
    const wanted = options.wantsDataset;
    if (wanted !== undefined) {
      const target = caseForDataset(cases, wanted, caseId);
      if (target === null) {
        frame.switchProblem = STUDIO_WORDS.switchRefused;
      } else if (target !== caseId) {
        const carried = options.opening === "model" ? `&opening=model&dataset=${encodeURIComponent(wanted)}` : "";
        res.redirect(303, `${options.path}?case=${encodeURIComponent(target)}${carried}`);
        return "sent";
      }
    }
  }
  // What the proposals count is the Conduit's, for this dataset only: never a total, never another dataset's.
  frame.proposed = needs?.proposals.find((p) => p.dataset_id === frame.datasetId)?.to_decide ?? 0;
  if (options.opening === "model" && options.wantsDataset !== undefined && options.wantsDataset === frame.datasetId && frame.switchProblem === null) {
    frame.openingNote = STUDIO_WORDS.needsYouCame(frame.proposed, frame.datasetName);
  }
  if (frame.datasetId !== null) await readStrip(frame, conduit, caseId, frame.datasetId);
  frame.tabs = PLACES.map((place) => ({
    id: place.id,
    label: place.id === "model" && frame.proposed > 0 ? `${place.label} · ${frame.proposed} proposed` : place.label,
    href: placeHref(place, caseId),
    current: place.id === frame.place,
  }));
  const model = PLACES[0];
  if (frame.proposed > 0 && frame.place !== "model" && model) {
    frame.reminder = { text: NEEDS_YOU_WORDS.reminder(frame.proposed), tip: NEEDS_YOU_WORDS.reminderTip, href: placeHref(model, caseId) };
  }
  return frame;
}

/** The readiness strip's reads: the case's pipelines, each deployed one's runs, and the dataset's registered sources. */
async function readStrip(frame: Frame, conduit: Conduit, caseId: string, datasetId: string): Promise<void> {
  const [registryRaw, sourcesRaw] = await Promise.all([
    read(conduit, v1("investigations", caseId, "ingest", "recipe-registry")),
    read(conduit, v1("datasets", datasetId, "sources")),
  ]);
  const registry = asList(registryRaw) as Pipeline[] | undefined;
  const sources = (asList(sourcesRaw) as Source[] | undefined) ?? "unreadable";
  const runs: Record<string, Run[]> = {};
  let pipelines: Pipeline[] | "unreadable" = "unreadable";
  if (registry !== undefined) {
    pipelines = registry.filter((p) => p.status !== "superseded");
    const deployed = pipelines.filter(isDeployed);
    await Promise.all(
      deployed.map(async (p) => {
        const found = asList(await read(conduit, v1("investigations", caseId, "ingest", "recipes", String(p.recipe_id), "runs")));
        // A pipeline whose runs the person may not read is absent, not shown as never run.
        if (found !== undefined) runs[String(p.recipe_id)] = found as Run[];
      }),
    );
  }
  frame.pipelinesProblem = pipelines === "unreadable";
  frame.strip = stripItems({ packs: frame.servingCase?.domains, pipelines, sources, runs });
}

// ------------------------------------------------------------------------------------------------- the templates

/** What every Studio template draws: the frame's parts, and the anti-forgery token for its forms. */
function context(req: Request, frame: Frame, extra: Record<string, unknown>): Record<string, unknown> {
  return {
    page: "studio",
    csrfToken: req.session.auth?.csrfToken,
    words: STUDIO_WORDS,
    needsWords: NEEDS_YOU_WORDS,
    release: RELEASE_WORDS,
    f: frame,
    help: {
      rolesRead: frame.roles !== null,
      roles: frame.roles ?? [],
      rights: frame.rights === null ? null : [...frame.rights].sort().map(rightName),
    },
    ...extra,
  };
}

// --------------------------------------------------------------------------------------------------- the frame page

export const studioFrame: PageModule = {
  id: "studio-frame",
  path: "/studio",
  methods: ["GET"],
  handler: async (req, res) => {
    const frame = await loadFrame(req, res, {
      path: "/studio",
      place: "frame",
      caseId: one(req.query["case"]),
      ...(one(req.query["dataset"]) === undefined ? {} : { wantsDataset: one(req.query["dataset"]) as string }),
      ...(one(req.query["opening"]) === undefined ? {} : { opening: one(req.query["opening"]) as string }),
    });
    if (frame === "sent") return;
    res.render("studio/index", context(req, frame, { title: "Ingest Studio" }));
  },
};

// -------------------------------------------------------------------------------------------------- the Releases page

/** What the Releases template draws beyond the frame. */
interface ReleaseView {
  name: string;
  version: string;
  mayExport: boolean;
  mayImport: boolean;
  whyExport: string | null;
  whyImport: string | null;
  exported: { count: number; leftOut: number; files: { path: string; href: string; download: string }[]; cli: string } | null;
  problem: string | null;
  staged: { count: number } | null;
  check: { view: PlanView; clean: boolean; replacesOwn: boolean; confirmed: boolean } | null;
  /** Whether Import is offered: the held folder's last check was clean. */
  clean: boolean;
  written: PlanView | null;
  /** The held folder's token, for the steps' forms (a hidden field: never an address). */
  token: string | null;
}

const EXPORT_NEEDS = ["edit_target_model", "publish_pipelines"] as const;
const IMPORT_NEEDS = ["edit_target_model", "edit_pipelines"] as const;

function releaseView(frame: Frame, over: Partial<ReleaseView> = {}): ReleaseView {
  const has = (needs: readonly string[]): boolean => frame.rights === null || needs.every((right) => frame.rights?.has(right));
  return {
    name: releaseName(frame.datasetName),
    version: "1",
    mayExport: has(EXPORT_NEEDS),
    mayImport: has(IMPORT_NEEDS),
    whyExport: whyNot(frame.rights, EXPORT_NEEDS),
    whyImport: whyNot(frame.rights, IMPORT_NEEDS),
    exported: null,
    problem: null,
    staged: null,
    check: null,
    clean: false,
    written: null,
    token: null,
    ...over,
  };
}

function renderReleases(req: Request, res: Response, frame: Frame, view: ReleaseView, status = 200): void {
  res.status(status).render("studio/releases", context(req, frame, { title: "Ingest Studio · Releases", rel: view, refusal: view.problem }));
}

/** The export, asked of the Conduit as the person: its files, or the words for why not. */
async function askExport(
  conduit: Conduit,
  datasetId: string,
  name: string,
  version: string,
): Promise<{ files: Record<string, string>; leftOut: number } | { problem: string }> {
  try {
    const reply = await conduit({ path: v1("datasets", datasetId, "release"), query: { name, version } });
    const body = reply.json as { files?: unknown; left_out?: unknown } | undefined;
    if (reply.status === 200 && body && typeof body.files === "object" && body.files !== null) {
      const files = body.files as Record<string, unknown>;
      if (Object.values(files).every((text) => typeof text === "string")) {
        return { files: files as Record<string, string>, leftOut: typeof body.left_out === "number" ? body.left_out : 0 };
      }
    }
    return { problem: refusalWords(reply.status === 200 ? 502 : reply.status, reply.json, "The export") };
  } catch (error) {
    if (error instanceof ConduitUnreachable) return { problem: refusalWords(502, undefined, "The export") };
    throw error;
  }
}

async function releasesGet(req: Request, res: Response): Promise<void> {
  const frame = await loadFrame(req, res, {
    path: "/studio/releases",
    place: "releases",
    caseId: one(req.query["case"]),
    ...(one(req.query["dataset"]) === undefined ? {} : { wantsDataset: one(req.query["dataset"]) as string }),
  });
  if (frame === "sent") return;
  if (frame.caseId === null || frame.datasetId === null || frame.conduit === undefined) {
    renderReleases(req, res, frame, releaseView(frame));
    return;
  }
  const datasetId = frame.datasetId;
  const name = (one(req.query["name"]) ?? releaseName(frame.datasetName)).trim();
  const version = (one(req.query["version"]) ?? "1").trim();
  const view = releaseView(frame, { name, version });
  const download = one(req.query["download"]);
  const asked = download !== undefined || one(req.query["export"]) === "1";
  if (!asked) {
    renderReleases(req, res, frame, view);
    return;
  }
  // The right is checked in words before the Conduit is asked, so that a person without it is not sent to a refusal; the
  // Conduit refuses all the same.
  if (!view.mayExport) {
    renderReleases(req, res, frame, view, 403);
    return;
  }
  const answer = await askExport(frame.conduit, datasetId, name, version);
  if ("problem" in answer) {
    renderReleases(req, res, frame, { ...view, problem: answer.problem }, download === undefined ? 200 : 404);
    return;
  }
  if (download !== undefined) {
    // The file is asked of the Conduit again, never kept: a name the release does not hold is not served.
    const text = Object.hasOwn(answer.files, download) ? answer.files[download] : undefined;
    if (text === undefined) {
      renderReleases(req, res, frame, { ...view, problem: RELEASE_WORDS.notInRelease }, 404);
      return;
    }
    res.status(200);
    res.set("Content-Type", "application/yaml; charset=utf-8");
    res.set("Content-Disposition", `attachment; filename="${downloadName(download)}"`);
    res.send(text);
    return;
  }
  const query = (path: string): string =>
    `/studio/releases?${new URLSearchParams({ case: frame.caseId as string, name, version, download: path }).toString()}`;
  const paths = Object.keys(answer.files);
  renderReleases(req, res, frame, {
    ...view,
    exported: {
      count: paths.length,
      leftOut: answer.leftOut,
      files: paths.map((path) => ({ path, href: query(path), download: downloadName(path) })),
      cli: RELEASE_WORDS.cliHint(datasetId, name, version),
    },
  });
}

/** Whether the held folder's last check was clean, and what the page says about it. */
function stagedView(token: string, folder: Staged): Partial<ReleaseView> {
  return {
    token,
    staged: { count: Object.keys(folder.files).length },
    clean: folder.check?.clean === true,
  };
}

function checkView(plan: Plan, folder: Staged): ReleaseView["check"] {
  return {
    view: planView(plan, plan.dry_run ?? true),
    clean: (plan.refused ?? []).length === 0,
    replacesOwn: plan.replaces_own_draft === true,
    confirmed: folder.check?.confirmed === true,
  };
}

/** The import route, as the Conduit takes it: the whole folder as JSON, a dry run or not, a confirmed version or none. */
async function askImport(
  conduit: Conduit,
  datasetId: string,
  files: Record<string, string>,
  dryRun: boolean,
  replaceVersion: number | null,
): Promise<{ plan: Plan } | { problem: string }> {
  try {
    const reply = await conduit({
      method: "POST",
      path: v1("datasets", datasetId, "release", "import"),
      query: { dry_run: dryRun, ...(replaceVersion === null ? {} : { replace_own_draft: replaceVersion }) },
      json: { files },
    });
    const body = reply.json as Plan | undefined;
    // A refusal at the plan comes back as a plan too (422), with `refused` in words.
    if ((reply.status === 200 || reply.status === 422) && body && Array.isArray(body.refused)) return { plan: body };
    return { problem: refusalWords(reply.status === 200 ? 502 : reply.status, reply.json, "The import") };
  } catch (error) {
    if (error instanceof ConduitUnreachable) return { problem: refusalWords(502, undefined, "The import") };
    throw error;
  }
}

async function releasesPost(req: Request, res: Response): Promise<void> {
  const st = studioOf(req);
  const auth = req.session.auth;
  if (!auth) {
    unavailable(res);
    return;
  }
  const held = heldBy(st.store, req.session, st.clock);
  const multipart = formKind(req.headers["content-type"]) === "multipart";
  let form: UploadedForm | undefined;
  let fields: Record<string, string>;
  // The frame read before the folder's first byte (so a person without the right is refused with it unread), if it was.
  const early: { frame?: Frame | "sent" } = {};

  const gate = (frame: Frame): string | null => {
    if (frame.caseId === null || frame.datasetId === null) return RELEASE_WORDS.noDataset;
    return releaseView(frame).mayImport ? null : RELEASE_WORDS.noImport;
  };

  const frameFor = (caseId: string | undefined): Promise<Frame | "sent"> =>
    loadFrame(req, res, { path: "/studio/releases", place: "releases", caseId });

  if (multipart) {
    try {
      form = await readUploadForm(req, {
        auth,
        maxBytes: MAX_FOLDER_BYTES,
        maxFiles: MAX_FOLDER_FILES,
        stallMs: st.bodyStallMs,
        tooLarge: RELEASE_WORDS.tooLarge,
        // Before a byte of the folder is taken in: a person without the right is refused, with their folder unread.
        beforeFiles: async (found) => {
          early.frame = await frameFor(found["case"]);
          if (early.frame === "sent") throw new UploadRefusal(403, RELEASE_WORDS.noImport);
          const why = gate(early.frame);
          if (why !== null) throw new UploadRefusal(403, why);
        },
      });
    } catch (error) {
      if (!(error instanceof UploadRefusal)) throw error;
      drainBody(req);
      if (error.token) {
        // The anti-forgery check: the page for a refused request, with none of the form in it.
        res.status(403).render("error", {
          title: "Request not carried out",
          message: "This request could not be checked, so it was not carried out. Go back, reload the page and try again.",
        });
        return;
      }
      if (early.frame === "sent") return;
      const frame = early.frame ?? (await frameFor(undefined));
      if (frame === "sent") return;
      renderReleases(req, res, frame, releaseView(frame, { problem: error.words }), error.status);
      return;
    }
    fields = form.fields;
  } else {
    const body: unknown = req.body;
    fields = {};
    if (typeof body === "object" && body !== null) {
      for (const [key, value] of Object.entries(body as Record<string, unknown>)) if (typeof value === "string") fields[key] = value;
    }
  }

  const frame = early.frame ?? (await frameFor(fields["case"]));
  if (frame === "sent") return;
  const closed = gate(frame);
  if (closed !== null) {
    renderReleases(req, res, frame, releaseView(frame, { problem: closed }), frame.caseId === null ? 422 : 403);
    return;
  }
  const datasetId = frame.datasetId as string;
  const caseId = frame.caseId as string;
  const conduit = frame.conduit as Conduit;
  const base = releaseView(frame);

  // ---- the folder sent as a form: read, its paths made, held for the check
  if (form !== undefined) {
    const named = form.files.filter((file) => file.filename !== "");
    if (named.length === 0) {
      renderReleases(req, res, frame, base);
      return;
    }
    const files: Record<string, string> = {};
    for (const file of named) {
      const path = bundlePath(file.filename);
      if (path === null) {
        renderReleases(req, res, frame, { ...base, problem: RELEASE_WORDS.badName }, 422);
        return;
      }
      files[path] = file.data.toString("utf8");
    }
    const folder: Staged = { v: 1, subject: auth.subject, caseId, datasetId, files };
    let token: string;
    try {
      token = await held.put(folder);
    } catch (error) {
      if (!(error instanceof StagedTooLarge)) throw error;
      renderReleases(req, res, frame, { ...base, problem: RELEASE_WORDS.tooLarge }, 413);
      return;
    }
    renderReleases(req, res, frame, { ...base, ...stagedView(token, folder) });
    return;
  }

  // ---- the steps after it: a form with the held folder's token
  const action = fields["action"];
  if (action !== "check" && action !== "import") {
    renderReleases(req, res, frame, { ...base, problem: "That request was not understood." }, 400);
    return;
  }
  const token = fields["staged"] ?? "";
  const folder = await held.get(token);
  // A folder held for another case or dataset is not this page's to use.
  if (folder === null || folder.caseId !== caseId || folder.datasetId !== datasetId) {
    renderReleases(req, res, frame, { ...base, problem: RELEASE_WORDS.gone }, 410);
    return;
  }
  await continueSteps({ req, res, frame, conduit, held, token, folder, base, action, replace: fields["replace"] === "1" });
}

async function continueSteps(input: {
  req: Request;
  res: Response;
  frame: Frame;
  conduit: Conduit;
  held: Held;
  token: string;
  folder: Staged;
  base: ReleaseView;
  action: "check" | "import";
  replace: boolean;
}): Promise<void> {
  const { req, res, frame, conduit, held, token, folder, base, action } = input;
  const datasetId = frame.datasetId as string;
  const shown = (over: Partial<ReleaseView>): ReleaseView => ({ ...base, ...stagedView(token, folder), ...over });

  if (action === "check") {
    // What is confirmed is the importer's own tick, with the version the last check named: never a number the form sent.
    const confirmed = input.replace;
    const version = confirmed ? (folder.check?.ownDraftVersion ?? null) : null;
    const answer = await askImport(conduit, datasetId, folder.files, true, version);
    if ("problem" in answer) {
      renderReleases(req, res, frame, shown({ problem: answer.problem }));
      return;
    }
    folder.check = { clean: (answer.plan.refused ?? []).length === 0, ownDraftVersion: answer.plan.own_draft_version ?? null, confirmed };
    await held.save(token, folder);
    renderReleases(req, res, frame, shown({ check: checkView(answer.plan, folder), clean: folder.check.clean }));
    return;
  }

  // Import: only after a clean check of this folder, which the page holds and the form cannot claim.
  if (folder.check?.clean !== true) {
    renderReleases(req, res, frame, shown({ problem: RELEASE_WORDS.checkFirst }));
    return;
  }
  const confirmed = folder.check.confirmed;
  const answer = await askImport(conduit, datasetId, folder.files, false, confirmed ? folder.check.ownDraftVersion : null);
  if ("problem" in answer) {
    renderReleases(req, res, frame, shown({ problem: answer.problem }));
    return;
  }
  if ((answer.plan.refused ?? []).length > 0) {
    // A refusal at the write (a draft someone opened since the check, say) wrote nothing: it is shown as a refused check, so a
    // new check goes on from it.
    folder.check = { clean: false, ownDraftVersion: answer.plan.own_draft_version ?? null, confirmed };
    await held.save(token, folder);
    renderReleases(req, res, frame, shown({ check: checkView(answer.plan, folder), clean: false }));
    return;
  }
  await held.drop(token);
  renderReleases(req, res, frame, { ...base, written: planView(answer.plan, answer.plan.dry_run ?? false) });
}

export const studioReleases: PageModule = {
  id: "studio-releases",
  path: "/studio/releases",
  methods: ["GET", "POST"],
  upload: true,
  handler: async (req, res) => {
    if (req.method === "POST") await releasesPost(req, res);
    else await releasesGet(req, res);
  },
};
