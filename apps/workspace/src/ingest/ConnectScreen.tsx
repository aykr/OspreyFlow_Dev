// Stage 1 of the Ingest Studio — `docs/09_INGEST_STUDIO.md` §2. A real
// top-level screen (`App.tsx`'s `view` state gains an `"ingest"` member),
// not a modal wizard: unlike `SiteCalibrationWizard`, a draft here spans
// sessions and sometimes people (§6), so it has to be revisitable the same
// way the Graph/Map screens are, not opened and dismissed once.
//
// Connect asks three things regardless of source — where the data is, the
// handling marking, and the legal basis — and none is optional or
// answerable later (§2). Profile (the next stage) does not exist yet, so
// "cannot proceed to Profile without all three" is enforced here only as a
// disabled button, gated on `StudioRecipeDraft.ready_for_profile` — the
// server-side gate this screen has to grow once Profile exists.
import { useEffect, useMemo, useState } from "react";

import type {
  ConnectDraftInput,
  ConnectorCatalogueEntry,
  StudioRecipeDraft,
} from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { Panel } from "../design/primitives/Panel";
import { Select } from "../design/primitives/Select";
import {
  ForbiddenError,
  createDraft,
  fetchConnectorCatalogue,
  fetchHandlingScheme,
  listDrafts,
  updateDraft,
  type HandlingScheme,
} from "./api";

export interface ConnectScreenProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** Fired whenever the screen's own idea of "the active draft" changes —
   * a fresh save, resuming a draft from the list, or starting a new one
   * (`null`) — so a host that navigates by stage (Connect/Profile) can
   * track `ready_for_profile` without duplicating this screen's state. */
  onDraftChange?: (draft: StudioRecipeDraft | null) => void;
  /** Fired when "Continue to Profile" is pressed, only ever enabled once
   * the active draft's `ready_for_profile` is `true` (§2). */
  onContinueToProfile?: (recipeId: string) => void;
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
  };
}

export function formToInput(form: FormState): ConnectDraftInput {
  const handling: Record<string, string> = {};
  if (form.classification) handling.classification = form.classification;
  if (form.handlingCode) handling.handling_code = form.handlingCode;
  if (form.originator) handling.originator = form.originator;
  if (form.owningUnit) handling.owning_unit = form.owningUnit;
  return {
    label: form.label,
    connector_profile: form.connectorProfile,
    source_location: form.sourceLocation || null,
    handling,
    legal_basis: form.legalBasis || null,
  };
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
  bearerToken,
  onDraftChange,
  onContinueToProfile,
}: ConnectScreenProps) {
  const [catalogue, setCatalogue] = useState<ConnectorCatalogueEntry[] | null>(null);
  const [scheme, setScheme] = useState<HandlingScheme | null>(null);
  const [drafts, setDrafts] = useState<StudioRecipeDraft[]>([]);
  const [activeRecipeId, setActiveRecipeId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<StudioRecipeDraft | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      fetchConnectorCatalogue(apiBaseUrl, bearerToken),
      fetchHandlingScheme(apiBaseUrl, bearerToken),
      listDrafts(apiBaseUrl, bearerToken),
    ])
      .then(([catalogueResult, schemeResult, draftsResult]) => {
        if (cancelled) return;
        setCatalogue(catalogueResult);
        setScheme(schemeResult);
        setDrafts(draftsResult);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
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
    setLastSaved(null);
    setSaveError(null);
    setForbidden(false);
    onDraftChange?.(null);
  }

  function resumeDraft(draft: StudioRecipeDraft) {
    setActiveRecipeId(draft.recipe_id);
    setForm(draftToForm(draft));
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
      const input = formToInput(form);
      const saved = activeRecipeId
        ? await updateDraft(apiBaseUrl, bearerToken, activeRecipeId, input)
        : await createDraft(apiBaseUrl, bearerToken, input);
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

  const canSave = form.label.trim().length > 0 && form.connectorProfile.length > 0;

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

      <div style={{ flex: 1, maxWidth: 640 }}>
        <Panel title="Connect">
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
          </fieldset>

          <label style={{ display: "block", marginBottom: "var(--sp-16)" }}>
            Where is the data? <span aria-hidden="true">*</span>
            <Input
              value={form.sourceLocation}
              onChange={(e) => setForm({ ...form, sourceLocation: e.target.value })}
              placeholder="s3://ingest/carrier-a/2026-09.csv"
              style={{ display: "block", width: "100%" }}
            />
          </label>

          <fieldset style={{ border: "none", padding: 0, marginBottom: "var(--sp-16)" }}>
            <legend>
              Handling marking <span aria-hidden="true">*</span>
            </legend>
            <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
              <Select
                value={form.classification}
                onChange={(e) => setForm({ ...form, classification: e.target.value })}
              >
                <option value="" disabled>
                  Classification…
                </option>
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
          </fieldset>

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
