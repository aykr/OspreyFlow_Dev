// The readiness strip (ADR-140 decision 1): where the dataset stands at a glance — its model, its
// sources, its pipelines with how many drafts have not passed Test, and its last run.
import type { ScheduleRunView, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import type { DomainPack } from "../../investigation/cases";
import { modelInWords } from "./packs";

export interface ReadinessStripProps {
  packs: readonly DomainPack[] | undefined;
  pipelines: readonly StudioRecipeDraft[] | null;
  runs: Record<string, ScheduleRunView[]>;
}

/** The sources the pipelines read: each distinct file, by its name. */
export function sourcesOf(pipelines: readonly StudioRecipeDraft[]): string[] {
  const names = pipelines.map((p) => p.source_location).filter((s): s is string => !!s);
  return [...new Set(names)];
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

export function ReadinessStrip({ packs, pipelines, runs }: ReadinessStripProps) {
  const list = pipelines ?? [];
  const untested = list.filter(isUntested).length;
  const sources = sourcesOf(list).length;
  const items = [
    `Model: ${modelInWords(packs)}`,
    `${sources} ${sources === 1 ? "source" : "sources"}`,
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
