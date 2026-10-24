// The Trends tab (ADR-113 stage 5): build a trend from what `/trends/options` offers — and only
// that, there is no free-text field for an event type or a property — preview it, save it, and add
// a saved one to a pack. Every figure arrives counted for this reader; the screen only draws it.
import { useEffect, useState } from "react";

import type {
  ReportPack,
  TrendDefinition,
  TrendDefinitionInput,
  TrendEventTypeOption,
  TrendFieldOption,
  TrendFigures,
  TrendOptions,
} from "../../../../packages/schemas/generated";
import { fetchCaseEvents } from "../analytics/api";
import { DOMAIN_PACKS, type DomainPack, domainLabels, listCases } from "../investigation/cases";
import { eventsElsewhereSentence } from "../analytics/eventsElsewhere";
import { Button, Checkbox, Input, RadioGroup, Select } from "../design/primitives";
import type { ReportsApi } from "./api";
import { addItem, listPacks } from "./packsApi";
import { TrendChart } from "./TrendChart";
import { deleteTrend, fetchTrendFigures, fetchTrendOptions, listTrends, previewTrend, saveTrend } from "./trendsApi";

const MAX_FILTERS = 5;
const WEEKS = [4, 12, 26, 52, 104];

interface FilterRow {
  field: string;
  value: string;
}

export interface TrendForm {
  title: string;
  types: string[];
  measure: "count" | "sum";
  field: string;
  interval: "week" | "month";
  weeks: number;
  groupBy: string;
  filters: FilterRow[];
}

const EMPTY: TrendForm = { title: "", types: [], measure: "count", field: "", interval: "week", weeks: 12, groupBy: "", filters: [] };

/** The fields of one kind that EVERY chosen event type declares — the only ones a trend may use. */
export function commonFields(options: TrendOptions, types: string[], kind: TrendFieldOption["kind"]): TrendFieldOption[] {
  const chosen = options.event_types.filter((t: TrendEventTypeOption) => types.includes(t.name));
  if (chosen.length === 0) return [];
  const [first, ...rest] = chosen;
  return (first?.fields ?? []).filter(
    (f) => f.kind === kind && rest.every((t) => (t.fields ?? []).some((g) => g.name === f.name && g.kind === kind)),
  );
}

/** Drops a choice that the current event types no longer allow. */
function pruned(form: TrendForm, options: TrendOptions): TrendForm {
  const numbers = commonFields(options, form.types, "number").map((f) => f.name);
  const categories = commonFields(options, form.types, "category").map((f) => f.name);
  return {
    ...form,
    field: numbers.includes(form.field) ? form.field : "",
    groupBy: form.groupBy === "event_type" || categories.includes(form.groupBy) ? form.groupBy : "",
    filters: form.filters.filter((f) => categories.includes(f.field)),
  };
}

/** What the form says is missing, in words; null when it can be previewed and saved. */
export function formProblem(form: TrendForm): string | null {
  if (form.title.trim() === "") return "Give the trend a title.";
  if (form.types.length === 0) return "Choose at least one event type.";
  if (form.measure === "sum" && form.field === "") return "Choose the property to add up.";
  if (form.filters.some((f) => f.field === "" || f.value === "")) return "Choose a property and a value for every filter, or remove it.";
  return null;
}

export function definitionOf(form: TrendForm): TrendDefinitionInput {
  return {
    title: form.title.trim(),
    event_types: form.types as TrendDefinitionInput["event_types"],
    measure: form.measure,
    measure_field: form.measure === "sum" ? form.field : null,
    interval: form.interval,
    weeks: form.weeks,
    group_by: form.groupBy === "" ? null : form.groupBy,
    filters: form.filters.map((f) => ({ field: f.field, value: f.value })) as TrendDefinitionInput["filters"],
  };
}

type Pane = { kind: "preview"; figures: TrendFigures } | { kind: "saved"; trend: TrendDefinition; figures: TrendFigures };

export interface TrendsTabProps {
  api: ReportsApi;
  /** The right to record an assessment: only then is a trend offered to a pack. */
  canAssemble: boolean;
}

export function TrendsTab({ api, canAssemble }: TrendsTabProps) {
  const [options, setOptions] = useState<TrendOptions | null>(null);
  const [saved, setSaved] = useState<TrendDefinition[]>([]);
  const [packs, setPacks] = useState<ReportPack[]>([]);
  const [packId, setPackId] = useState("");
  const [pane, setPane] = useState<Pane | null>(null);
  const [form, setForm] = useState<TrendForm>(EMPTY);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // ADR-099 Amendment 9: a case reading a dataset whose events another case holds says where they are.
  const [elsewhere, setElsewhere] = useState<string | null>(null);
  // ADR-126 decision 6: the case's packs, so the form can say what it is offered from. Only a help:
  // if the case cannot be read, the line is not drawn and the builder still works.
  const [domains, setDomains] = useState<DomainPack[] | null>(null);

  const fail = (e: unknown) => setProblem((e as Error).message);

  useEffect(() => {
    let live = true;
    fetchTrendOptions(api).then((o) => live && setOptions(o)).catch((e: Error) => live && setProblem(e.message));
    listTrends(api).then((t) => live && setSaved(t)).catch((e: Error) => live && setProblem(e.message));
    // Only a help to the reader: if it cannot be asked, nothing is said and the builder still works.
    fetchCaseEvents(api.apiBaseUrl, api.bearerToken, api.investigationId)
      .then((found) => live && setElsewhere(eventsElsewhereSentence(found)))
      .catch(() => live && setElsewhere(null));
    listCases(api.apiBaseUrl, api.bearerToken)
      .then((cases) => live && setDomains(cases.find((c) => c.id === api.investigationId)?.domains ?? null))
      .catch(() => live && setDomains(null));
    if (canAssemble) {
      listPacks(api)
        .then((p) => {
          if (!live) return;
          setPacks(p);
          setPackId((current) => current || (p[0]?.id ?? ""));
        })
        .catch((e: Error) => live && setProblem(e.message));
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId, canAssemble]);

  const eventTypes = options?.event_types ?? [];
  const numbers = options ? commonFields(options, form.types, "number") : [];
  const categories = options ? commonFields(options, form.types, "category") : [];
  const missing = formProblem(form);

  function toggleType(name: string, on: boolean) {
    if (!options) return;
    const types = on ? [...form.types, name] : form.types.filter((t) => t !== name);
    setForm(pruned({ ...form, types }, options));
  }

  function valuesFor(field: string): string[] {
    const first = eventTypes.find((t) => form.types.includes(t.name));
    return (first?.fields ?? []).find((f) => f.name === field)?.values ?? [];
  }

  function setFilter(at: number, change: Partial<FilterRow>) {
    setForm({ ...form, filters: form.filters.map((f, i) => (i === at ? { ...f, ...change } : f)) });
  }

  async function preview() {
    setProblem(null);
    setNotice(null);
    try {
      setPane({ kind: "preview", figures: await previewTrend(api, definitionOf(form)) });
    } catch (e) {
      setPane(null);
      fail(e);
    }
  }

  async function save() {
    setProblem(null);
    setNotice(null);
    try {
      const made = await saveTrend(api, definitionOf(form));
      setSaved(await listTrends(api));
      setPane({ kind: "saved", trend: made, figures: await fetchTrendFigures(api, made.id) });
      setNotice(`Saved “${made.title}”.`);
    } catch (e) {
      fail(e);
    }
  }

  async function choose(trend: TrendDefinition) {
    setProblem(null);
    setNotice(null);
    try {
      setPane({ kind: "saved", trend, figures: await fetchTrendFigures(api, trend.id) });
    } catch (e) {
      setPane(null);
      fail(e);
    }
  }

  async function remove(trend: TrendDefinition) {
    setProblem(null);
    try {
      await deleteTrend(api, trend.id);
      setSaved(await listTrends(api));
      setPane(null);
      setNotice(`Deleted “${trend.title}”.`);
    } catch (e) {
      fail(e);
    }
  }

  async function addToPack(trend: TrendDefinition) {
    const pack = packs.find((p) => p.id === packId);
    if (!pack) return;
    setProblem(null);
    try {
      await addItem(api, pack.id, { kind: "trend", trend_id: trend.id });
      setNotice(`Added to ${pack.title}`);
    } catch (e) {
      fail(e);
    }
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-16)", display: "grid", gridTemplateColumns: "minmax(18rem, 24rem) 1fr", gap: "var(--sp-16)", alignContent: "start", alignItems: "start" }}>
      <div style={{ display: "grid", gap: "var(--sp-16)" }}>
        <section aria-label="Saved trends" style={{ display: "grid", gap: "var(--sp-8)" }}>
          <h3 className="value" style={{ margin: 0 }}>Saved trends</h3>
          {saved.length === 0 && <p className="label" style={{ margin: 0 }}>No trends are saved in this case yet.</p>}
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
            {saved.map((t) => (
              <li key={t.id}>
                <Button aria-pressed={pane?.kind === "saved" && pane.trend.id === t.id} onClick={() => void choose(t)}>
                  {t.title}
                </Button>
                {t.outside_case_domains && (
                  <span className="label" style={{ marginLeft: "var(--sp-8)" }}>
                    Uses link types outside this case&apos;s domain models
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>

        <form
          aria-label="New trend"
          onSubmit={(e) => e.preventDefault()}
          style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-8)" }}
        >
          {domains !== null && domains.length < DOMAIN_PACKS.length && (
            <p className="label" style={{ margin: 0 }}>
              {`This case's domain models are ${domainLabels(domains)}; an Author can change them in the Cases drawer, beside 'Data this case reads'.`}
            </p>
          )}
          <h3 className="value" style={{ margin: 0 }}>New trend</h3>
          <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            Title
            <Input value={form.title} maxLength={120} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </label>
          <fieldset style={{ border: 0, margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
            <legend className="label">Event types</legend>
            {eventTypes.length === 0 && <span className="label">{options ? "This case has no event types to count." : "Reading what can be counted…"}</span>}
            {eventTypes.map((t) => (
              <label key={t.name} className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                <Checkbox checked={form.types.includes(t.name)} onChange={(e) => toggleType(t.name, e.target.checked)} />
                {t.label}
              </label>
            ))}
          </fieldset>
          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span className="label">Measure</span>
            <RadioGroup
              name="trend-measure"
              aria-label="Measure"
              options={[{ value: "count", label: "Count" }, { value: "sum", label: "Sum" }]}
              value={form.measure}
              onChange={(measure) => setForm({ ...form, measure: measure as TrendForm["measure"], field: measure === "sum" ? form.field : "" })}
            />
          </div>
          {form.measure === "sum" && (
            <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
              Property to add up
              <Select aria-label="Property to add up" value={form.field} onChange={(e) => setForm({ ...form, field: e.target.value })}>
                <option value="">{numbers.length === 0 ? "No number is declared by every chosen type" : "Choose a property"}</option>
                {numbers.map((f) => (
                  <option key={f.name} value={f.name}>{f.name}</option>
                ))}
              </Select>
            </label>
          )}
          <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            Interval
            <Select aria-label="Interval" value={form.interval} onChange={(e) => setForm({ ...form, interval: e.target.value as TrendForm["interval"] })}>
              <option value="week">Week</option>
              <option value="month">Month</option>
            </Select>
          </label>
          <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            Weeks back
            <Select aria-label="Weeks back" value={String(form.weeks)} onChange={(e) => setForm({ ...form, weeks: Number(e.target.value) })}>
              {WEEKS.map((w) => (
                <option key={w} value={w}>{w}</option>
              ))}
            </Select>
          </label>
          <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            Series
            <Select aria-label="Series" value={form.groupBy} onChange={(e) => setForm({ ...form, groupBy: e.target.value })}>
              <option value="">None</option>
              <option value="event_type">By event type</option>
              {categories.map((f) => (
                <option key={f.name} value={f.name}>{`By ${f.name}`}</option>
              ))}
            </Select>
          </label>
          <fieldset style={{ border: 0, margin: 0, padding: 0, display: "grid", gap: "var(--sp-8)" }}>
            <legend className="label">Filters</legend>
            {form.filters.map((row, at) => {
              const values = valuesFor(row.field);
              return (
                <div key={at} style={{ display: "flex", gap: "var(--sp-4)", flexWrap: "wrap", alignItems: "center" }}>
                  <Select aria-label="Filter property" value={row.field} onChange={(e) => setFilter(at, { field: e.target.value, value: "" })}>
                    <option value="">Choose a property</option>
                    {categories.map((f) => (
                      <option key={f.name} value={f.name}>{f.name}</option>
                    ))}
                  </Select>
                  {values.length > 0 ? (
                    <Select aria-label="Filter value" value={row.value} onChange={(e) => setFilter(at, { value: e.target.value })}>
                      <option value="">Choose a value</option>
                      {values.map((v) => (
                        <option key={v} value={v}>{v}</option>
                      ))}
                    </Select>
                  ) : (
                    <Input aria-label="Filter value" value={row.value} onChange={(e) => setFilter(at, { value: e.target.value })} />
                  )}
                  <Button onClick={() => setForm({ ...form, filters: form.filters.filter((_, i) => i !== at) })}>Remove filter</Button>
                </div>
              );
            })}
            <div>
              <Button
                disabled={form.filters.length >= MAX_FILTERS || categories.length === 0}
                onClick={() => setForm({ ...form, filters: [...form.filters, { field: "", value: "" }] })}
              >
                Add filter
              </Button>
            </div>
            {form.filters.length >= MAX_FILTERS && <span className="label">A trend may have at most five filters.</span>}
          </fieldset>
          {missing && <p className="label" style={{ margin: 0 }}>{missing}</p>}
          <div style={{ display: "flex", gap: "var(--sp-8)" }}>
            <Button disabled={missing !== null} onClick={() => void preview()}>Preview</Button>
            <Button variant="primary" disabled={missing !== null} onClick={() => void save()}>Save trend</Button>
          </div>
        </form>
      </div>

      <section aria-label="Trend" style={{ display: "grid", gap: "var(--sp-8)", alignContent: "start" }}>
        {elsewhere && (
          <p role="note" aria-label="Where this case's events are" className="label" style={{ margin: 0 }}>{elsewhere}</p>
        )}
        {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
        {notice && <p role="status" style={{ margin: 0 }}>{notice}</p>}
        {!pane && !problem && <p className="label" style={{ margin: 0 }}>Preview a trend, or choose a saved one, to see it here.</p>}
        {pane && (
          <>
            <h3 style={{ margin: 0 }}>{pane.figures.definition.title}</h3>
            {pane.figures.marking && <p className="label" style={{ margin: 0 }}>{`Marked ${pane.figures.marking}`}</p>}
            <TrendChart figures={pane.figures} />
            {pane.kind === "saved" && (
              <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
                {canAssemble && packs.length > 0 && (
                  <>
                    <Select aria-label="Pack" value={packId} onChange={(e) => setPackId(e.target.value)}>
                      {packs.map((p) => (
                        <option key={p.id} value={p.id}>{p.title}</option>
                      ))}
                    </Select>
                    <Button onClick={() => void addToPack(pane.trend)}>Add to pack</Button>
                  </>
                )}
                {canAssemble && packs.length === 0 && <span className="label">Create a pack in the Packs tab to add this trend to it.</span>}
                <Button onClick={() => void remove(pane.trend)}>Delete</Button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
