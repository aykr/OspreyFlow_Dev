// The structured schedule editor on the Publish screen (`06_DECISIONS.md` ADR-110 decision 7): run
// hourly, daily, on weekdays or weekly at a time, in a named time zone (Europe/London by default) — or
// on an advanced cron expression — explained in words with the next five runs before anything is
// saved. The words and the times are the Conduit's, from the executor's own arithmetic, so what is
// shown is what will run; a schedule it could not keep is refused here in its words.
import { useEffect, useState } from "react";

import type { SchedulePreview } from "../../../../../packages/schemas/generated";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import { StudioActionError, previewSchedule } from "../api";
import { cronOf, type ScheduleChoice } from "./scheduleChoice";

export const DEFAULT_TIMEZONE = "Europe/London";
const ZONES = ["Europe/London", "UTC", "Europe/Dublin", "Europe/Paris", "America/New_York", "Asia/Singapore"];
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const KINDS: { id: ScheduleChoice["kind"]; label: string }[] = [
  { id: "none", label: "Not scheduled — run by hand" },
  { id: "hourly", label: "Every hour" },
  { id: "daily", label: "Every day" },
  { id: "weekdays", label: "Every weekday" },
  { id: "weekly", label: "Every week" },
  { id: "cron", label: "Advanced (cron expression)" },
];

function changed(kind: ScheduleChoice["kind"], from: ScheduleChoice): ScheduleChoice {
  const time = "time" in from ? from.time : "06:00";
  switch (kind) {
    case "none":
      return { kind };
    case "hourly":
      return { kind, minute: 0 };
    case "daily":
    case "weekdays":
      return { kind, time };
    case "weekly":
      return { kind, day: 1, time };
    case "cron":
      return { kind, cron: cronOf(from) ?? "0 6 * * *" };
  }
}

export interface ScheduleEditorProps {
  apiBaseUrl: string;
  bearerToken: string;
  choice: ScheduleChoice;
  timezone: string;
  disabled?: boolean;
  onChange: (choice: ScheduleChoice, timezone: string) => void;
}

export function ScheduleEditor({ apiBaseUrl, bearerToken, choice, timezone, disabled, onChange }: ScheduleEditorProps) {
  const cron = cronOf(choice);
  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    setPreview(null);
    setRefused(null);
    if (!cron) {
      if (choice.kind !== "none") setRefused("Give a time such as 06:00.");
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      previewSchedule(apiBaseUrl, bearerToken, cron, timezone)
        .then((p) => live && setPreview(p))
        .catch((e: unknown) => live && setRefused(e instanceof StudioActionError ? e.message : "The schedule could not be checked."));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [apiBaseUrl, bearerToken, cron, timezone, choice.kind]);

  const set = (next: ScheduleChoice) => onChange(next, timezone);
  const field = { display: "grid", gap: "var(--sp-4)" } as const;

  return (
    <div style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 480 }}>
      <label className="label" style={field}>
        Run on a schedule
        <Select aria-label="How often" value={choice.kind} disabled={disabled}
                onChange={(e) => set(changed(e.target.value as ScheduleChoice["kind"], choice))}>
          {KINDS.map((k) => (
            <option key={k.id} value={k.id}>{k.label}</option>
          ))}
        </Select>
      </label>
      {choice.kind === "hourly" && (
        <label className="label" style={field}>
          Minutes past the hour
          <Input aria-label="Minutes past the hour" type="number" min={0} max={59} value={choice.minute} disabled={disabled}
                 onChange={(e) => set({ kind: "hourly", minute: Number(e.target.value) })} />
        </label>
      )}
      {choice.kind === "weekly" && (
        <label className="label" style={field}>
          On
          <Select aria-label="Day of the week" value={String(choice.day)} disabled={disabled}
                  onChange={(e) => set({ ...choice, day: Number(e.target.value) })}>
            {DAYS.map((d, i) => (
              <option key={d} value={i}>{d}</option>
            ))}
          </Select>
        </label>
      )}
      {(choice.kind === "daily" || choice.kind === "weekdays" || choice.kind === "weekly") && (
        <label className="label" style={field}>
          At
          <Input aria-label="Time" type="time" value={choice.time} disabled={disabled}
                 onChange={(e) => set({ ...choice, time: e.target.value })} />
        </label>
      )}
      {choice.kind === "cron" && (
        <label className="label" style={field}>
          Cron expression (minute, hour, day of month, month, day of week)
          <Input aria-label="Cron expression" value={choice.cron} disabled={disabled}
                 onChange={(e) => set({ kind: "cron", cron: e.target.value })} />
        </label>
      )}
      {choice.kind !== "none" && (
        <label className="label" style={field}>
          Time zone
          <Select aria-label="Time zone" value={timezone} disabled={disabled} onChange={(e) => onChange(choice, e.target.value)}>
            {(ZONES.includes(timezone) ? ZONES : [timezone, ...ZONES]).map((z) => (
              <option key={z} value={z}>{z}</option>
            ))}
          </Select>
        </label>
      )}
      {refused && <p role="alert" style={{ margin: 0 }}>{refused}</p>}
      {preview && (
        <div role="status" aria-label="Schedule preview">
          <p className="value" style={{ margin: 0 }}>{`Runs ${preview.words}.`}</p>
          <p className="label" style={{ margin: "var(--sp-4) 0 0" }}>Next five runs:</p>
          <ol style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {preview.next_runs.map((at) => (
              <li key={at} className="label">
                {new Date(at).toLocaleString("en-GB", { dateStyle: "full", timeStyle: "short", timeZone: timezone })}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
