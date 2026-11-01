// The case's typology rules (`06_DECISIONS.md` ADR-109 phase A, rulings 1 and 4): what watches this
// case's loads, where each runs, and — for an Author — deploying one and retiring one. A rule is a
// typology with its parameters, a closed list per typology (rule 8: no expression language).
// ADR-133 stage (a): the seven typologies are offered as templates above the form; using one fills it.
// ADR-133 stage (c): the four new AML templates — a jurisdiction list as two-letter codes the Author
// enters (data in the rule, never code), cash types, and a measure for a rise in velocity.
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  RuleSentence,
  SavedPattern,
  TypologyRule,
  TypologyRuleInput,
} from "../../../../packages/schemas/generated";
import { Button, Input, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import { listPatterns } from "../patterns/api";
import { deployRule, listRules, retireRule, type AlertsApi } from "./api";
import { money, ruleTypologyLabel, when } from "./names";
import { SentenceBuilder } from "./SentenceBuilder";
import { sentenceSummary } from "./sentence";
import { TEMPLATES, type RuleTemplate } from "./templates";

type Typology =
  | "structuring"
  | "rapid_movement"
  | "circular_flow"
  | "kyc_screening"
  | "shared_attributes"
  | "document_verification"
  | "pattern"
  | "sentence"
  | "high_risk_jurisdiction"
  | "large_cash"
  | "dormant_reactivated"
  | "velocity_rise";

/** ADR-133 stage (c): these compare an account with its own stored past, so run after commit only. */
export const AFTER_COMMIT_ONLY: ReadonlySet<Typology> = new Set(["pattern", "dormant_reactivated", "velocity_rise"]);

/** The cash movements `large_cash` may watch (the ontology's `transaction_type`). */
export const CASH_TYPES = [
  { key: "CASH_IN", label: "Cash paid in (CASH_IN)" },
  { key: "CASH_OUT", label: "Cash drawn out (CASH_OUT)" },
] as const;

/** Two-letter codes as typed, separated by commas or spaces, upper-cased; the server checks each. */
export function jurisdictionCodes(typed: string): string[] {
  return [...new Set(typed.split(/[\s,;]+/).map((c) => c.trim().toUpperCase()).filter(Boolean))];
}

/** What a stage (c) template adds to its numbers. */
export interface AmlExtras {
  jurisdictions?: string[];
  cashTypes?: string[];
  measure?: "count" | "amount";
}

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
  // ADR-133 stage (c): the new AML templates (the jurisdiction list, cash types and the measure are
  // their own fields, below the numbers).
  high_risk_jurisdiction: [],
  large_cash: [{ key: "threshold", label: "Cash at or over", step: "1", fallback: 10000 }],
  dormant_reactivated: [{ key: "dormant_days", label: "Dormant for at least (days)", step: "1", fallback: 180 }],
  velocity_rise: [
    { key: "recent_days", label: "Over the last (days)", step: "1", fallback: 7 },
    { key: "baseline_days", label: "Against its own rate over the days before (days)", step: "1", fallback: 90 },
    { key: "factor", label: "At least (times its own rate)", step: "0.5", fallback: 3 },
    { key: "min_recent", label: "With at least (movements in the last days)", step: "1", fallback: 5 },
  ],
  // ADR-133 stage (b): written in the sentence builder, never in this form.
  sentence: [],
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
    case "high_risk_jurisdiction": {
      const codes = ((rule.params as unknown as Record<string, unknown>).jurisdictions as string[] | undefined) ?? [];
      return `a payment to or from an account held in ${codes.join(", ")} (its IBAN country code)`;
    }
    case "large_cash": {
      const kinds = ((rule.params as unknown as Record<string, unknown>).cash_types as string[] | undefined) ?? [];
      const words = kinds.map((k) => (k === "CASH_IN" ? "paid in" : "drawn out")).join(" or ");
      return `cash ${words} of ${money(n("threshold"))} or more in one movement`;
    }
    case "dormant_reactivated":
      return `an account moving money again after ${n("dormant_days")} days or more without a movement; runs after each load commits`;
    case "velocity_rise": {
      const measure = (rule.params as unknown as Record<string, unknown>).measure === "amount" ? "amount moved" : "movements";
      return `an account's ${measure} over the last ${n("recent_days")} day(s) at ${n("factor")} times or more its own daily rate over the ${n("baseline_days")} days before, with ${n("min_recent")} or more movements; runs after each load commits`;
    }
    case "sentence": {
      const sentence = (rule.params as unknown as { sentence: RuleSentence }).sentence;
      return sentenceSummary(sentence);
    }
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
  extras: AmlExtras = {},
): TypologyRuleInput {
  const params: Record<string, unknown> = { typology };
  if (typology === "pattern") params.pattern_id = patternId;
  if (typology === "high_risk_jurisdiction") params.jurisdictions = extras.jurisdictions ?? [];
  for (const field of PARAMETERS[typology])
    params[field.key] = Number(values[field.key] ?? field.fallback);
  for (const choice of CHOICES[typology] ?? [])
    params[choice.key] = choices[choice.key] ?? choice.fallback;
  if (typology === "shared_attributes") params.kinds = kinds;
  if (typology === "large_cash") params.cash_types = extras.cashTypes ?? CASH_TYPES.map((c) => c.key);
  if (typology === "velocity_rise") params.measure = extras.measure ?? "count";
  return {
    name: name.trim(),
    params: params as unknown as TypologyRuleInput["params"],
    trigger: AFTER_COMMIT_ONLY.has(typology) ? "post_commit" : trigger,
    budget_ms: budgetMs,
  };
}

export interface RulesPanelProps extends AlertsApi {
  level: AccessLevel | null;
  /** ADR-133 decision 1: a rule for the whole deployment is an administrator's. */
  isAdministrator?: boolean;
}

export function RulesPanel(props: RulesPanelProps) {
  const { apiBaseUrl, bearerToken, investigationId, level } = props;
  const [rules, setRules] = useState<TypologyRule[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [patterns, setPatterns] = useState<SavedPattern[]>([]);
  const [preset, setPreset] = useState<{ template: RuleTemplate; nonce: number } | null>(null);
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
      <SentenceBuilder
        {...props}
        isAdministrator={props.isAdministrator ?? false}
        patterns={patterns}
        onDeployed={(rule) => {
          setSaid(`Deployed “${rule.name}”.`);
          reload();
        }}
      />
      <Templates
        canUse={author}
        onUse={(template) => setPreset({ template, nonce: (preset?.nonce ?? 0) + 1 })}
      />
      {author ? (
        <DeployForm
          key={preset?.nonce ?? 0}
          {...props}
          preset={preset?.template ?? null}
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

const SEVERITY_WORDS: Record<string, string> = { high: "high", medium: "medium", low: "low" };

/** ADR-133 decision 2, stage (a): the typologies as named templates, grouped by the work they serve.
 * Every reader sees them; an Author uses one to fill the form below. */
function Templates(props: { canUse: boolean; onUse: (template: RuleTemplate) => void }) {
  return (
    <section aria-label="Rule templates" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="value" style={{ margin: 0 }}>
        Templates
      </h3>
      <p className="label" style={{ margin: 0 }}>
        Start a rule from one of these: it fills the form with the template&apos;s defaults, which you can change before deploying.
      </p>
      <ul aria-label="Templates" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
        {TEMPLATES.map((template) => (
          <li
            key={template.typology}
            style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-12)", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", padding: "var(--sp-4) 0" }}
          >
            <span style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
              <span className="value">
                {template.name} · <span className="label">{template.group}</span>
              </span>
              <span className="label">{template.description}</span>
              <span className="label">{`Raises ${SEVERITY_WORDS[template.severity]}-severity alerts.`}</span>
            </span>
            {props.canUse && (
              <Button aria-label={`Use the template: ${template.name}`} onClick={() => props.onUse(template)}>
                Use
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function DeployForm(
  props: RulesPanelProps & {
    patterns: SavedPattern[];
    preset: RuleTemplate | null;
    onDeployed: (rule: TypologyRule) => void;
  },
) {
  const [name, setName] = useState(props.preset?.name ?? "");
  const [typology, setTypology] = useState<Typology>(props.preset?.typology ?? "structuring");
  const nameRef = useRef<HTMLInputElement>(null);
  // A template just used: the form is filled, and the keyboard is put on its first field.
  useEffect(() => {
    if (props.preset) nameRef.current?.focus();
  }, [props.preset]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [trigger, setTrigger] = useState<"pre_commit" | "post_commit">(
    "post_commit",
  );
  const [budget, setBudget] = useState("5000");
  const [choices, setChoices] = useState<Record<string, boolean>>({});
  const [kinds, setKinds] = useState<string[]>(["msisdn", "email", "ip"]);
  const [patternId, setPatternId] = useState("");
  const [codes, setCodes] = useState("");
  const [cashTypes, setCashTypes] = useState<string[]>(CASH_TYPES.map((c) => c.key));
  const [measure, setMeasure] = useState<"count" | "amount">("count");
  const [problem, setProblem] = useState<string | null>(null);
  const afterCommitOnly = AFTER_COMMIT_ONLY.has(typology);

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
            trigger,
            Number(budget),
            choices,
            kinds,
            patternId,
            { jurisdictions: jurisdictionCodes(codes), cashTypes, measure },
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
          ref={nameRef}
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
          <option value="high_risk_jurisdiction">AML: high-risk jurisdiction</option>
          <option value="large_cash">AML: large cash</option>
          <option value="dormant_reactivated">AML: dormant account reactivated</option>
          <option value="velocity_rise">AML: sudden rise in velocity</option>
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
      {typology === "high_risk_jurisdiction" && (
        <label className="label" style={FIELD}>
          High-risk jurisdictions: two-letter country codes, separated by commas (an account&apos;s is its IBAN&apos;s first two letters)
          <Input
            aria-label="High-risk jurisdictions"
            placeholder="for example XA, XB"
            value={codes}
            onChange={(e) => setCodes(e.target.value)}
          />
        </label>
      )}
      {typology === "large_cash" && (
        <fieldset style={{ border: "none", padding: 0, display: "flex", gap: "var(--sp-12)" }}>
          <legend className="label">Which cash movements</legend>
          {CASH_TYPES.map((cash) => (
            <label key={cash.key} className="label" style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
              <input
                type="checkbox"
                aria-label={cash.label}
                checked={cashTypes.includes(cash.key)}
                onChange={(e) =>
                  setCashTypes(e.target.checked ? [...cashTypes, cash.key] : cashTypes.filter((k) => k !== cash.key))
                }
              />
              {cash.label}
            </label>
          ))}
        </fieldset>
      )}
      {typology === "velocity_rise" && (
        <label className="label" style={FIELD}>
          Measured by
          <Select aria-label="Measured by" value={measure} onChange={(e) => setMeasure(e.target.value as "count" | "amount")}>
            <option value="count">The number of movements</option>
            <option value="amount">The amount moved</option>
          </Select>
        </label>
      )}
      {typology === "pattern" ? (
        <p className="label" style={{ margin: 0 }}>
          Runs after each load commits: a drawn pattern is matched against the
          stored graph.
        </p>
      ) : afterCommitOnly ? (
        <p className="label" style={{ margin: 0 }}>
          Runs after each load commits: an account is compared with its own stored past.
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
      {trigger === "pre_commit" && !afterCommitOnly && (
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
        disabled={
          !name.trim() ||
          (typology === "pattern" && !patternId) ||
          (typology === "high_risk_jurisdiction" && jurisdictionCodes(codes).length === 0) ||
          (typology === "large_cash" && cashTypes.length === 0)
        }
      >
        Deploy
      </Button>
    </form>
  );
}
