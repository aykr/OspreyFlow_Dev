// The case's typology rules (`06_DECISIONS.md` ADR-109 phase A, rulings 1 and 4): what watches this
// case's loads, where each runs, and — for an Author — deploying one and retiring one. A rule is a
// typology with its parameters, a closed list per typology (rule 8: no expression language).
import { useCallback, useEffect, useState } from "react";
import type { TypologyRule, TypologyRuleInput } from "../../../../packages/schemas/generated";
import { Button, Input, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import { deployRule, listRules, retireRule, type AlertsApi } from "./api";
import { money, typologyLabel, when } from "./names";

type Typology = "structuring" | "rapid_movement" | "circular_flow";

interface Field {
  key: string;
  label: string;
  step: string;
  fallback: number;
}

/** Each typology's parameters, in the order the server's models declare them. */
export const PARAMETERS: Record<Typology, Field[]> = {
  structuring: [
    { key: "threshold", label: "Reportable amount", step: "1", fallback: 10000 },
    { key: "window_days", label: "Within (days)", step: "1", fallback: 7 },
    { key: "minimum_count", label: "At least (movements)", step: "1", fallback: 3 },
  ],
  rapid_movement: [
    { key: "within_hours", label: "Leaves within (hours)", step: "1", fallback: 48 },
    { key: "keep_fraction", label: "Share that leaves (0 to 1)", step: "0.05", fallback: 0.8 },
  ],
  circular_flow: [
    { key: "max_hops", label: "At most (movements round)", step: "1", fallback: 4 },
    { key: "window_days", label: "Within (days)", step: "1", fallback: 30 },
  ],
};

export function describeParams(rule: TypologyRule): string {
  const p = rule.params as unknown as Record<string, number | undefined>;
  const n = (key: string) => p[key] ?? 0;
  switch (rule.params.typology) {
    case "structuring":
      return `${n("minimum_count")}+ movements each under ${money(n("threshold"))}, summing past it, within ${n("window_days")} day(s)`;
    case "rapid_movement":
      return `${Math.round(n("keep_fraction") * 100)}% or more leaving within ${n("within_hours")} hour(s) of arriving`;
    default:
      return `value back where it started in ${n("max_hops")} movements or fewer, within ${n("window_days")} day(s)`;
  }
}

/** The form's values as the server's input, numbers as numbers. */
export function ruleInput(
  name: string,
  typology: Typology,
  values: Record<string, string>,
  trigger: "pre_commit" | "post_commit",
  budgetMs: number,
): TypologyRuleInput {
  const params: Record<string, unknown> = { typology };
  for (const field of PARAMETERS[typology]) params[field.key] = Number(values[field.key] ?? field.fallback);
  return { name: name.trim(), params: params as unknown as TypologyRuleInput["params"], trigger, budget_ms: budgetMs };
}

export interface RulesPanelProps extends AlertsApi {
  level: AccessLevel | null;
}

export function RulesPanel(props: RulesPanelProps) {
  const { apiBaseUrl, bearerToken, investigationId, level } = props;
  const [rules, setRules] = useState<TypologyRule[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const author = level === "author";

  const reload = useCallback(() => {
    listRules({ apiBaseUrl, bearerToken, investigationId })
      .then(setRules)
      .catch((e: Error) => setProblem(e.message));
  }, [apiBaseUrl, bearerToken, investigationId]);
  useEffect(reload, [reload]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16)" }}>
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
      {said && <p role="status" className="label">{said}</p>}
      {rules !== null && rules.length === 0 && <p className="label">No rules watch this case yet.</p>}
      <ul aria-label="Rules" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {(rules ?? []).map((rule) => (
          <li key={rule.id} style={{ borderBottom: "1px solid var(--border-subtle)", padding: "var(--sp-8) 0", display: "flex", justifyContent: "space-between", gap: "var(--sp-12)" }}>
            <span style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
              <span className="value">
                {rule.name} · {typologyLabel(rule.params.typology)}
              </span>
              <span className="label">{describeParams(rule)}</span>
              <span className="label">
                {rule.trigger === "pre_commit"
                  ? `Judges each load before it commits (budget ${rule.budget_ms ?? 5000} ms; held if it cannot judge)`
                  : "Runs after each load commits"}{" "}
                · {rule.status === "retired" ? `retired ${rule.retired_at ? when(rule.retired_at) : ""}` : "active"}
              </span>
            </span>
            {author && rule.status === "active" && (
              <Button
                aria-label={`Retire ${rule.name}`}
                onClick={() =>
                  void retireRule(props, rule.id)
                    .then(() => {
                      setSaid(`Retired “${rule.name}”.`);
                      reload();
                    })
                    .catch((e: Error) => setProblem(e.message))
                }
              >
                Retire
              </Button>
            )}
          </li>
        ))}
      </ul>
      {author ? (
        <DeployForm
          {...props}
          onDeployed={(rule) => {
            setSaid(`Deployed “${rule.name}”.`);
            reload();
          }}
        />
      ) : (
        <p className="label">A case Author deploys and retires rules.</p>
      )}
    </div>
  );
}

function DeployForm(props: RulesPanelProps & { onDeployed: (rule: TypologyRule) => void }) {
  const [name, setName] = useState("");
  const [typology, setTypology] = useState<Typology>("structuring");
  const [values, setValues] = useState<Record<string, string>>({});
  const [trigger, setTrigger] = useState<"pre_commit" | "post_commit">("post_commit");
  const [budget, setBudget] = useState("5000");
  const [problem, setProblem] = useState<string | null>(null);

  return (
    <form
      aria-label="Deploy a rule"
      onSubmit={(e) => {
        e.preventDefault();
        setProblem(null);
        deployRule(props, ruleInput(name, typology, values, trigger, Number(budget)))
          .then((rule) => {
            setName("");
            props.onDeployed(rule);
          })
          .catch((err: Error) => setProblem(err.message));
      }}
      style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}
    >
      <h3 className="value" style={{ margin: 0 }}>Deploy a rule</h3>
      <label className="label">
        Name
        <Input value={name} onChange={(e) => setName(e.target.value)} required aria-label="Rule name" />
      </label>
      <label className="label">
        Typology
        <Select
          aria-label="Typology"
          value={typology}
          onChange={(e) => {
            setTypology(e.target.value as Typology);
            setValues({});
          }}
        >
          <option value="structuring">Structuring</option>
          <option value="rapid_movement">Rapid movement</option>
          <option value="circular_flow">Circular flow</option>
        </Select>
      </label>
      {PARAMETERS[typology].map((field) => (
        <label key={field.key} className="label">
          {field.label}
          <Input
            type="number"
            step={field.step}
            aria-label={field.label}
            value={values[field.key] ?? String(field.fallback)}
            onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
          />
        </label>
      ))}
      <label className="label">
        Runs
        <Select aria-label="When the rule runs" value={trigger} onChange={(e) => setTrigger(e.target.value as "pre_commit" | "post_commit")}>
          <option value="post_commit">After each load commits</option>
          <option value="pre_commit">Before each load commits</option>
        </Select>
      </label>
      {trigger === "pre_commit" && (
        <label className="label">
          Time budget (ms) — a load it cannot judge in time is held for review
          <Input type="number" step="100" aria-label="Time budget" value={budget} onChange={(e) => setBudget(e.target.value)} />
        </label>
      )}
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
      <Button type="submit" variant="primary" disabled={!name.trim()}>
        Deploy
      </Button>
    </form>
  );
}
