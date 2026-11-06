// A source's governance as a form (ADR-140 decision 7): its marking (classification and handling
// code, the originator and the owning unit), the units its rows may name, its legal basis and its
// refresh policy (ADR-110 Amendment 6): when it is read again, and how each file is read — the whole
// file each time, keeping or withdrawing the rows it no longer carries, or only the rows past a
// watermark column. Used to register a source and to edit one.
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
  if (g.refresh.trigger === "watch" && g.refresh.mode === "incremental" && !(g.refresh.watermark_column ?? "").trim())
    out.push("a watermark column");
  return out;
}

/** A refresh policy in words, as the source's page says it (ADR-110 Amendment 6 point 1). */
export function refreshInWords(refresh: SourceRefresh | null | undefined): string {
  if (!refresh || refresh.trigger !== "watch") return "by hand";
  const when = `when a file matching ${refresh.pattern ?? ""} arrives`;
  if (refresh.mode === "incremental")
    return `${when}, reading only the rows past the highest ${refresh.watermark_column ?? ""} already loaded`;
  return refresh.dropped_rows === "withdraw"
    ? `${when}, reading the whole file and withdrawing what rows it no longer carries had loaded`
    : `${when}, reading the whole file and keeping what rows it no longer carries had loaded`;
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
        <>
          <label style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span className="label">Filename pattern to watch for</span>
            <Input
              value={value.refresh.pattern ?? ""}
              placeholder="*.csv"
              onChange={(e) => set({ refresh: { ...value.refresh, pattern: e.target.value } })}
            />
          </label>
          <label style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span className="label">How each file is read</span>
            <Select
              value={value.refresh.mode ?? "snapshot"}
              onChange={(e) =>
                set({ refresh: { ...value.refresh, mode: e.target.value === "incremental" ? "incremental" : "snapshot" } })
              }
            >
              <option value="snapshot">The whole file each time (full snapshot)</option>
              <option value="incremental">Only rows past a watermark column (incremental)</option>
            </Select>
          </label>
          {(value.refresh.mode ?? "snapshot") === "snapshot" ? (
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">Rows a new file no longer carries</span>
              <Select
                value={value.refresh.dropped_rows ?? "keep"}
                onChange={(e) =>
                  set({ refresh: { ...value.refresh, dropped_rows: e.target.value === "withdraw" ? "withdraw" : "keep" } })
                }
              >
                <option value="keep">Keep what they loaded</option>
                <option value="withdraw">Withdraw what they loaded (reverting the refresh restores it)</option>
              </Select>
            </label>
          ) : (
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">Watermark column (its values only grow)</span>
              <Input
                value={value.refresh.watermark_column ?? ""}
                onChange={(e) => set({ refresh: { ...value.refresh, watermark_column: e.target.value } })}
              />
            </label>
          )}
        </>
      )}
      <p className="label" style={{ margin: 0 }}>
        Each file the watch takes runs every deployed pipeline that reads the source, as whoever set the
        refresh; a pipeline with no deduplication key is never run by it.
      </p>
    </div>
  );
}
