// Write a rule as a sentence (`06_DECISIONS.md` ADR-133 decisions 1 and 3, stage (b)): "When a
// <subject> whose <conditions>, <relationship>, <how often>, raise a <severity> alert for <whom>,
// <when>." Every blank is a choice from the deployment's ontology (rule 8: nothing typed is parsed).
// The drawn pattern is the sentence's advanced view: shown here, opened in the Query builder once
// deployed (it is saved as the author's), and a saved pattern reads back as a sentence. "Preview on
// the last 90 days" says how many alerts the rule would have raised, as its author, and shows up to
// five; it raises and writes nothing.
import { useEffect, useMemo, useState } from "react";
import type {
  CompiledSentence,
  OntologySchema,
  RulePreview,
  SavedPattern,
  TypologyRule,
} from "../../../../packages/schemas/generated";
import { Button, Input, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import {
  compileSentence,
  deploySentence,
  previewRule,
  readOntology,
  readSentence,
  type AlertsApi,
} from "./api";
import {
  MAX_CONDITIONS,
  OP_WORDS,
  POLE_WORDS,
  amountsFor,
  emptyCondition,
  emptyDraft,
  eventLinksFor,
  fromSentence,
  linkLabel,
  linksFor,
  opsFor,
  otherEndsFor,
  propertiesFor,
  subjectsByPole,
  toSentence,
  unfinished,
  type AreaBox,
  type ConditionDraft,
  type Op,
  type SentenceDraft,
  WEEKDAY_WORDS,
} from "./sentence";

const ROW = { display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "end" } as const;
const BLANK = { display: "grid", gap: "var(--sp-4)" } as const;
const GROUP = { border: "1px solid var(--border-subtle)", padding: "var(--sp-8) var(--sp-12)", margin: 0, display: "grid", gap: "var(--sp-8)" } as const;

export interface SentenceBuilderProps extends AlertsApi {
  level: AccessLevel | null;
  isAdministrator: boolean;
  patterns: SavedPattern[];
  onDeployed: (rule: TypologyRule) => void;
}

function AreaBlanks(props: { label: string; area: AreaBox; onChange: (area: AreaBox) => void }) {
  const corner = (key: keyof AreaBox, words: string) => (
    <label className="label" style={BLANK}>
      {words}
      <Input
        type={key === "name" ? "text" : "number"}
        step="any"
        aria-label={`${props.label}: ${words}`}
        value={props.area[key]}
        onChange={(e) => props.onChange({ ...props.area, [key]: e.target.value })}
        style={{ width: key === "name" ? 160 : 96 }}
      />
    </label>
  );
  return (
    <span style={ROW}>
      {corner("name", "Area name")}
      {corner("west", "West (longitude)")}
      {corner("south", "South (latitude)")}
      {corner("east", "East (longitude)")}
      {corner("north", "North (latitude)")}
    </span>
  );
}

function ConditionRow(props: {
  index: number;
  row: ConditionDraft;
  ontology: OntologySchema;
  subject: string;
  onChange: (row: ConditionDraft) => void;
  onRemove: () => void;
}) {
  const { row, index } = props;
  const properties = propertiesFor(props.ontology, props.subject);
  const declared = properties.find((p) => p.name === row.property);
  const ops = opsFor(declared);
  const n = index + 1;
  return (
    <div role="group" aria-label={`Condition ${n}`} style={ROW}>
      <label className="label" style={BLANK}>
        Property
        <Select
          aria-label={`Condition ${n}: property`}
          value={row.property}
          onChange={(e) => {
            const next = properties.find((p) => p.name === e.target.value);
            props.onChange(emptyCondition(e.target.value, opsFor(next)[0] ?? "equals"));
          }}
        >
          {properties.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
      </label>
      <label className="label" style={BLANK}>
        Test
        <Select aria-label={`Condition ${n}: test`} value={row.op} onChange={(e) => props.onChange({ ...emptyCondition(row.property, e.target.value as Op) })}>
          {ops.map((op) => (
            <option key={op} value={op}>
              {OP_WORDS[op]}
            </option>
          ))}
        </Select>
      </label>
      {(row.op === "equals" || row.op === "above" || row.op === "below") &&
        (declared?.type === "enum" || declared?.type === "boolean" ? (
          <label className="label" style={BLANK}>
            Value
            <Select aria-label={`Condition ${n}: value`} value={row.value} onChange={(e) => props.onChange({ ...row, value: e.target.value })}>
              <option value="">Choose…</option>
              {(declared.type === "boolean" ? ["true", "false"] : (declared.values ?? [])).map((v) => (
                <option key={v} value={v}>
                  {declared.type === "boolean" ? (v === "true" ? "yes" : "no") : v.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </label>
        ) : (
          <label className="label" style={BLANK}>
            Value
            <Input
              aria-label={`Condition ${n}: value`}
              type={row.op === "equals" && declared && !["integer", "float"].includes(declared.type) ? "text" : "number"}
              step="any"
              value={row.value}
              onChange={(e) => props.onChange({ ...row, value: e.target.value })}
            />
          </label>
        ))}
      {row.op === "one_of" && (
        <fieldset style={{ ...ROW, border: "none", padding: 0, margin: 0 }}>
          <legend className="label">Values</legend>
          {declared?.type === "enum" ? (
            (declared.values ?? []).map((v) => (
              <label key={v} className="label" style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
                <input
                  type="checkbox"
                  aria-label={`Condition ${n}: ${v.replace(/_/g, " ")}`}
                  checked={row.values.includes(v)}
                  onChange={(e) => props.onChange({ ...row, values: e.target.checked ? [...row.values, v] : row.values.filter((x) => x !== v) })}
                />
                {v.replace(/_/g, " ")}
              </label>
            ))
          ) : (
            <Input
              aria-label={`Condition ${n}: values, one per line`}
              value={row.values.join("\n")}
              onChange={(e) => props.onChange({ ...row, values: e.target.value.split("\n").map((v) => v.trim()).filter(Boolean) })}
            />
          )}
        </fieldset>
      )}
      {row.op === "within_time" && (
        <>
          <label className="label" style={BLANK}>
            From
            <Input type="date" aria-label={`Condition ${n}: from`} value={row.start} onChange={(e) => props.onChange({ ...row, start: e.target.value })} />
          </label>
          <label className="label" style={BLANK}>
            To
            <Input type="date" aria-label={`Condition ${n}: to`} value={row.end} onChange={(e) => props.onChange({ ...row, end: e.target.value })} />
          </label>
        </>
      )}
      {row.op === "within_area" && <AreaBlanks label={`Condition ${n}`} area={row.area} onChange={(area) => props.onChange({ ...row, area })} />}
      <Button type="button" aria-label={`Remove condition ${n}`} onClick={props.onRemove}>
        Remove
      </Button>
    </div>
  );
}

export function SentenceBuilder(props: SentenceBuilderProps) {
  const api = { apiBaseUrl: props.apiBaseUrl, bearerToken: props.bearerToken, investigationId: props.investigationId };
  const [ontology, setOntology] = useState<OntologySchema | null>(null);
  const [draft, setDraft] = useState<SentenceDraft>(emptyDraft());
  const [name, setName] = useState("");
  const [compiled, setCompiled] = useState<CompiledSentence | null>(null);
  const [preview, setPreview] = useState<RulePreview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [readFrom, setReadFrom] = useState("");
  const canDeployCase = props.level === "author";
  const canDeploy = canDeployCase || props.level === "editor";

  useEffect(() => {
    readOntology(api)
      .then(setOntology)
      .catch((e: Error) => setProblem(e.message));
    // The ontology is the deployment's: read once per builder.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.apiBaseUrl, props.bearerToken]);

  const change = (next: Partial<SentenceDraft>) => {
    setDraft((d) => ({ ...d, ...next }));
    setCompiled(null);
    setPreview(null);
    setProblem(null);
  };
  const subjects = useMemo(() => (ontology ? subjectsByPole(ontology) : []), [ontology]);
  if (!ontology) return problem ? <p role="alert" style={{ color: "var(--error)" }}>{problem}</p> : <p className="label">Reading the ontology…</p>;

  const properties = propertiesFor(ontology, draft.subject);
  const links = linksFor(ontology, draft.subject);
  const eventLinks = eventLinksFor(ontology, draft.subject);
  const others = draft.linkType ? otherEndsFor(ontology, draft.subject, draft.linkType) : [];
  const locationLinks = links.filter((l) => otherEndsFor(ontology, draft.subject, l.name).includes("Location"));
  const amounts = draft.frequencyLink ? amountsFor(ontology, draft.frequencyLink) : [];
  const missing = unfinished(draft);
  const graphLink = ["linked", "within_steps", "at_location"].includes(draft.relationship);
  const justMe = draft.scope === "just_me";
  const allowedToDeploy = draft.scope === "just_me" ? canDeploy : canDeployCase && (draft.scope !== "deployment" || props.isAdministrator);

  const run = (what: () => Promise<void>) => {
    if (missing) {
      setProblem(missing);
      return;
    }
    setBusy(true);
    setProblem(null);
    what()
      .catch((e: Error) => setProblem(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <form
      aria-label="Write a rule as a sentence"
      onSubmit={(e) => {
        e.preventDefault();
        run(async () => {
          const rule = await deploySentence(api, name.trim(), toSentence(draft));
          setName("");
          props.onDeployed(rule);
        });
      }}
      style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-12)", maxWidth: 880 }}
    >
      <h3 className="value" style={{ margin: 0 }}>
        Write a rule as a sentence
      </h3>
      <p className="label" style={{ margin: 0 }}>
        Fill each blank from the lists. Preview it on the last 90 days before you deploy it.
      </p>

      <fieldset style={GROUP}>
        <legend className="label">When a…</legend>
        <span style={ROW}>
          <label className="label" style={BLANK}>
            Subject
            <Select
              aria-label="Subject"
              value={draft.subject}
              onChange={(e) => change({ ...emptyDraft(e.target.value), severity: draft.severity, scope: draft.scope, team: draft.team })}
            >
              {subjects.map(([pole, types]) => (
                <optgroup key={pole} label={POLE_WORDS[pole] ?? pole}>
                  {types.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </label>
        </span>
      </fieldset>

      <fieldset style={GROUP}>
        <legend className="label">…whose</legend>
        {draft.conditions.length === 0 && <p className="label" style={{ margin: 0 }}>No conditions: any {draft.subject}.</p>}
        {draft.conditions.map((row, i) => (
          <ConditionRow
            key={i}
            index={i}
            row={row}
            ontology={ontology}
            subject={draft.subject}
            onChange={(next) => change({ conditions: draft.conditions.map((c, j) => (j === i ? next : c)) })}
            onRemove={() => change({ conditions: draft.conditions.filter((_, j) => j !== i) })}
          />
        ))}
        {properties.length > 0 && draft.conditions.length < MAX_CONDITIONS && (
          <span>
            <Button type="button"
              onClick={() => {
                const free = properties.find((p) => !draft.conditions.some((c) => c.property === p.name)) ?? properties[0];
                if (!free) return;
                change({ conditions: [...draft.conditions, emptyCondition(free.name, opsFor(free)[0] ?? "equals")] });
              }}
            >
              Add a condition
            </Button>
          </span>
        )}
      </fieldset>

      <fieldset style={GROUP}>
        <legend className="label">…and is</legend>
        <span style={ROW}>
          <label className="label" style={BLANK}>
            Relationship
            <Select aria-label="Relationship" value={draft.relationship} onChange={(e) => {
                const relationship = e.target.value as SentenceDraft["relationship"];
                const fromTheGraph = ["linked", "within_steps", "at_location"].includes(relationship);
                change({ relationship, linkType: "", otherType: "", ...(fromTheGraph ? { runs: "post_commit", onHit: "load" } : {}) });
              }}>
              <option value="none">(no relationship)</option>
              <option value="linked">linked by a link type to…</option>
              <option value="within_steps">within a number of steps of…</option>
              {locationLinks.length > 0 && <option value="at_location">at a location in a drawn area</option>}
              <option value="on_hotlist">on one of my hotlists</option>
              {(draft.subject === "Person" || draft.subject === "Organisation") && <option value="on_screening_list">on a screening list</option>}
            </Select>
          </label>
          {(draft.relationship === "linked" || draft.relationship === "at_location") && (
            <label className="label" style={BLANK}>
              Link type
              <Select aria-label="Link type" value={draft.linkType} onChange={(e) => change({ linkType: e.target.value, otherType: "" })}>
                <option value="">Choose…</option>
                {(draft.relationship === "at_location" ? locationLinks : links).map((l) => (
                  <option key={l.name} value={l.name}>
                    {linkLabel(l)}
                  </option>
                ))}
              </Select>
            </label>
          )}
          {draft.relationship === "linked" && draft.linkType && (
            <label className="label" style={BLANK}>
              To
              <Select aria-label="Linked to" value={draft.otherType} onChange={(e) => change({ otherType: e.target.value })}>
                <option value="">anything</option>
                {others.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </label>
          )}
          {draft.relationship === "within_steps" && (
            <>
              <label className="label" style={BLANK}>
                Steps
                <Select aria-label="Steps" value={draft.steps} onChange={(e) => change({ steps: e.target.value })}>
                  {["1", "2", "3", "4"].map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="label" style={BLANK}>
                Of a
                <Select aria-label="Of a (the type near it)" value={draft.otherType} onChange={(e) => change({ otherType: e.target.value })}>
                  <option value="">Choose…</option>
                  {ontology.entity_types
                    .filter((t) => t.name !== "Alert")
                    .map((t) => (
                      <option key={t.name} value={t.name}>
                        {t.name}
                      </option>
                    ))}
                </Select>
              </label>
            </>
          )}
          {draft.relationship === "on_screening_list" && (
            <label className="label" style={BLANK}>
              Name match at least
              <Select aria-label="Name match at least" value={draft.minScore} onChange={(e) => change({ minScore: e.target.value })}>
                {["0.8", "0.85", "0.9", "0.95"].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </label>
          )}
        </span>
        {draft.relationship === "at_location" && <AreaBlanks label="Area" area={draft.area} onChange={(area) => change({ area })} />}
      </fieldset>

      <fieldset style={GROUP}>
        <legend className="label">…how often</legend>
        <span style={ROW}>
          <label className="label" style={BLANK}>
            Frequency
            <Select aria-label="Frequency" value={draft.frequency} onChange={(e) => change({ frequency: e.target.value as SentenceDraft["frequency"], frequencyLink: eventLinks[0]?.name ?? "" })}>
              <option value="none">(any number of times)</option>
              {eventLinks.length > 0 && <option value="count">a number of times or more within some days</option>}
              {eventLinks.length > 0 && <option value="amount">a total amount over a figure within some days</option>}
              {eventLinks.length > 0 && <option value="first_time">for the first time ever</option>}
            </Select>
          </label>
          {draft.frequency !== "none" && (
            <label className="label" style={BLANK}>
              By
              <Select aria-label="By (counted link type)" value={draft.frequencyLink} onChange={(e) => change({ frequencyLink: e.target.value, amountProperty: "" })}>
                {eventLinks.map((l) => (
                  <option key={l.name} value={l.name}>
                    {linkLabel(l)}
                  </option>
                ))}
              </Select>
            </label>
          )}
          {draft.frequency === "count" && (
            <label className="label" style={BLANK}>
              Times or more
              <Input type="number" min={2} aria-label="Times or more" value={draft.atLeast} onChange={(e) => change({ atLeast: e.target.value })} style={{ width: 96 }} />
            </label>
          )}
          {draft.frequency === "amount" && (
            <>
              <label className="label" style={BLANK}>
                Total of
                <Select aria-label="Total of (amount)" value={draft.amountProperty} onChange={(e) => change({ amountProperty: e.target.value })}>
                  <option value="">Choose…</option>
                  {amounts.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name.replace(/_/g, " ")}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="label" style={BLANK}>
                Over
                <Input type="number" min={0} step="any" aria-label="Over" value={draft.over} onChange={(e) => change({ over: e.target.value })} style={{ width: 120 }} />
              </label>
            </>
          )}
          {(draft.frequency === "count" || draft.frequency === "amount") && (
            <label className="label" style={BLANK}>
              Within (days)
              <Input type="number" min={1} max={366} aria-label="Within (days)" value={draft.withinDays} onChange={(e) => change({ withinDays: e.target.value })} style={{ width: 96 }} />
            </label>
          )}
        </span>
      </fieldset>

      <fieldset style={GROUP}>
        <legend className="label">…then</legend>
        <span style={ROW}>
          <label className="label" style={BLANK}>
            Severity
            <Select aria-label="Severity" value={draft.severity} onChange={(e) => change({ severity: e.target.value as SentenceDraft["severity"] })}>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </Select>
          </label>
          <label className="label" style={BLANK}>
            For
            <Select
              aria-label="For (scope)"
              value={draft.scope}
              onChange={(e) => {
                const scope = e.target.value as SentenceDraft["scope"];
                // A runs choice the new scope does not offer goes back to "after each load commits".
                const offered = !(scope === "just_me" && draft.runs === "pre_commit") && !(scope === "deployment" && draft.runs === "schedule");
                change({ scope, ...(offered ? {} : { runs: "post_commit", onHit: "load" }) });
              }}
            >
              <option value="just_me">just me</option>
              <option value="this_case">this case</option>
              {props.isAdministrator && <option value="deployment">the whole deployment</option>}
            </Select>
          </label>
          {!justMe && (
            <label className="label" style={BLANK}>
              Alert goes to
              <Select aria-label="Alert goes to (team)" value={draft.team} onChange={(e) => change({ team: e.target.value as SentenceDraft["team"] })}>
                <option value="case">the case team</option>
                <option value="my_team">my team</option>
              </Select>
            </label>
          )}
          <label className="label" style={BLANK}>
            Runs
            <Select aria-label="Runs" value={draft.runs} onChange={(e) => change({ runs: e.target.value as SentenceDraft["runs"], onHit: "load" })}>
              <option value="post_commit">after each load commits</option>
              {!graphLink && !justMe && <option value="pre_commit">before each load commits</option>}
              {/* ADR-133 stage (d): daily or weekly; never for the whole deployment, which is
                  judged within each case as its data loads. */}
              {draft.scope !== "deployment" && <option value="schedule">on a schedule</option>}
            </Select>
          </label>
          {draft.runs === "schedule" && draft.scope !== "deployment" && (
            <>
              <label className="label" style={BLANK}>
                Every
                <Select aria-label="Every" value={draft.every} onChange={(e) => change({ every: e.target.value as SentenceDraft["every"] })}>
                  <option value="daily">day</option>
                  <option value="weekly">week</option>
                </Select>
              </label>
              {draft.every === "weekly" && (
                <label className="label" style={BLANK}>
                  On
                  <Select aria-label="On (day of the week)" value={draft.weekday} onChange={(e) => change({ weekday: e.target.value })}>
                    {WEEKDAY_WORDS.map((day, i) => (
                      <option key={day} value={String(i + 1)}>
                        {day}
                      </option>
                    ))}
                  </Select>
                </label>
              )}
              <label className="label" style={BLANK}>
                At (Europe/London)
                <Select aria-label="At (hour, Europe/London)" value={draft.hour} onChange={(e) => change({ hour: e.target.value })}>
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={String(h)}>
                      {`${String(h).padStart(2, "0")}:00`}
                    </option>
                  ))}
                </Select>
              </label>
            </>
          )}
          {!justMe && draft.runs === "pre_commit" && (
            <label className="label" style={BLANK}>
              A hit
              <Select aria-label="A hit" value={draft.onHit} onChange={(e) => change({ onHit: e.target.value as SentenceDraft["onHit"] })}>
                <option value="load">loads with its alert</option>
                <option value="hold">holds its rows for review</option>
              </Select>
            </label>
          )}
        </span>
        {graphLink && !justMe && <p className="label" style={{ margin: 0 }}>A link is read from the stored graph, so this rule runs after each load commits.</p>}
      </fieldset>

      <span style={ROW}>
        <Button type="button"
          disabled={busy}
          onClick={() =>
            run(async () => {
              setCompiled(await compileSentence(api, toSentence(draft)));
            })
          }
        >
          Show the drawn pattern
        </Button>
        <Button type="button"
          variant="primary"
          disabled={busy}
          onClick={() =>
            run(async () => {
              setPreview(await previewRule(api, toSentence(draft)));
            })
          }
        >
          Preview on the last 90 days
        </Button>
      </span>

      {problem && (
        <p role="alert" style={{ color: "var(--error)", margin: 0 }}>
          {problem}
        </p>
      )}

      {compiled && (
        <section aria-label="The drawn pattern" style={GROUP}>
          <p className="value" style={{ margin: 0 }}>
            {compiled.words}
          </p>
          <p className="label" style={{ margin: 0 }}>
            As a drawn pattern: {compiled.pattern.nodes.map((n) => `${n.entity_type ?? "anything"}${Object.keys(n.where ?? {}).length ? ` (${Object.entries(n.where ?? {}).map(([k, v]) => `${k.replace(/_/g, " ")} = ${v}`).join(", ")})` : ""}`).join(compiled.pattern.edges.length ? ` — ${compiled.pattern.edges[0]?.edge_type} — ` : ", ")}
            . Once deployed it is saved to your patterns, to open in the Query builder.
          </p>
        </section>
      )}

      {preview && (
        <section aria-label="Preview" aria-live="polite" style={GROUP}>
          <p className="value" style={{ margin: 0 }} role="status">
            {preview.would_raise === 0
              ? `It would have raised no alerts in the last ${preview.days} days.`
              : `It would have raised ${preview.would_raise.toLocaleString("en-GB")} alert${preview.would_raise === 1 ? "" : "s"} in the last ${preview.days} days.`}
          </p>
          {(preview.examples ?? []).length > 0 && (
            <>
              <p className="label" style={{ margin: 0 }}>
                {preview.would_raise > (preview.examples ?? []).length ? `The first ${(preview.examples ?? []).length}:` : "They are:"}
              </p>
              <ul aria-label="Preview examples" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
                {(preview.examples ?? []).map((e) => (
                  <li key={e.node_id} className="label">
                    {e.words}
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="label" style={{ margin: 0 }}>
            Counted as you, over what you may see. Nothing was raised or written.
          </p>
        </section>
      )}

      {props.patterns.length > 0 && (
        <span style={ROW}>
          <label className="label" style={BLANK}>
            Read a saved pattern as a sentence
            <Select aria-label="Read a saved pattern as a sentence" value={readFrom} onChange={(e) => setReadFrom(e.target.value)}>
              <option value="">Choose one you saved…</option>
              {props.patterns.map((p) => (
                <option key={p.pattern_id} value={p.pattern_id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </label>
          <Button type="button"
            disabled={!readFrom || busy}
            onClick={() => {
              const saved = props.patterns.find((p) => p.pattern_id === readFrom);
              if (!saved) return;
              setBusy(true);
              setProblem(null);
              readSentence(api, saved.definition, toSentence(draft))
                .then((sentence) => {
                  setDraft(fromSentence(sentence));
                  setCompiled(null);
                  setPreview(null);
                })
                .catch((e: Error) => setProblem(e.message))
                .finally(() => setBusy(false));
            }}
          >
            Read as a sentence
          </Button>
        </span>
      )}

      {canDeploy ? (
        <span style={ROW}>
          <label className="label" style={BLANK}>
            Name
            <Input aria-label="Name of the sentence rule" value={name} onChange={(e) => setName(e.target.value)} style={{ width: 280 }} />
          </label>
          <Button type="submit" disabled={!name.trim() || busy || !allowedToDeploy}>
            Deploy the sentence
          </Button>
          {!allowedToDeploy && <span className="label">Only “just me” is yours to deploy at your level in this case.</span>}
        </span>
      ) : (
        <p className="label" style={{ margin: 0 }}>
          A case Editor deploys a rule for themselves; a case Author deploys one for the case.
        </p>
      )}
    </form>
  );
}
