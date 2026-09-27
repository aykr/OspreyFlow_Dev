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
  PublishRecipeInput,
  RowTemplate,
  ScheduleUpdateInput,
  SourceProfile,
  StudioRecipeDraft,
  TransformDescriptor,
  UnmappedField,
  VerifyReport,
} from "../../../../packages/schemas/generated";

export interface HandlingCode {
  label: string;
  dissemination: "permitted" | "conditional" | "restricted";
}

export interface HandlingScheme {
  name: string;
  classification: string[];
  handling_codes: Record<string, HandlingCode>;
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
): Promise<IngestSourceListing> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/source-files`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/source-files");
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
  return parseOrThrow(response, action);
}

export async function createDraft(
  apiBaseUrl: string,
  bearerToken: string,
  input: ConnectDraftInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseDraftOrThrow(response, "POST /v1/ingest/recipes");
}

export async function updateDraft(
  apiBaseUrl: string,
  bearerToken: string,
  recipeId: string,
  input: ConnectDraftInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}`, {
    method: "PATCH",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseDraftOrThrow(response, "PATCH /v1/ingest/recipes/{id}");
}

export async function fetchDraft(
  apiBaseUrl: string,
  bearerToken: string,
  recipeId: string,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/recipes/{id}");
}

export async function listDrafts(
  apiBaseUrl: string,
  bearerToken: string,
): Promise<StudioRecipeDraft[]> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes`, {
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
  recipeId: string,
): Promise<SourceProfile> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}/profile`, {
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
  recipeId: string,
  rowIndex: number,
): Promise<MapSampleRow> {
  const response = await fetch(
    `${apiBaseUrl}/v1/ingest/recipes/${recipeId}/map/sample-rows/${rowIndex}`,
    { headers: authHeaders(bearerToken) },
  );
  return parseCodedErrorOrThrow(response, "GET /v1/ingest/recipes/{id}/map/sample-rows/{row_index}");
}

export async function previewHandling(
  apiBaseUrl: string,
  bearerToken: string,
  recipeId: string,
  request: MapHandlingPreviewRequest,
): Promise<MapHandlingPreviewResult> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}/map/handling-preview`, {
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
  recipeId: string,
  rowTemplate: RowTemplate,
  unmappedFields: UnmappedField[],
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}/row-template`, {
    method: "PUT",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify({ row_template: rowTemplate, unmapped_fields: unmappedFields }),
  });
  if (response.status === 403) {
    throw new RowTemplateSaveError("forbidden", "principal lacks the required studio role");
  }
  if (!response.ok) {
    let body: { error?: unknown; detail?: unknown } = {};
    try {
      body = await response.json();
    } catch {
      // Not a JSON error body — fall through with the generic detail below.
    }
    const code = typeof body.error === "string" ? body.error : "unknown_error";
    const detail =
      typeof body.detail === "string"
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
  recipeId: string,
): Promise<VerifyReport> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}/verify`, {
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
): Promise<StudioRecipeDraft[]> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipe-registry`, {
    headers: authHeaders(bearerToken),
  });
  return parseOrThrow(response, "GET /v1/ingest/recipe-registry");
}

export async function publishRecipe(
  apiBaseUrl: string,
  bearerToken: string,
  recipeId: string,
  input: PublishRecipeInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}/publish`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseActionErrorOrThrow(response, "POST /v1/ingest/recipes/{id}/publish");
}

export async function updateSchedule(
  apiBaseUrl: string,
  bearerToken: string,
  recipeId: string,
  input: ScheduleUpdateInput,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}/schedule`, {
    method: "PATCH",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseActionErrorOrThrow(response, "PATCH /v1/ingest/recipes/{id}/schedule");
}

export async function createNewVersion(
  apiBaseUrl: string,
  bearerToken: string,
  recipeId: string,
): Promise<StudioRecipeDraft> {
  const response = await fetch(`${apiBaseUrl}/v1/ingest/recipes/${recipeId}/versions`, {
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
): Promise<LoadReport> {
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
