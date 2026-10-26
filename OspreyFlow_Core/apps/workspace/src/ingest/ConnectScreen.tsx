// Stage 1 of the Ingest Studio — `spec/09_INGEST_STUDIO.md` §2. A real
// top-level screen (`App.tsx`'s `view` state gains an `"ingest"` member),
// not a modal wizard: unlike `SiteCalibrationWizard`, a draft here spans
// sessions and sometimes people (§6), so it has to be revisitable the same
// way the Graph/Map screens are, not opened and dismissed once.
//
// Connect asks three things regardless of source — where the data is, the
// handling marking, and the legal basis — and none can be answered later
// (§2). The one exception is the classification inside the marking: left
// blank it is recorded as PUBLIC (ADR-068). "Cannot proceed to Profile
// without all three" is enforced as a disabled button, gated on
// `StudioRecipeDraft.ready_for_profile`, which the server computes.
//
// Beside the marking a source may declare two more things (ADR-127 decision 3, Amendment 2): the
// units its rows may name, and the column that carries each part of a marking. Both are optional and
// are saved into the draft's handling as the API takes them (`units`, `handling_columns`).
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import type {
  ConnectDraftInput,
  ConnectorCatalogueEntry,
  FieldBinding,
  StudioRecipeDraft,
  TransformDescriptor,
} from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { Panel } from "../design/primitives/Panel";
import { Select } from "../design/primitives/Select";
import { DeduplicateControl, cleanBinding } from "./DeduplicateControl";
import { describeFileSize } from "./fileSize";
import { HANDLING_BINDABLE, HANDLING_PART_LABELS } from "./handlingParts";
import {
  ForbiddenError,
  createDraft,
  fetchConnectorCatalogue,
  fetchDraft,
  fetchHandlingScheme,
  UPLOAD_ACCEPT,
  fetchIngestSourceFiles,
  fetchTransforms,
  listDrafts,
  updateDraft,
  uploadIngestSourceFile,
  type HandlingScheme,
  type IngestSourceListing,
} from "./api";

export interface ConnectScreenProps {
  apiBaseUrl: string;
  /** ADR-099 Amendment 3: the case whose dataset the recipe belongs to. */
  investigationId: string;
  bearerToken: string;
  /** Fired whenever the screen's own idea of "the active draft" changes —
   * a fresh save, resuming a draft from the list, or starting a new one
   * (`null`) — so a host that navigates by stage (Connect/Profile) can
   * track `ready_for_profile` without duplicating this screen's state. */
  onDraftChange?: (draft: StudioRecipeDraft | null) => void;
  /** Fired when "Continue to Profile" is pressed, only ever enabled once
   * the active draft's `ready_for_profile` is `true` (§2). */
  onContinueToProfile?: (recipeId: string) => void;
  /** ADR-108: pinned to one pipeline's draft, opened from its source node. The Sources sidebar
   * and "Continue to Profile" make no sense there (the canvas is the navigation), so a pinned
   * screen shows the one draft's form and a way back to the pipeline. */
  recipeId?: string | null;
  onBack?: () => void;
}

export interface FormState {
  label: string;
  connectorProfile: string;
  sourceLocation: string;
  classification: string;
  handlingCode: string;
  originator: string;
  owningUnit: string;
  legalBasis: string;
  /** ADR-127 decision 3: the units the source's rows may name. */
  units: string[];
  /** A marking part to the column that carries it; a blank entry declares nothing. */
  handlingColumns: Record<string, string>;
  /** ADR-127 decision 5: the columns that identify a row, in order; none is no deduplication. */
  dedupKey: FieldBinding[];
}

const EMPTY_FORM: FormState = {
  label: "",
  connectorProfile: "",
  sourceLocation: "",
  classification: "",
  handlingCode: "",
  originator: "",
  owningUnit: "",
  legalBasis: "",
  units: [],
  handlingColumns: {},
  dedupKey: [],
};

export function draftToForm(draft: StudioRecipeDraft): FormState {
  const handling = (draft.handling ?? {}) as Record<string, unknown>;
  return {
    label: draft.label,
    connectorProfile: draft.connector_profile ?? "",
    sourceLocation: draft.source_location ?? "",
    classification: typeof handling.classification === "string" ? handling.classification : "",
    handlingCode: typeof handling.handling_code === "string" ? handling.handling_code : "",
    originator: typeof handling.originator === "string" ? handling.originator : "",
    owningUnit: typeof handling.owning_unit === "string" ? handling.owning_unit : "",
    legalBasis: draft.legal_basis ?? "",
    units: Array.isArray(handling.units)
      ? handling.units.filter((u): u is string => typeof u === "string")
      : [],
    handlingColumns: stringRecord(handling.handling_columns),
    dedupKey: (draft.deduplicate?.key ?? []).map(cleanBinding),
  };
}

function stringRecord(value: unknown): Record<string, string> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

/** The columns the form declares, names trimmed and blanks dropped, as the server keeps them. */
function declaredColumns(form: FormState): Record<string, string> {
  const declared: Record<string, string> = {};
  for (const part of HANDLING_BINDABLE) {
    const column = (form.handlingColumns[part] ?? "").trim();
    if (column) declared[part] = column;
  }
  return declared;
}

/** The server's rule for a declared unit column (`check_source_declarations`), in its own words so
 * the analyst reads the same sentence before and after a save: an originator or owning-unit column
 * needs at least one unit, since a cell may name only a unit the source lists. */
export function sourceDeclarationProblem(form: FormState): string | null {
  const unitParts = (["originator", "owning_unit"] as const).filter((p) => p in declaredColumns(form));
  if (unitParts.length === 0 || form.units.length > 0) return null;
  return (
    `handling_columns declares a column for ${unitParts.join(" and ")} but the source lists no units: ` +
    "a cell may name only a unit the source declares in units"
  );
}

/** `previous` is the draft being edited. The server keeps what a PATCH's handling leaves unsaid, so
 * a declaration the analyst emptied is sent as an explicit empty value, not left out. */
export function formToInput(form: FormState, previous?: StudioRecipeDraft | null): ConnectDraftInput {
  const handling: Record<string, unknown> = {};
  if (form.classification) handling.classification = form.classification;
  if (form.handlingCode) handling.handling_code = form.handlingCode;
  if (form.originator) handling.originator = form.originator;
  if (form.owningUnit) handling.owning_unit = form.owningUnit;
  const before = (previous?.handling ?? {}) as Record<string, unknown>;
  if (form.units.length > 0 || "units" in before) handling.units = form.units;
  const columns = declaredColumns(form);
  if (Object.keys(columns).length > 0 || "handling_columns" in before) handling.handling_columns = columns;
  const input: ConnectDraftInput = {
    label: form.label,
    connector_profile: form.connectorProfile,
    source_location: form.sourceLocation || null,
    handling,
    legal_basis: form.legalBasis || null,
  };
  // ADR-127 decision 5: the server keeps the key a PATCH leaves unsaid, replaces it with a key, and
  // removes it for an empty one — so a key the author cleared is sent empty, and a draft that never
  // had one sends nothing.
  if (form.dedupKey.length > 0) input.deduplicate = { key: form.dedupKey };
  else if ((previous?.deduplicate?.key ?? []).length > 0) input.deduplicate = { key: [] };
  return input;
}

export function groupCatalogue(
  entries: ConnectorCatalogueEntry[],
): [string, ConnectorCatalogueEntry[]][] {
  const groups = new Map<string, ConnectorCatalogueEntry[]>();
  for (const entry of entries) {
    const list = groups.get(entry.group) ?? [];
    list.push(entry);
    groups.set(entry.group, list);
  }
  return Array.from(groups.entries());
}

export function ConnectScreen({
  apiBaseUrl,
  investigationId,
  bearerToken,
  onDraftChange,
  onContinueToProfile,
  recipeId = null,
  onBack,
}: ConnectScreenProps) {
  const [catalogue, setCatalogue] = useState<ConnectorCatalogueEntry[] | null>(null);
  const [scheme, setScheme] = useState<HandlingScheme | null>(null);
  const [drafts, setDrafts] = useState<StudioRecipeDraft[]>([]);
  const [activeRecipeId, setActiveRecipeId] = useState<string | null>(null);
  // Owner ruling R6, 27 September 2026 — the deployment's ingest root, listed so the analyst
  // picks a file rather than typing a path. `null` means "not loaded yet"; a load failure is kept
  // separately because an empty folder and a refused listing must not look the same to an analyst
  // (`09_INGEST_STUDIO.md` §2, "the ingest root").
  const [sourceFiles, setSourceFiles] = useState<IngestSourceListing | null>(null);
  const [sourceFilesError, setSourceFilesError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [unitDraft, setUnitDraft] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // ADR-067 — the file chosen from the analyst's own computer. `uploading` disables the button so a
  // second upload cannot start while one is in flight; `uploadError` is the server's own sentence.
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [lastSaved, setLastSaved] = useState<StudioRecipeDraft | null>(null);
  // The catalogue Map's transform picker reads, for the key's optional transforms. Read apart from
  // the rest, as the ingest root is: a catalogue that cannot be read leaves a key without transforms,
  // never a blank Connect.
  const [transforms, setTransforms] = useState<TransformDescriptor[]>([]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      fetchConnectorCatalogue(apiBaseUrl, bearerToken),
      fetchHandlingScheme(apiBaseUrl, bearerToken),
      listDrafts(apiBaseUrl, bearerToken, investigationId),
    ])
      .then(([catalogueResult, schemeResult, draftsResult]) => {
        if (cancelled) return;
        setCatalogue(catalogueResult);
        setScheme(schemeResult);
        setDrafts(draftsResult);
        if (recipeId) {
          const pinned = draftsResult.find((d) => d.recipe_id === recipeId);
          if (pinned) resumeDraft(pinned);
          else {
            void fetchDraft(apiBaseUrl, bearerToken, investigationId, recipeId).then((d) => {
              if (!cancelled) resumeDraft(d);
            });
          }
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resumeDraft is stable in behaviour
  }, [apiBaseUrl, bearerToken, investigationId, recipeId]);

  // The ingest root, loaded separately from the three above on purpose: a deployment whose
  // operator has staged nothing, or an analyst without `source_author`, must still get a working
  // Connect screen. Folding this into the `Promise.all` would make a 403 here blank the whole
  // stage, which is the failure mode this screen already avoids for the catalogue.
  useEffect(() => {
    let cancelled = false;
    void fetchIngestSourceFiles(apiBaseUrl, bearerToken, investigationId)
      .then((listing) => {
        if (cancelled) return;
        setSourceFiles(listing);
        setSourceFilesError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setSourceFiles(null);
        setSourceFilesError(
          err instanceof ForbiddenError
            ? "You do not hold the source-author role, so the ingest folder cannot be browsed."
            : err instanceof Error
              ? err.message
              : String(err),
        );
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  useEffect(() => {
    let cancelled = false;
    void fetchTransforms(apiBaseUrl, bearerToken)
      .then((catalogueOfTransforms) => {
        if (!cancelled) setTransforms(catalogueOfTransforms);
      })
      .catch(() => {
        if (!cancelled) setTransforms([]);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

  const groupedCatalogue = useMemo(
    () => (catalogue ? groupCatalogue(catalogue) : []),
    [catalogue],
  );

  function startNewDraft() {
    setActiveRecipeId(null);
    setForm(EMPTY_FORM);
    setUnitDraft("");
    setLastSaved(null);
    setSaveError(null);
    setForbidden(false);
    onDraftChange?.(null);
  }

  function resumeDraft(draft: StudioRecipeDraft) {
    setActiveRecipeId(draft.recipe_id);
    setForm(draftToForm(draft));
    setUnitDraft("");
    setLastSaved(draft);
    setSaveError(null);
    setForbidden(false);
    onDraftChange?.(draft);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setForbidden(false);
    try {
      const input = formToInput(form, lastSaved);
      const saved = activeRecipeId
        ? await updateDraft(apiBaseUrl, bearerToken, investigationId, activeRecipeId, input)
        : await createDraft(apiBaseUrl, bearerToken, investigationId, input);
      setLastSaved(saved);
      setActiveRecipeId(saved.recipe_id);
      setDrafts((prev) => {
        const withoutSaved = prev.filter((d) => d.recipe_id !== saved.recipe_id);
        return [saved, ...withoutSaved];
      });
      onDraftChange?.(saved);
    } catch (err) {
      if (err instanceof ForbiddenError) {
        setForbidden(true);
      } else {
        setSaveError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleChosenFile(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      const saved = await uploadIngestSourceFile(apiBaseUrl, bearerToken, investigationId, file);
      setForm((current) => ({ ...current, sourceLocation: saved.source_location }));
      try {
        setSourceFiles(await fetchIngestSourceFiles(apiBaseUrl, bearerToken, investigationId));
        setSourceFilesError(null);
      } catch {
        // The upload worked and is selected; a failed refresh of the list is not worth an alarm.
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  if (loadError) {
    return (
      <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>
        Could not load the Connect screen: {loadError}
      </div>
    );
  }

  if (!catalogue || !scheme) {
    return (
      <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>
        Loading Connect…
      </div>
    );
  }

  const declarationProblem = sourceDeclarationProblem(form);
  const canSave =
    form.label.trim().length > 0 && form.connectorProfile.length > 0 && declarationProblem === null;

  function addUnit() {
    const name = unitDraft.trim();
    setUnitDraft("");
    if (name && !form.units.includes(name)) setForm({ ...form, units: [...form.units, name] });
  }

  function setColumn(part: string, column: string) {
    setForm({ ...form, handlingColumns: { ...form.handlingColumns, [part]: column } });
  }

  return (
    <div
      style={{
        display: "flex",
        gap: "var(--sp-16)",
        padding: "var(--sp-16)",
        height: "100%",
        overflow: "auto",
      }}
    >
      {!recipeId && (
      <div style={{ width: 280, flexShrink: 0 }}>
        <Panel title="Sources">
          <Button variant="primary" onClick={startNewDraft} style={{ marginBottom: "var(--sp-8)" }}>
            + New source
          </Button>
          {drafts.length === 0 && (
            <p style={{ color: "var(--text-tertiary)" }}>No drafts yet.</p>
          )}
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {drafts.map((draft) => (
              <li key={draft.recipe_id}>
                <button
                  type="button"
                  aria-pressed={draft.recipe_id === activeRecipeId}
                  onClick={() => resumeDraft(draft)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "var(--sp-8)",
                    background:
                      draft.recipe_id === activeRecipeId
                        ? "var(--surface-hover)"
                        : "transparent",
                    border: "none",
                    color: "var(--text-primary)",
                    cursor: "pointer",
                  }}
                >
                  {draft.label || "(untitled)"}
                  {!draft.ready_for_profile && (
                    <span style={{ color: "var(--text-tertiary)" }}> — incomplete</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      )}

      <div style={{ flex: 1, maxWidth: 640 }}>
        <Panel title={recipeId ? "Source" : "Connect"}>
          {forbidden && (
            <div
              role="alert"
              style={{
                background: "var(--surface-raised)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--r-panel)",
                padding: "var(--sp-8)",
                marginBottom: "var(--sp-16)",
              }}
            >
              You don't hold the Source Author role, so you can't create or edit a source
              recipe. Ask a source approver to grant it.
            </div>
          )}
          {saveError && (
            <div role="alert" style={{ color: "var(--text-secondary)", marginBottom: "var(--sp-16)" }}>
              {saveError}
            </div>
          )}

          <label style={{ display: "block", marginBottom: "var(--sp-16)" }}>
            Label
            <Input
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              placeholder="Carrier A — call detail records"
              style={{ display: "block", width: "100%" }}
            />
          </label>

          <fieldset style={{ border: "none", padding: 0, marginBottom: "var(--sp-16)" }}>
            <legend>Connector</legend>
            <Select
              aria-label="Connector"
              value={form.connectorProfile}
              onChange={(e) => setForm({ ...form, connectorProfile: e.target.value })}
              style={{ width: "100%" }}
            >
              <option value="" disabled>
                Choose a connector…
              </option>
              {groupedCatalogue.map(([group, entries]) => (
                <optgroup key={group} label={group}>
                  {entries.map((entry) => (
                    <option key={entry.id} value={entry.id} disabled={!entry.available}>
                      {entry.label}
                      {!entry.available ? " (not yet available)" : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
            {/* Owner ruling of 3 October 2026, "Keep them, but say why": the formats the spec lists
                but no connector reads yet stay visible and greyed, with the reason beside them. */}
            {catalogue.some((entry) => !entry.available) ? (
              <p style={{ margin: "var(--sp-4) 0 0", color: "var(--text-tertiary)" }}>
                Greyed formats have no connector built yet.
              </p>
            ) : null}
          </fieldset>

          <fieldset style={{ border: "none", padding: 0, marginBottom: "var(--sp-16)" }}>
            <legend>
              Where is the data? <span aria-hidden="true">*</span>
            </legend>

            {/* ADR-067 (amends R6) — the file picker the owner asked for on 3 October 2026: "I need a
                file picker, not just the bar saying file path". The button is a real <button>, so
                the keyboard reaches it; it presses a hidden file input, which opens the system's
                own picker. The chosen file is uploaded to the ingest folder and selected. */}
            <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", marginBottom: "var(--sp-8)" }}>
              <input
                ref={fileInput}
                type="file"
                aria-label="Choose a file from your computer"
                accept={UPLOAD_ACCEPT}
                tabIndex={-1}
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void handleChosenFile(file);
                }}
              />
              <Button
                variant="primary"
                disabled={uploading}
                onClick={() => fileInput.current?.click()}
              >
                {uploading ? "Uploading…" : "Choose file…"}
              </Button>
              <span style={{ color: "var(--text-tertiary)" }}>From your computer</span>
            </div>
            {uploadError ? (
              <div role="alert" style={{ color: "var(--text-secondary)", marginBottom: "var(--sp-8)" }}>
                {uploadError}
              </div>
            ) : null}
            {form.sourceLocation ? (
              <p style={{ margin: "0 0 var(--sp-8)" }}>
                Selected:{" "}
                <code>
                  {form.sourceLocation.startsWith("/")
                    ? (form.sourceLocation.split("/").pop() ?? form.sourceLocation)
                    : form.sourceLocation}
                </code>
              </p>
            ) : null}

            {/* Owner ruling R6, 27 September 2026 — files an operator placed in the ingest folder
                (and, since ADR-067, files uploaded earlier). The Conduit reads `source_location`
                inside its own container, so only a file the server can see names anything it can
                open. */}
            {sourceFiles && sourceFiles.files.length > 0 ? (
              <Select
                aria-label="Choose a file from the ingest folder"
                value=""
                onChange={(e) => {
                  const chosen = sourceFiles.files.find(
                    (f) => f.source_location === e.target.value,
                  );
                  if (chosen) setForm({ ...form, sourceLocation: chosen.source_location });
                }}
                style={{ display: "block", width: "100%", marginBottom: "var(--sp-8)" }}
              >
                <option value="">Or choose one already on the server…</option>
                {sourceFiles.files.map((file) => (
                  <option key={file.source_location} value={file.source_location}>
                    {file.name} ({describeFileSize(file.size_bytes)}
                    {file.uploaded ? ", uploaded" : ""})
                  </option>
                ))}
              </Select>
            ) : null}

            {/* An empty folder and a refused listing are different facts and are said
                differently — an analyst who sees "nothing here" when the real answer is "you may
                not look" will go and ask the wrong person. */}
            {sourceFiles && sourceFiles.files.length === 0 ? (
              <p style={{ margin: "0 0 var(--sp-8)", color: "var(--fg-muted)" }}>
                No files on the server yet (<code>{sourceFiles.root}</code>). Choose one from your
                computer above, or an operator can place source files there.
              </p>
            ) : null}
            {sourceFilesError ? (
              <p role="status" style={{ margin: "0 0 var(--sp-8)", color: "var(--fg-muted)" }}>
                {sourceFilesError}
              </p>
            ) : null}

            {/* The typed path stays for what a file cannot cover (an `s3://` address, a developer's
                local path); behind a disclosure so the picker is what the analyst sees first. */}
            <details>
              <summary style={{ cursor: "pointer", color: "var(--text-secondary)" }}>
                Or type a path or address
              </summary>
              <Input
                aria-label="Where is the data?"
                value={form.sourceLocation}
                onChange={(e) => setForm({ ...form, sourceLocation: e.target.value })}
                placeholder="s3://ingest/carrier-a/2026-09.csv"
                style={{ display: "block", width: "100%", marginTop: "var(--sp-8)" }}
              />
            </details>
          </fieldset>

          <fieldset style={{ border: "none", padding: 0, marginBottom: "var(--sp-16)" }}>
            <legend>
              Handling marking <span aria-hidden="true">*</span>
            </legend>
            <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
              <Select
                aria-label="Classification"
                value={form.classification}
                onChange={(e) => setForm({ ...form, classification: e.target.value })}
              >
                <option value="">Classification (optional)</option>
                {scheme.classification.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
              <Select
                value={form.handlingCode}
                onChange={(e) => setForm({ ...form, handlingCode: e.target.value })}
              >
                <option value="" disabled>
                  Handling code…
                </option>
                {Object.entries(scheme.handling_codes).map(([code, def]) => (
                  <option key={code} value={code}>
                    {code} — {def.label}
                  </option>
                ))}
              </Select>
              <Input
                value={form.originator}
                onChange={(e) => setForm({ ...form, originator: e.target.value })}
                placeholder="Originator (e.g. unit-42)"
              />
              <Input
                value={form.owningUnit}
                onChange={(e) => setForm({ ...form, owningUnit: e.target.value })}
                placeholder="Owning unit (e.g. unit-1)"
              />
            </div>
            {/* ADR-068: the server records the scheme's lowest level for a blank classification;
                this only says so, so a blank is never a silent choice. */}
            {form.classification === "" ? (
              <p style={{ margin: "var(--sp-4) 0 0", color: "var(--text-tertiary)" }}>
                Left blank: recorded as{" "}
                {scheme.classification.includes("PUBLIC") ? "PUBLIC" : (scheme.classification[0] ?? "PUBLIC")}
              </p>
            ) : null}
          </fieldset>

          {/* ADR-127 decision 3: what a source may declare beside its marking. Both are optional; a
              declared originator or owning-unit column needs a unit to name, which the server
              enforces and this says first. */}
          <fieldset style={{ border: "none", padding: 0, marginBottom: "var(--sp-16)" }}>
            <legend>Units this source's rows may name</legend>
            {form.units.length > 0 ? (
              <ul style={{ listStyle: "none", margin: "0 0 var(--sp-8)", padding: 0 }}>
                {form.units.map((unit) => (
                  <li key={unit} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                    <span>{unit}</span>
                    <Button
                      aria-label={`Remove unit ${unit}`}
                      onClick={() => setForm({ ...form, units: form.units.filter((u) => u !== unit) })}
                    >
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            ) : null}
            <div style={{ display: "flex", gap: "var(--sp-8)" }}>
              <Input
                aria-label="Unit name"
                value={unitDraft}
                onChange={(e) => setUnitDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addUnit();
                  }
                }}
                placeholder="Unit name (e.g. unit-42)"
              />
              <Button onClick={addUnit}>Add unit</Button>
            </div>
          </fieldset>

          <fieldset style={{ border: "none", padding: 0, marginBottom: "var(--sp-16)" }}>
            <legend>Columns that carry the marking</legend>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "var(--sp-8)", alignItems: "center" }}>
              {HANDLING_BINDABLE.map((part) => {
                const label = HANDLING_PART_LABELS[part];
                const column = form.handlingColumns[part] ?? "";
                return (
                  <Fragment key={part}>
                    <span>{label}</span>
                    {/* Connect reads no source, so the column is typed; Map offers the declared
                        one from the source's own columns. */}
                    <Input
                      aria-label={`Column carrying ${label}`}
                      value={column}
                      onChange={(e) => setColumn(part, e.target.value)}
                      placeholder="Column name (optional)"
                    />
                  </Fragment>
                );
              })}
            </div>
            {declarationProblem ? (
              <p role="status" style={{ margin: "var(--sp-8) 0 0", color: "var(--warning)" }}>
                {declarationProblem}
              </p>
            ) : null}
          </fieldset>

          <DeduplicateControl
            keyParts={form.dedupKey}
            onChange={(dedupKey) => setForm({ ...form, dedupKey })}
            transforms={transforms}
            newVersion={(lastSaved?.version ?? 1) > 1}
          />

          <label style={{ display: "block", marginBottom: "var(--sp-16)" }}>
            Legal basis <span aria-hidden="true">*</span>
            <Input
              value={form.legalBasis}
              onChange={(e) => setForm({ ...form, legalBasis: e.target.value })}
              placeholder="RIPA s22 acquisition — authorisation 2026/0114"
              style={{ display: "block", width: "100%" }}
            />
          </label>

          <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
            <Button variant="primary" disabled={!canSave || saving} onClick={() => void handleSave()}>
              {activeRecipeId ? "Save" : "Create draft"}
            </Button>
            {recipeId ? (
              <Button onClick={() => onBack?.()}>Back to the pipeline</Button>
            ) : (
              <Button
                disabled={!lastSaved?.ready_for_profile}
                title={
                  lastSaved?.ready_for_profile
                    ? undefined
                    : "Answer location, handling marking and legal basis to continue"
                }
                onClick={() => lastSaved && onContinueToProfile?.(lastSaved.recipe_id)}
              >
                Continue to Profile
              </Button>
            )}
            {lastSaved && !lastSaved.ready_for_profile && (
              <span style={{ color: "var(--text-tertiary)" }}>
                Answer location, handling marking and legal basis to continue.
              </span>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
