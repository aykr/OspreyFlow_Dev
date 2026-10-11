// The case's typology rules (`06_DECISIONS.md` ADR-109 phase A, rulings 1 and 4): what watches this
// case's loads, where each runs, and — for an Author — deploying one and retiring one. A rule is a
// typology with its parameters, a closed list per typology (rule 8: no expression language).
import { useCallback, useEffect, useState } from "react";
import type {
  SavedPattern,
  TypologyRule,
  TypologyRuleInput,
} from "../../../../packages/schemas/generated";
import { Button, Input, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import { listPatterns } from "../patterns/api";
import { deployRule, listRules, retireRule, type AlertsApi } from "./api";
import { money, ruleTypologyLabel, when } from "./names";

type Typology =
  | "structuring"
  | "rapid_movement"
  | "circular_flow"
  | "kyc_screening"
  | "shared_attributes"
  | "document_verification"
  | "pattern";

interface Field {
  key: string;
  label: string;
  step: string;
  fallback: number;
}

/** ADR-109 phase F: a typology's yes-or-no setting, sent as a boolean. */
interface Choice {
  key: string;
  label: string;
  fallback: boolean;
}

/** Each KYC typology's switches, in the order the server's models declare them. */
export const CHOICES: Partial<Record<Typology, Choice[]>> = {
  kyc_screening: [
    {
      key: "screen_owners",
      label: "Screen beneficial owners too",
      fallback: true,
    },
  ],
};

/** The shared-attribute typology's closed list of what may be shared. */
/** A form field: its label above its input, the input the form's full width. */
const FIELD = { display: "grid", gap: "var(--sp-4)" } as const;

export const SHARED_KINDS = ["msisdn", "email", "ip", "handle"] as const;

/** Each typology's parameters, in the order the server's models declare them. */
export const PARAMETERS: Record<Typology, Field[]> = {
  structuring: [
    {
      key: "threshold",
      label: "Reportable amount",
      step: "1",
      fallback: 10000,
    },
    { key: "window_days", label: "Within (days)", step: "1", fallback: 7 },
    {
      key: "minimum_count",
      label: "At least (movements)",
      step: "1",
      fallback: 3,
    },
  ],
  rapid_movement: [
    {
      key: "within_hours",
      label: "Leaves within (hours)",
      step: "1",
      fallback: 48,
    },
    {
      key: "keep_fraction",
      label: "Share that leaves (0 to 1)",
      step: "0.05",
      fallback: 0.8,
    },
  ],
  circular_flow: [
    {
      key: "max_hops",
      label: "At most (movements round)",
      step: "1",
      fallback: 4,
    },
    { key: "window_days", label: "Within (days)", step: "1", fallback: 30 },
  ],
  kyc_screening: [
    {
      key: "min_score",
      label: "Name match at least (0.5 to 1)",
      step: "0.01",
      fallback: 0.9,
    },
    {
      key: "owner_threshold",
      label: "Screen owners holding at least (%)",
      step: "1",
      fallback: 25,
    },
  ],
  shared_attributes: [
    {
      key: "min_others",
      label: "Used by at least (other customers)",
      step: "1",
      fallback: 3,
    },
  ],
  document_verification: [],
  // ADR-109 phase D: a pattern drawn in the Query builder and saved; it alerts on whole matches.
  pattern: [
    {
      key: "max_matches",
      label: "Alert on matches of at most (nodes)",
      step: "1",
      fallback: 200,
    },
  ],
};

export function describeParams(
  rule: TypologyRule,
  patternNames?: Map<string, string>,
): string {
  const p = rule.params as unknown as Record<string, number | undefined>;
  const n = (key: string) => p[key] ?? 0;
  switch (rule.params.typology) {
    case "structuring":
      return `${n("minimum_count")}+ movements each under ${money(n("threshold"))}, summing past it, within ${n("window_days")} day(s)`;
    case "rapid_movement":
      return `${Math.round(n("keep_fraction") * 100)}% or more leaving within ${n("within_hours")} hour(s) of arriving`;
    case "kyc_screening": {
      const owners =
        (rule.params as unknown as Record<string, unknown>).screen_owners !==
        false;
      return `new customers' names${owners ? `, and owners holding ${n("owner_threshold")}% or more,` : ""} screened at ${n("min_score")} or closer`;
    }
    case "shared_attributes": {
      const kinds =
        ((rule.params as unknown as Record<string, unknown>).kinds as
          string[] | undefined) ?? [];
      return `a new customer's ${kinds.join(", ")} already used by ${n("min_others")} or more other customers`;
    }
    case "document_verification":
      return "a new customer with no valid verifying document (none, expired or marked fraudulent); checked again daily as documents lapse";
    case "pattern": {
      const id = String(
        (rule.params as unknown as Record<string, unknown>).pattern_id ?? "",
      );
      const name = patternNames?.get(id);
      return `matches of the drawn pattern ${name ? `“${name}”` : "(a pattern saved in the Query builder)"}, up to ${n("max_matches")} nodes, after each load`;
    }
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
  choices: Record<string, boolean> = {},
  kinds: string[] = ["msisdn", "email", "ip"],
  patternId = "",
): TypologyRuleInput {
  const params: Record<string, unknown> = { typology };
  if (typology === "pattern") params.pattern_id = patternId;
  for (const field of PARAMETERS[typology])
    params[field.key] = Number(values[field.key] ?? field.fallback);
  for (const choice of CHOICES[typology] ?? [])
    params[choice.key] = choices[choice.key] ?? choice.fallback;
  if (typology === "shared_attributes") params.kinds = kinds;
  return {
    name: name.trim(),
    params: params as unknown as TypologyRuleInput["params"],
    trigger,
    budget_ms: budgetMs,
  };
}

export interface RulesPanelProps extends AlertsApi {
  level: AccessLevel | null;
}

export function RulesPanel(props: RulesPanelProps) {
  const { apiBaseUrl, bearerToken, investigationId, level } = props;
  const [rules, setRules] = useState<TypologyRule[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [patterns, setPatterns] = useState<SavedPattern[]>([]);
  const author = level === "author";

  // ADR-109 phase D: the account's own saved patterns — what a drawn rule may be deployed from,
  // and how a deployed one is named. Only this account's: the server refuses another's anyway.
  useEffect(() => {
    listPatterns(apiBaseUrl, bearerToken, investigationId)
      .then(setPatterns)
      .catch(() => setPatterns([]));
  }, [apiBaseUrl, bearerToken, investigationId]);
  const patternNames = new Map(patterns.map((p) => [p.pattern_id, p.name]));

  const reload = useCallback(() => {
    listRules({ apiBaseUrl, bearerToken, investigationId })
      .then(setRules)
      .catch((e: Error) => setProblem(e.message));
  }, [apiBaseUrl, bearerToken, investigationId]);
  useEffect(reload, [reload]);

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16)" }}
    >
      {problem && (
        <p role="alert" style={{ color: "var(--error)" }}>
          {problem}
        </p>
      )}
      {said && (
        <p role="status" className="label">
          {said}
        </p>
      )}
      {rules !== null && rules.length === 0 && (
        <p className="label">No rules watch this case yet.</p>
      )}
      <ul
        aria-label="Rules"
        style={{ listStyle: "none", margin: 0, padding: 0 }}
      >
        {(rules ?? []).map((rule) => (
          <li
            key={rule.id}
            style={{
              borderBottom: "1px solid var(--border-subtle)",
              padding: "var(--sp-8) 0",
              display: "flex",
              justifyContent: "space-between",
              gap: "var(--sp-12)",
            }}
          >
            <span
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--sp-4)",
              }}
            >
              <span className="value">
                {rule.name} · {ruleTypologyLabel(rule.params.typology)}
              </span>
              <span className="label">
                {describeParams(rule, patternNames)}
              </span>
              <span className="label">
                {rule.trigger === "pre_commit"
                  ? `Judges each load before it commits (budget ${(rule.budget_ms ?? 5000).toLocaleString("en-GB")} ms; held if it cannot judge)`
                  : "Runs after each load commits"}{" "}
                ·{" "}
                {rule.status === "retired"
                  ? `retired ${rule.retired_at ? when(rule.retired_at) : ""}`
                  : "active"}
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
          patterns={patterns}
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

function DeployForm(
  props: RulesPanelProps & {
    patterns: SavedPattern[];
    onDeployed: (rule: TypologyRule) => void;
  },
) {
  const [name, setName] = useState("");
  const [typology, setTypology] = useState<Typology>("structuring");
  const [values, setValues] = useState<Record<string, string>>({});
  const [trigger, setTrigger] = useState<"pre_commit" | "post_commit">(
    "post_commit",
  );
  const [budget, setBudget] = useState("5000");
  const [choices, setChoices] = useState<Record<string, boolean>>({});
  const [kinds, setKinds] = useState<string[]>(["msisdn", "email", "ip"]);
  const [patternId, setPatternId] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  return (
    <form
      aria-label="Deploy a rule"
      onSubmit={(e) => {
        e.preventDefault();
        setProblem(null);
        deployRule(
          props,
          ruleInput(
            name,
            typology,
            values,
            typology === "pattern" ? "post_commit" : trigger,
            Number(budget),
            choices,
            kinds,
            patternId,
          ),
        )
          .then((rule) => {
            setName("");
            props.onDeployed(rule);
          })
          .catch((err: Error) => setProblem(err.message));
      }}
      style={{
        border: "1px solid var(--border-subtle)",
        padding: "var(--sp-12)",
        display: "grid",
        gap: "var(--sp-8)",
        maxWidth: 520,
      }}
    >
      <h3 className="value" style={{ margin: 0 }}>
        Deploy a rule
      </h3>
      <label className="label" style={FIELD}>
        Name
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          aria-label="Rule name"
        />
      </label>
      <label className="label" style={FIELD}>
        Typology
        <Select
          aria-label="Typology"
          value={typology}
          onChange={(e) => {
            setTypology(e.target.value as Typology);
            setValues({});
            setChoices({});
          }}
        >
          <option value="structuring">Structuring</option>
          <option value="rapid_movement">Rapid movement</option>
          <option value="circular_flow">Circular flow</option>
          <option value="kyc_screening">
            KYC: screening (sanctions, PEPs, adverse media)
          </option>
          <option value="shared_attributes">
            KYC: shared phone, email or address
          </option>
          <option value="document_verification">
            KYC: verifying documents
          </option>
          <option value="pattern">
            Drawn pattern (from the Query builder)
          </option>
        </Select>
      </label>
      {typology === "pattern" && (
        <label className="label" style={FIELD}>
          Saved pattern
          <Select
            aria-label="Saved pattern"
            value={patternId}
            onChange={(e) => setPatternId(e.target.value)}
          >
            <option value="">Choose one you saved…</option>
            {props.patterns.map((p) => (
              <option key={p.pattern_id} value={p.pattern_id}>
                {p.name}
              </option>
            ))}
          </Select>
          {props.patterns.length === 0 && (
            <span className="label">
              {" "}
              Draw and save a pattern in the Query builder first.
            </span>
          )}
        </label>
      )}
      {PARAMETERS[typology].map((field) => (
        <label key={field.key} className="label" style={FIELD}>
          {field.label}
          <Input
            type="number"
            step={field.step}
            aria-label={field.label}
            value={values[field.key] ?? String(field.fallback)}
            onChange={(e) =>
              setValues({ ...values, [field.key]: e.target.value })
            }
          />
        </label>
      ))}
      {(CHOICES[typology] ?? []).map((choice) => (
        <label
          key={choice.key}
          className="label"
          style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}
        >
          <input
            type="checkbox"
            aria-label={choice.label}
            checked={choices[choice.key] ?? choice.fallback}
            onChange={(e) =>
              setChoices({ ...choices, [choice.key]: e.target.checked })
            }
          />
          {choice.label}
        </label>
      ))}
      {typology === "shared_attributes" && (
        <fieldset
          style={{
            border: "none",
            padding: 0,
            display: "flex",
            gap: "var(--sp-12)",
          }}
        >
          <legend className="label">What counts as shared</legend>
          {SHARED_KINDS.map((kind) => (
            <label
              key={kind}
              className="label"
              style={{
                display: "flex",
                gap: "var(--sp-4)",
                alignItems: "center",
              }}
            >
              <input
                type="checkbox"
                aria-label={`Shared ${kind}`}
                checked={kinds.includes(kind)}
                onChange={(e) =>
                  setKinds(
                    e.target.checked
                      ? [...kinds, kind]
                      : kinds.filter((k) => k !== kind),
                  )
                }
              />
              {kind}
            </label>
          ))}
        </fieldset>
      )}
      {typology === "pattern" ? (
        <p className="label" style={{ margin: 0 }}>
          Runs after each load commits: a drawn pattern is matched against the
          stored graph.
        </p>
      ) : (
        <label className="label" style={FIELD}>
          Runs
          <Select
            aria-label="When the rule runs"
            value={trigger}
            onChange={(e) =>
              setTrigger(e.target.value as "pre_commit" | "post_commit")
            }
          >
            <option value="post_commit">After each load commits</option>
            <option value="pre_commit">Before each load commits</option>
          </Select>
        </label>
      )}
      {trigger === "pre_commit" && typology !== "pattern" && (
        <label className="label" style={FIELD}>
          Time budget (ms) — a load it cannot judge in time is held for review
          <Input
            type="number"
            step="100"
            aria-label="Time budget"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
        </label>
      )}
      {problem && (
        <p role="alert" style={{ color: "var(--error)" }}>
          {problem}
        </p>
      )}
      <Button
        type="submit"
        variant="primary"
        disabled={!name.trim() || (typology === "pattern" && !patternId)}
      >
        Deploy
      </Button>
    </form>
  );
}
