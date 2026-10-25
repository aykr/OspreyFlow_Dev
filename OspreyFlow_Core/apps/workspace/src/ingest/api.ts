// Fetch wrappers for `/v1/ingest/*` and `/v1/handling-scheme`
// (`services/api/app.py`) — mirrors `site/api.ts`'s convention exactly.
// `ConnectorCatalogueEntry`/`ConnectDraftInput`/`StudioRecipeDraft` are
// generated from `packages/schemas/ingest.py`; `HandlingScheme` is not —
// it lives in `packages/ontology/handling.py`, outside the schemas
// package's generated-types registry, so it is hand-typed here the same
// way `Site` is hand-typed (Conduit-local metadata, not something this
// project generates a type for).
import type {
  ConnectDraftInput,
  ConnectorCatalogueEntry,
  LoadReport,
  MapHandlingPreviewRequest,
  MapHandlingPreviewResult,
  MapSampleRow,
  OntologySchema,
  PipelineRunReport,
  PublishRecipeInput,
  RowTemplate,
  SchedulePreview,
  ScheduleRunView,
  ScheduleUpdateInput,
  SourceProfile,
  StudioRecipeDraft,
  TransformDescriptor,
  UnmappedField,
  VerifyReport,
  PipelineGraph,
  DomainPackEntry,
} from "../../../../packages/schemas/generated";

export interface HandlingCode {
  label: string;
  dissemination: "permitted" | "conditional" | "restricted";
}

export interface ActionCode {
  label: string;
  direct_action: boolean;
  originator_permission?: boolean;
}

export interface SanitisationCode {
  label: string;
  consult_originator: boolean;
}

export interface HandlingScheme {
  name: string;
  classification: string[];
  handling_codes: Record<string, HandlingCode>;
  /** The route always sends both (ADR-102 reads them); optional so a test's own scheme may omit
   * what it does not use. */
  action_codes?: Record<string, ActionCode>;
  sanitisation_codes?: Record<string, SanitisationCode>;
}

/** ADR-099 Amendment 3: a recipe and a source file are the dataset's, asked of the case. The
 * connector and transform catalogues stay global. */
function studioCase(apiBaseUrl: string, investigationId: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}`;
}

function authHeaders(bearerToken: string): HeadersInit {
  return { Authorization: `Bearer ${bearerToken}` };
}

async function parseOrThrow<T>(response: Response, action: string): Promise<T> {
  if (!response.ok) {
    throw new Error(`${action} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

/** Owner ruling R6, 27 September 2026 — one entry in the deployment's ingest root. The analyst
 * picks one of these instead of typing a path, which is the whole point: in a rendered
 * deployment there is no path they could have typed that the Conduit can read. */
export interface IngestSourceFile {
  name: string;
  source_location: string;
  size_bytes: number;
  modified_at: number;
  /** True for a file the analyst uploaded from the browser (ADR-067), false for one an operator
   * placed in the ingest folder. */
  uploaded?: boolean;
}

export interface IngestSourceListing {
  root: string;
  files: IngestSourceFile[];
}

/** `GET /v1/ingest/source-files` (`09_INGEST_STUDIO.md` §2, "the ingest root"). Needs
 * `StudioRole.SOURCE_AUTHOR`; a principal without it gets 403 and this throws, which Connect
 * renders as "you cannot browse the ingest folder" rather than as an empty folder — an empty
 * list and a refusal mean very different things to an analyst. */
export async function fetchIngestSourceFiles(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<IngestSourceListing> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/source-files`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/source-files");
}

/** The file types the server accepts for upload (`services/api/ingest_sources.py`'s
 * `UPLOAD_EXTENSIONS`), handed to the system file picker so it only offers files the server will
 * take. The server remains the authority; this only saves an analyst a refusal. */
export const UPLOAD_ACCEPT = [
  ".csv", ".tsv", ".txt", ".json", ".xml", ".xlsx",
  ".pdf", ".docx", ".rtf", ".eml", ".msg", ".html", ".htm",
  ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic",
  ".wav", ".mp3", ".m4a", ".mp4",
  ".zip", ".tar", ".gz", ".tgz",
].join(","); // prettier-ignore

/** `POST /v1/ingest/source-files?name=` (ADR-067, which amends ruling R6) — send the analyst's own
 * file, as the raw request body, into the deployment's `uploaded` folder. A refusal (bad name,
 * unsupported type, name already used, too large, no role) throws an `Error` whose message is the
 * sentence the server gave, so Connect can show it as it is. */
export async function uploadIngestSourceFile(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  file: File,
): Promise<IngestSourceFile> {
  const response = await fetch(
    `${studioCase(apiBaseUrl, investigationId)}/ingest/source-files?name=${encodeURIComponent(file.name)}`,
    {
      method: "POST",
      headers: { ...authHeaders(bearerToken), "Content-Type": "application/octet-stream" },
      body: file,
    },
  );
  if (!response.ok) {
    let reason = `The upload was refused (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) reason = body.detail;
    } catch {
      // The body was not JSON; the status line above is all there is to say.
    }
    if (response.status === 403) reason = "You do not hold the source-author role, so you cannot upload files.";
    throw new Error(reason);
  }
  return (await response.json()) as IngestSourceFile;
}

export async function fetchConnectorCatalogue(
  apiBaseUrl: string,
  bearerToken: string,
): Promise<ConnectorCatalogueEntry[]> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/connectors`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/connectors");
}

export async function fetchHandlingScheme(
  apiBaseUrl: string,
  bearerToken: string,
): Promise<HandlingScheme> {
  const response = await fetch(`${apiBaseUrl}/v1/handling-scheme`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/handling-scheme");
}

/** Thrown by `createDraft`/`updateDraft` on a 403, so the screen can tell
 * "you don't hold the role" apart from any other failure. */
export class ForbiddenError extends Error {}

async function parseDraftOrThrow(response: Response, action: string): Promise<StudioRecipeDraft> {
  if (response.status === 403) {
    throw new ForbiddenError(`${action}: principal lacks the required studio role`);
  }
  // ADR-127 Amendment 2: a source whose declared units or marking columns cannot stand is refused
  // with the cause in `detail` (coded, or FastAPI's validation list); the analyst reads that
  // sentence, not a bare status.
  if (response.status === 422) {
    let cause: string | null = null;
    try {
      const body = (await response.json()) as { error?: unknown; detail?: unknown };
      if (body.error === "source_declarations_invalid" && typeof body.detail === "string") cause = body.detail;
      // FastAPI's own list, for a body `ConnectDraftInput` refuses before the route runs.
      else if (Array.isArray(body.detail)) {
        const first = (body.detail[0] as { msg?: unknown } | undefined)?.msg;
        if (typeof first === "string" && first) cause = first;
      }
    } catch {
      // Not a JSON body; the status line below is all there is to say.
    }
    throw new Error(cause ?? `${action} failed: ${response.status}`);
  }
  return parseOrThrow(response, action);
}

export async function createDraft(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  input: ConnectDraftInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseDraftOrThrow(response, "POST /v1/ingest/recipes");
}

export async function updateDraft(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  input: ConnectDraftInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}`, {
    method: "PATCH",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseDraftOrThrow(response, "PATCH /v1/ingest/recipes/{id}");
}

export async function fetchDraft(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/recipes/{id}");
}

export async function listDrafts(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<StudioRecipeDraft[]> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/recipes");
}

/** Thrown by `fetchProfile` on any non-2xx response, carrying the typed
 * `error` code `services/api/app.py`'s exception handlers attach —
 * `recipe_not_ready_for_profile`, `connector_not_available`,
 * `source_unreadable` or `source_handling_incomplete` — so the Profile
 * screen can show the analyst what actually went wrong rather than a bare
 * HTTP status. */
export class ProfileError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function parseCodedErrorOrThrow<T>(response: Response, action: string): Promise<T> {
  if (!response.ok) {
    let body: { error?: unknown; detail?: unknown } = {};
    try {
      body = await response.json();
    } catch {
      // Not a JSON error body — fall through with the generic detail below.
    }
    const code = typeof body.error === "string" ? body.error : "unknown_error";
    const detail = typeof body.detail === "string" ? body.detail : `${action}: ${response.status}`;
    throw new ProfileError(code, detail);
  }
  return (await response.json()) as T;
}

export async function fetchProfile(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<SourceProfile> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/profile`, {
    headers: authHeaders(bearerToken),
  });
  return parseCodedErrorOrThrow(response, "GET /v1/ingest/recipes/{id}/profile");
}

// --- Map (09_INGEST_STUDIO.md §4) -------------------------------------------

export async function fetchOntologySchema(
  apiBaseUrl: string,
  bearerToken: string,
): Promise<OntologySchema> {
  const response = await fetch(`${apiBaseUrl}/v1/ontology`, { headers: authHeaders(bearerToken) });
  return parseOrThrow(response, "GET /v1/ontology");
}

export async function fetchTransforms(
  apiBaseUrl: string,
  bearerToken: string,
): Promise<TransformDescriptor[]> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/transforms`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/transforms");
}

/** Same coded-error shape as `fetchProfile` — `recipe_not_ready_for_profile`
 * chief among them, since Map is unreachable until Profile has run. */
export async function fetchSampleRow(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  rowIndex: number,
): Promise<MapSampleRow> {
  const response = await fetch(
    `${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/map/sample-rows/${rowIndex}`,
    { headers: authHeaders(bearerToken) },
  );
  return parseCodedErrorOrThrow(response, "GET /v1/ingest/recipes/{id}/map/sample-rows/{row_index}");
}

export async function previewHandling(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  request: MapHandlingPreviewRequest,
): Promise<MapHandlingPreviewResult> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/map/handling-preview`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseCodedErrorOrThrow(response, "POST /v1/ingest/recipes/{id}/map/handling-preview");
}

/** Thrown by `updateRowTemplate` on a 403 (missing role) or 422
 * (`handling_loosened` — an element's override loosened the source-level
 * marking, `09_INGEST_STUDIO.md` §3/§4). */
export class RowTemplateSaveError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function updateRowTemplate(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  rowTemplate: RowTemplate,
  unmappedFields: UnmappedField[],
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/row-template`, {
    method: "PUT",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify({ row_template: rowTemplate, unmapped_fields: unmappedFields }),
  });
  if (response.status === 403) {
    throw new RowTemplateSaveError("forbidden", "principal lacks the required studio role");
  }
  if (!response.ok) {
    let body: { error?: unknown; detail?: unknown; problems?: unknown } = {};
    try {
      body = await response.json();
    } catch {
      // Not a JSON error body — fall through with the generic detail below.
    }
    const code = typeof body.error === "string" ? body.error : "unknown_error";
    // ADR-081 step D: the recipe rules name each problem; the analyst reads those words.
    const problems = Array.isArray(body.problems)
      ? body.problems.filter((p): p is string => typeof p === "string")
      : [];
    const detail =
      problems.length > 0
        ? problems.join(" ")
        : typeof body.detail === "string"
          ? body.detail
          : `PUT /v1/ingest/recipes/{id}/row-template: ${response.status}`;
    throw new RowTemplateSaveError(code, detail);
  }
  return (await response.json()) as StudioRecipeDraft;
}

// --- Verify (09_INGEST_STUDIO.md §5) ----------------------------------------

/** Same coded-error shape as `fetchProfile`/`fetchSampleRow` —
 * `row_template_missing` (Map hasn't saved anything yet),
 * `recipe_not_ready_for_profile`, or `ontology_violation` (the recipe
 * itself declares a type/property the ontology doesn't). */
export async function runVerify(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<VerifyReport> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/verify`, {
    method: "POST",
    headers: authHeaders(bearerToken),
  });
  return parseCodedErrorOrThrow(response, "POST /v1/ingest/recipes/{id}/verify");
}

// --- Publish (09_INGEST_STUDIO.md §6) ---------------------------------------

/** Same coded-error shape as the rest of the studio's fetch wrappers —
 * `studio_recipe_not_verified` (Verify hasn't passed since the last edit),
 * `studio_recipe_not_a_draft`, `studio_recipe_cannot_version`,
 * `recipe_not_runnable` (§6: a `flagged`/`draft`/`superseded` recipe can't
 * be run), or a 403 for a role the principal doesn't hold. */
export class StudioActionError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function parseActionErrorOrThrow<T>(response: Response, action: string): Promise<T> {
  if (response.status === 403) {
    throw new StudioActionError("forbidden", `${action}: principal lacks the required studio role`);
  }
  if (!response.ok) {
    let body: { error?: unknown; detail?: unknown } = {};
    try {
      body = await response.json();
    } catch {
      // Not a JSON error body — fall through with the generic detail below.
    }
    const code = typeof body.error === "string" ? body.error : "unknown_error";
    const detail = typeof body.detail === "string" ? body.detail : `${action}: ${response.status}`;
    throw new StudioActionError(code, detail);
  }
  return (await response.json()) as T;
}

export async function fetchRecipeRegistry(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<StudioRecipeDraft[]> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipe-registry`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/recipe-registry");
}

export async function publishRecipe(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  input: PublishRecipeInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/publish`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseActionErrorOrThrow(response, "POST /v1/ingest/recipes/{id}/publish");
}

export async function updateSchedule(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  input: ScheduleUpdateInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/schedule`, {
    method: "PATCH",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseActionErrorOrThrow(response, "PATCH /v1/ingest/recipes/{id}/schedule");
}

export async function createNewVersion(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/versions`, {
    method: "POST",
    headers: authHeaders(bearerToken),
  });
  return parseActionErrorOrThrow(response, "POST /v1/ingest/recipes/{id}/versions");
}

export async function runRecipe(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  /** §8: "run a published recipe against a file" — omit to repeat
   * against the recipe's own recorded location. */
  sourceLocation?: string,
): Promise<LoadReport | PipelineRunReport> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/ingest/recipes/${recipeId}/run`,
    {
      method: "POST",
      headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
      body: JSON.stringify({ source_location: sourceLocation || null }),
    },
  );
  return parseActionErrorOrThrow(
    response,
    "POST /v1/investigations/{id}/ingest/recipes/{id}/run",
  );
}

/** ADR-108 phase B: what the pipeline save answers — the draft, or every problem in words. */
export type PipelineSaveOutcome =
  | { kind: "saved"; draft: StudioRecipeDraft }
  | { kind: "invalid"; problems: string[] };

export async function savePipeline(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  pipeline: PipelineGraph,
): Promise<PipelineSaveOutcome> {
  const response = await fetch(
    `${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/pipeline`,
    {
      method: "PUT",
      headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
      body: JSON.stringify(pipeline),
    },
  );
  if (response.status === 422) {
    const body = (await response.json()) as { error?: string; problems?: string[] };
    if (body.error === "pipeline_invalid") {
      return { kind: "invalid", problems: body.problems ?? [] };
    }
  }
  return { kind: "saved", draft: await parseOrThrow(response, "PUT /v1/ingest/recipes/{id}/pipeline") };
}

export async function fetchDomainPacks(
  apiBaseUrl: string,
  bearerToken: string,
): Promise<DomainPackEntry[]> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/packs`, { headers: authHeaders(bearerToken) });
  return parseOrThrow(response, "GET /v1/ingest/packs");
}

// --- ADR-110 decision 7: the structured schedule editor ------------------------------------------

/** The schedule in words and its next five runs, or a `StudioActionError` with the refusal in words
 * (`schedule_refused`). */
export async function previewSchedule(
  apiBaseUrl: string,
  bearerToken: string,
  cron: string,
  timezone: string,
): Promise<SchedulePreview> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/schedule-preview`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify({ cron, timezone }),
  });
  return parseActionErrorOrThrow(response, "POST /v1/ingest/schedule-preview");
}

export async function setRecipeSchedulePaused(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  paused: boolean,
): Promise<StudioRecipeDraft> {
  const response = await fetch(
    `${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/schedule/${paused ? "pause" : "resume"}`,
    { method: "POST", headers: authHeaders(bearerToken) },
  );
  return parseActionErrorOrThrow(response, `POST …/schedule/${paused ? "pause" : "resume"}`);
}

export async function fetchRecipeRuns(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<ScheduleRunView[]> {
  const response = await fetch(`${studioCase(apiBaseUrl, investigationId)}/ingest/recipes/${recipeId}/runs`, {
    headers: authHeaders(bearerToken),
  });
  return parseActionErrorOrThrow(response, "GET …/runs");
}
