// Admin › Models' usage and each engine's limits (`06_DECISIONS.md` ADR-135 Amendment 3), behind
// `manage_models`. Usage is the model gateway's own record, as counts: calls and tokens per engine
// and per job over whole UTC days. No prompt, answer, key or person is in it, and there is no figure
// per person. Limits are applied by the gateway itself to every call sent to the engine.
import { useEffect, useState, type FormEvent } from "react";

import type { AdminEngine, EngineLimits, ModelUsageView, UsageFigures } from "../../../../../packages/schemas/generated";
import { Button, Input, Select } from "../../design/primitives";
import { readUsage, type ModelsApi } from "./ModelsApi";

const JOB_WORDS: Record<string, string> = {
  extraction: "Extraction and Ask",
  vision: "Image description",
  transcription: "Transcription",
  embedding: "Embeddings",
};
const PERIODS = [
  { value: "7", label: "The last 7 days" },
  { value: "30", label: "The last 30 days" },
  { value: "month", label: "This month" },
  { value: "chosen", label: "Days I choose" },
] as const;

const number = (n: number | null | undefined) => (n ?? 0).toLocaleString("en-GB");
const isoDay = (d: Date) => d.toISOString().slice(0, 10);

/** An engine's limits, in words, for its row in the engines' table. */
export function limitsInWords(limits: EngineLimits | undefined): string {
  const parts: string[] = [];
  if (limits?.requests_per_minute) parts.push(`${number(limits.requests_per_minute)} requests a minute`);
  if (limits?.tokens_per_minute) parts.push(`${number(limits.tokens_per_minute)} tokens a minute`);
  if (limits?.budget_tokens && limits.budget_period) {
    parts.push(`${number(limits.budget_tokens)} tokens a ${limits.budget_period}`);
  }
  return parts.length ? parts.join("; ") : "No limits";
}

/** The limits form: each blank is no limit. A budget needs its tokens and its period together. */
export function LimitsForm({
  engine,
  onSave,
  onCancel,
}: {
  engine: AdminEngine;
  onSave: (limits: EngineLimits) => void;
  onCancel: () => void;
}) {
  const name = engine.provider.name;
  const label = engine.provider.label ?? name;
  const held = engine.limits ?? {};
  const [rpm, setRpm] = useState(held.requests_per_minute?.toString() ?? "");
  const [tpm, setTpm] = useState(held.tokens_per_minute?.toString() ?? "");
  const [budget, setBudget] = useState(held.budget_tokens?.toString() ?? "");
  const [period, setPeriod] = useState<string>(held.budget_period ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const whole = (text: string) => (text.trim() === "" ? null : Number(text.replace(/[,\s]/g, "")));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const limits = {
      requests_per_minute: whole(rpm),
      tokens_per_minute: whole(tpm),
      budget_tokens: whole(budget),
      budget_period: (period || null) as EngineLimits["budget_period"],
    };
    const bad = Object.entries(limits).find(([k, v]) => k !== "budget_period" && v !== null && (!Number.isInteger(v) || (v as number) < 1));
    if (bad) return setProblem("Each limit is a whole number of at least 1, or blank for no limit.");
    if ((limits.budget_tokens === null) !== (limits.budget_period === null)) {
      return setProblem("A budget needs both its tokens and its period (a day or a month).");
    }
    setProblem(null);
    onSave(limits);
  };
  const id = `limits-${name}`;
  return (
    <form className="admin-models-form" aria-label={`Limits for ${label}`} onSubmit={submit}>
      <p className="label" style={{ margin: 0 }}>
        The model gateway applies these to every call sent to {label}. A call past a limit is refused, and the person
        who asked is told which limit stopped it and when to try again. The call that crosses a limit is still answered;
        the next one is refused. Leave a field blank for no limit.
      </p>
      {problem && <p role="alert">{problem}</p>}
      <label htmlFor={`${id}-rpm`}>Requests a minute</label>
      <Input id={`${id}-rpm`} inputMode="numeric" value={rpm} onChange={(e) => setRpm(e.target.value)} />
      <label htmlFor={`${id}-tpm`}>Tokens a minute</label>
      <Input id={`${id}-tpm`} inputMode="numeric" value={tpm} onChange={(e) => setTpm(e.target.value)} />
      <label htmlFor={`${id}-budget`}>Token budget (prompt and answer together)</label>
      <Input id={`${id}-budget`} inputMode="numeric" value={budget} onChange={(e) => setBudget(e.target.value)} />
      <label htmlFor={`${id}-period`}>Budget period</label>
      <Select id={`${id}-period`} value={period} onChange={(e) => setPeriod(e.target.value)}>
        <option value="">No budget</option>
        <option value="day">A day (from midnight UTC)</option>
        <option value="month">A month (from the first, UTC)</option>
      </Select>
      <div className="admin-models-actions">
        <Button type="submit" variant="primary">
          Save the limits
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Figures({ f }: { f: UsageFigures }) {
  return (
    <>
      <td>{number(f.calls)}</td>
      <td>{number(f.failed)}</td>
      <td>{number(f.prompt_tokens)}</td>
      <td>{number(f.completion_tokens)}</td>
      <td>{number(f.tokens)}</td>
    </>
  );
}

function periodOf(choice: string, from: string, to: string, today: Date): [string, string] {
  const end = isoDay(today);
  if (choice === "chosen") return [from || end, to || end];
  if (choice === "month") return [`${end.slice(0, 8)}01`, end];
  const start = new Date(today);
  start.setUTCDate(start.getUTCDate() - (Number(choice) - 1));
  return [isoDay(start), end];
}

/** The usage section: a period, then the gateway's counts by engine and job. */
export function ModelsUsage({ api, today = new Date() }: { api: ModelsApi; today?: Date }) {
  const [choice, setChoice] = useState<string>("30");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [asked, setAsked] = useState<[string, string]>(() => periodOf("30", "", "", today));
  const [usage, setUsage] = useState<ModelUsageView | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    // Only the answer for the period last asked is shown: an earlier, slower one is dropped.
    let current = true;
    setProblem(null);
    readUsage(api, asked[0], asked[1])
      .then((u) => {
        if (!current) return;
        if (Array.isArray(u?.rows)) setUsage(u);
        else setProblem("The usage could not be read.");
      })
      .catch((e: Error) => {
        if (current) setProblem(e.message);
      });
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, asked[0], asked[1]]);

  const choose = (next: string) => {
    setChoice(next);
    if (next !== "chosen") setAsked(periodOf(next, from, to, today));
  };

  return (
    <section aria-labelledby="models-usage">
      <h3 id="models-usage">Usage</h3>
      <p className="label" style={{ margin: 0 }}>
        Calls and tokens per engine and job, from the model gateway&apos;s own records, by whole days in UTC. Only counts
        are kept: no prompt, answer, key or person, and no figure for any one person. Calls refused for a budget are
        counted as failed. Transcriptions and embeddings are not counted yet.
      </p>
      <div className="admin-models-row">
        <label htmlFor="usage-period">Period</label>
        <Select id="usage-period" value={choice} onChange={(e) => choose(e.target.value)}>
          {PERIODS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </Select>
      </div>
      {choice === "chosen" && (
        <div className="admin-models-actions">
          <div className="admin-models-row">
            <label htmlFor="usage-from">First day</label>
            <Input id="usage-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="admin-models-row">
            <label htmlFor="usage-to">Last day</label>
            <Input id="usage-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
          <Button onClick={() => setAsked(periodOf("chosen", from, to, today))}>Show the usage</Button>
        </div>
      )}
      {problem && <p role="alert">{problem}</p>}
      {usage && !problem && (
        <table className="table" aria-label="Usage by engine and job">
          <caption className="label">
            {usage.start === usage.end ? usage.start : `${usage.start} to ${usage.end}`}
          </caption>
          <thead>
            <tr>
              <th>Engine</th>
              <th>Job</th>
              <th>Calls</th>
              <th>Failed</th>
              <th>Prompt tokens</th>
              <th>Answer tokens</th>
              <th>Tokens</th>
            </tr>
          </thead>
          <tbody>
            {usage.rows.length === 0 && (
              <tr>
                <td colSpan={7}>No calls in this period.</td>
              </tr>
            )}
            {usage.rows.map((row) => (
              <tr key={`${row.engine}/${row.job}`}>
                <td>{row.engine_label}</td>
                <td>{JOB_WORDS[row.job] ?? row.job}</td>
                <Figures f={row.figures} />
              </tr>
            ))}
          </tbody>
          {usage.rows.length > 0 && (
            <tfoot>
              <tr>
                <th scope="row" colSpan={2}>
                  All engines and jobs
                </th>
                <Figures f={usage.total} />
              </tr>
            </tfoot>
          )}
        </table>
      )}
    </section>
  );
}
