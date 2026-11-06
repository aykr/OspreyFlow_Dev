// A source's governance as a form (ADR-140 decision 7): its marking (classification and handling
// code, the originator and the owning unit), the units its rows may name, its legal basis and its
// refresh policy (recorded; phase 4 runs it). Used to register a source and to edit one.
import type { SourceRefresh } from "../../../../../packages/schemas/generated";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import type { HandlingScheme } from "../api";

export interface Governance {
  classification: string;
  handlingCode: string;
  originator: string;
  owningUnit: string;
  units: string;
  legalBasis: string;
  refresh: SourceRefresh;
}

export const EMPTY_GOVERNANCE: Governance = {
  classification: "",
  handlingCode: "",
  originator: "",
  owningUnit: "",
  units: "",
  legalBasis: "",
  refresh: { trigger: "manual", pattern: null },
};

/** The handling the Conduit takes: the four parts, and the units only when some are named. */
export function handlingOf(g: Governance): Record<string, unknown> {
  const units = g.units.split(",").map((u) => u.trim()).filter(Boolean);
  return {
    classification: g.classification,
    handling_code: g.handlingCode,
    originator: g.originator.trim(),
    owning_unit: g.owningUnit.trim(),
    ...(units.length > 0 ? { units } : {}),
  };
}

export function governanceOf(handling: Record<string, unknown>, legalBasis: string | null | undefined, refresh?: SourceRefresh): Governance {
  const text = (key: string) => (typeof handling[key] === "string" ? (handling[key] as string) : "");
  const units = Array.isArray(handling.units) ? (handling.units as string[]).join(", ") : "";
  return {
    classification: text("classification"),
    handlingCode: text("handling_code"),
    originator: text("originator"),
    owningUnit: text("owning_unit"),
    units,
    legalBasis: legalBasis ?? "",
    refresh: refresh ?? { trigger: "manual", pattern: null },
  };
}

/** What is still missing, in words; empty when the governance is complete. */
export function missing(g: Governance): string[] {
  const out: string[] = [];
  if (!g.classification) out.push("a classification");
  if (!g.handlingCode) out.push("a handling code");
  if (!g.originator.trim()) out.push("an originator");
  if (!g.owningUnit.trim()) out.push("an owning unit");
  if (!g.legalBasis.trim()) out.push("a legal basis");
  if (g.refresh.trigger === "watch" && !(g.refresh.pattern ?? "").trim()) out.push("a filename pattern to watch for");
  return out;
}

export function GovernanceFields({
  scheme,
  value,
  onChange,
}: {
  scheme: HandlingScheme | null;
  value: Governance;
  onChange: (next: Governance) => void;
}) {
  const set = (patch: Partial<Governance>) => onChange({ ...value, ...patch });
  return (
    <div style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Classification</span>
        <Select value={value.classification} onChange={(e) => set({ classification: e.target.value })}>
          <option value="">Choose a classification</option>
          {(scheme?.classification ?? []).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Handling code</span>
        <Select value={value.handlingCode} onChange={(e) => set({ handlingCode: e.target.value })}>
          <option value="">Choose a handling code</option>
          {Object.entries(scheme?.handling_codes ?? {}).map(([code, h]) => (
            <option key={code} value={code}>
              {`${code}: ${h.label}`}
            </option>
          ))}
        </Select>
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Originator</span>
        <Input value={value.originator} onChange={(e) => set({ originator: e.target.value })} />
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Owning unit</span>
        <Input value={value.owningUnit} onChange={(e) => set({ owningUnit: e.target.value })} />
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Units its rows may name (comma between)</span>
        <Input value={value.units} onChange={(e) => set({ units: e.target.value })} />
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Legal basis</span>
        <Input value={value.legalBasis} onChange={(e) => set({ legalBasis: e.target.value })} />
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Refresh</span>
        <Select
          value={value.refresh.trigger}
          onChange={(e) => set({ refresh: { ...value.refresh, trigger: e.target.value === "watch" ? "watch" : "manual" } })}
        >
          <option value="manual">By hand</option>
          <option value="watch">When a new file arrives (folder watch)</option>
        </Select>
      </label>
      {value.refresh.trigger === "watch" && (
        <label style={{ display: "grid", gap: "var(--sp-2)" }}>
          <span className="label">Filename pattern to watch for</span>
          <Input
            value={value.refresh.pattern ?? ""}
            placeholder="*.csv"
            onChange={(e) => set({ refresh: { ...value.refresh, pattern: e.target.value } })}
          />
        </label>
      )}
      <p className="label" style={{ margin: 0 }}>
        The refresh policy is recorded with the source; the pipelines that read it run by it from the
        next stage of the Studio.
      </p>
    </div>
  );
}
