// The readiness strip (ADR-140 decision 1): where the dataset stands at a glance — its model, its
// registered sources (ADR-140 Amendment 6), its pipelines with how many drafts have not passed Test,
// and its last run.
import type { ScheduleRunView, SourceTable, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import type { DomainPack } from "../../investigation/cases";
import { modelInWords } from "./packs";

export interface ReadinessStripProps {
  packs: readonly DomainPack[] | undefined;
  pipelines: readonly StudioRecipeDraft[] | null;
  /** The dataset's registered sources; `null` while read, `"unreadable"` when the read failed. */
  sources: readonly SourceTable[] | null | "unreadable";
  runs: Record<string, ScheduleRunView[]>;
}

/** The files the pipelines read: each distinct location. */
export function filesRead(pipelines: readonly StudioRecipeDraft[]): string[] {
  const names = pipelines.map((p) => p.source_location).filter((s): s is string => !!s);
  return [...new Set(names)];
}

/** The registered sources in words, and any file a pipeline reads that no source registers: named,
 * never folded into the count, since such a pipeline inherits nothing from a source. */
export function sourcesInWords(
  sources: readonly SourceTable[] | null | "unreadable",
  pipelines: readonly StudioRecipeDraft[],
): string {
  if (sources === "unreadable") return "sources could not be read";
  if (sources === null) return "reading the sources…";
  const registered = new Set(sources.map((s) => s.location));
  const loose = filesRead(pipelines).filter((f) => !registered.has(f)).length;
  const count = `${sources.length} ${sources.length === 1 ? "source" : "sources"}`;
  return loose ? `${count} · ${loose} ${loose === 1 ? "file" : "files"} not registered` : count;
}

/** A draft that has not passed Test since its last edit. */
export function isUntested(p: StudioRecipeDraft): boolean {
  return p.status === "draft" && !p.verified_at;
}

export function lastRun(runs: Record<string, ScheduleRunView[]>): ScheduleRunView | null {
  const all = Object.values(runs).flat();
  return all.reduce<ScheduleRunView | null>((latest, r) => (!latest || r.started_at > latest.started_at ? r : latest), null);
}

function lastRunInWords(run: ScheduleRunView | null): string {
  if (!run) return "no run yet";
  const at = new Date(run.started_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
  return `last run ${at}, ${run.outcome}`;
}

export function ReadinessStrip({ packs, pipelines, sources, runs }: ReadinessStripProps) {
  const list = pipelines ?? [];
  const untested = list.filter(isUntested).length;
  const items = [
    `Model: ${modelInWords(packs)}`,
    sourcesInWords(sources, list),
    `${list.length} ${list.length === 1 ? "pipeline" : "pipelines"}${untested ? ` · ${untested} untested` : ""}`,
    lastRunInWords(lastRun(runs)),
  ];
  return (
    <ul
      aria-label="Where this dataset stands"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "var(--sp-16)",
        listStyle: "none",
        margin: 0,
        padding: "var(--sp-8) var(--sp-16)",
        borderBottom: "1px solid var(--border-subtle)",
        color: "var(--text-secondary)",
      }}
    >
      {pipelines === null ? <li>Reading the dataset…</li> : items.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}
