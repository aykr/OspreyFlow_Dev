// ADR-133 stage (d) on a rule in the rules list: maker–checker (decision 7) — a whole-deployment
// rule's deployment, change or retirement waits for a second person, who approves or rejects it
// (never the person who proposed it; the server refuses that in words) — the rule's versions with
// who made and who decided each, and a scheduled rule's schedule and runs (decision 1).
import { useState } from "react";
import type { RuleScheduleView, RuleVersion, TypologyRule } from "../../../../packages/schemas/generated";
import { Button, Input } from "../design/primitives";
import { approveRule, rejectRule, ruleRuns, ruleVersions, type AlertsApi } from "./api";
import { when } from "./names";

const ACTION_WORDS: Record<string, string> = { deploy: "deploying it", change: "a change to it", retire: "retiring it" };
const STATUS_WORDS: Record<string, string> = {
  pending: "waiting for a second person",
  approved: "approved",
  rejected: "rejected",
  applied: "applied",
};

/** The words a waiting change shows on the rule. */
export function pendingWords(rule: TypologyRule): string | null {
  if (!rule.pending_action) return null;
  // ADR-106: the proposer's name as the rules list serves it; the id only where none resolved.
  const who = rule.pending_by_name ?? rule.pending_by ?? "someone";
  return `Waiting for a second person's approval: ${ACTION_WORDS[rule.pending_action] ?? rule.pending_action}, proposed by ${who}.`;
}

export function RuleApproval(props: AlertsApi & { rule: TypologyRule; canApprove: boolean; onDone: (said: string) => void }) {
  const { rule, canApprove, onDone } = props;
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const words = pendingWords(rule);
  if (!words) return null;
  return (
    <span style={{ display: "grid", gap: "var(--sp-4)", justifyItems: "start", alignContent: "start" }}>
      <span className="label" role="note">
        {words}
      </span>
      {canApprove && (
        <span style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap", alignItems: "center" }}>
          <Button
            aria-label={`Approve ${rule.name}`}
            onClick={() =>
              void approveRule(props, rule.id)
                .then(() => onDone(`Approved the change to “${rule.name}”.`))
                .catch((e: Error) => setProblem(e.message))
            }
          >
            Approve
          </Button>
          {!rejecting ? (
            <Button aria-label={`Reject ${rule.name}`} onClick={() => setRejecting(true)}>
              Reject
            </Button>
          ) : (
            <>
              <Input aria-label={`Why reject the change to ${rule.name}`} value={reason} onChange={(e) => setReason(e.target.value)} />
              <Button
                aria-label={`Send the rejection of ${rule.name}`}
                disabled={reason.trim() === ""}
                onClick={() =>
                  void rejectRule(props, rule.id, reason.trim())
                    .then(() => onDone(`Rejected the change to “${rule.name}”.`))
                    .catch((e: Error) => setProblem(e.message))
                }
              >
                Send the rejection
              </Button>
            </>
          )}
        </span>
      )}
      {problem && (
        <span role="alert" className="label" style={{ color: "var(--error)" }}>
          {problem}
        </span>
      )}
    </span>
  );
}

/** The rule's versions, oldest first: what each did, who proposed it and who decided it. */
export function RuleHistory(props: AlertsApi & { rule: TypologyRule }) {
  const [versions, setVersions] = useState<RuleVersion[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <span style={{ display: "grid", gap: "var(--sp-4)", justifyItems: "start", alignContent: "start" }}>
      <Button
        aria-label={`Versions of ${props.rule.name}`}
        aria-expanded={versions !== null}
        onClick={() =>
          versions !== null
            ? setVersions(null)
            : void ruleVersions(props, props.rule.id)
                .then(setVersions)
                .catch((e: Error) => setProblem(e.message))
        }
      >
        Versions
      </Button>
      {versions !== null && (
        <ol aria-label={`Versions of ${props.rule.name}`} style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
          {versions.map((v) => (
            <li key={v.version} className="label">
              {`Version ${v.version}: ${v.action === "deploy" ? "deployed" : v.action === "change" ? "changed" : "retired"} by ${v.proposed_by_name ?? v.proposed_by} ${when(v.proposed_at)}`}
              {` · ${STATUS_WORDS[v.status] ?? v.status}`}
              {v.decided_by && v.status !== "applied" ? ` by ${v.decided_by_name ?? v.decided_by}` : ""}
              {v.words ? ` — ${v.words}` : ""}
            </li>
          ))}
        </ol>
      )}
      {problem && (
        <span role="alert" className="label" style={{ color: "var(--error)" }}>
          {problem}
        </span>
      )}
    </span>
  );
}

const OUTCOME_WORDS: Record<string, string> = { ran: "ran", refused: "refused", missed: "missed", failed: "failed" };

/** A scheduled rule's schedule in words, its next run or why it will not run, and its latest runs. */
export function RuleSchedule(props: AlertsApi & { rule: TypologyRule }) {
  const [view, setView] = useState<RuleScheduleView | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <span style={{ display: "grid", gap: "var(--sp-4)", justifyItems: "start", alignContent: "start" }}>
      <Button
        aria-label={`Schedule and runs of ${props.rule.name}`}
        aria-expanded={view !== null}
        onClick={() =>
          view !== null
            ? setView(null)
            : void ruleRuns(props, props.rule.id)
                .then(setView)
                .catch((e: Error) => setProblem(e.message))
        }
      >
        Schedule and runs
      </Button>
      {view !== null && (
        <span aria-label={`The schedule of ${props.rule.name}`} role="group" style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span className="value">{`Runs ${view.schedule}`}</span>
          <span className="label" role="status">
            {view.state === "scheduled" ? `Next run ${view.next_run ? when(view.next_run) : "not yet known"}.` : view.words}
          </span>
          {(view.runs ?? []).length === 0 ? (
            <span className="label">It has not run yet.</span>
          ) : (
            <ul aria-label={`Runs of ${props.rule.name}`} style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {(view.runs ?? []).map((run) => (
                <li key={run.id} className="label">
                  {`${when(run.slot)}: ${OUTCOME_WORDS[run.outcome] ?? run.outcome} — ${run.words}`}
                </li>
              ))}
            </ul>
          )}
        </span>
      )}
      {problem && (
        <span role="alert" className="label" style={{ color: "var(--error)" }}>
          {problem}
        </span>
      )}
    </span>
  );
}
