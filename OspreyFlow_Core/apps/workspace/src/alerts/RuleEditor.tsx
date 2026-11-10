// The rule editor (`06_DECISIONS.md` ADR-146 decision 3 and Amendment 6, L2.11): a rule names one
// dataset, chosen first and never changed; its *When / If / Then* is the sentence builder's, its
// conditions offered from that dataset's live model alone; saved as a draft, which never runs; *Test*
// runs the draft over the dataset's last 30 days as the person testing; *Make live* follows only a
// test of this draft, at once or, where the dataset's policy asks, on a second person's approval.
// Where its alerts go is said before saving.
import { useEffect, useState } from "react";
import type { RuleDatasetOffer, RuleTestResult, SavedPattern, TypologyRule } from "../../../../packages/schemas/generated";
import { Button, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import { listRuleDatasets, makeRuleLive, readRuleBpmn, testRuleDraft, type AlertsApi } from "./api";
import { ShowAsBpmn } from "./ruleStandards/ShowAsBpmn";
import { SentenceBuilder } from "./SentenceBuilder";

export interface RuleEditorProps extends AlertsApi {
  level: AccessLevel | null;
  patterns: SavedPattern[];
  /** Whether the reader may make a rule live (`deploy_rules`); writing and testing a draft is
   * `author_rules`, which the server checks either way. */
  canMakeLive: boolean;
  onChanged: (words: string) => void;
}

/** What a test said, in words: the count is the tester's own (rule 7), over what they may see. */
export function testWords(result: RuleTestResult): string {
  const n = result.would_raise;
  return n === 0
    ? `It would have raised no alerts in the last ${result.days} days.`
    : `It would have raised ${n.toLocaleString("en-GB")} alert${n === 1 ? "" : "s"} in the last ${result.days} days.`;
}

export function RuleEditor(props: RuleEditorProps) {
  const api: AlertsApi = { apiBaseUrl: props.apiBaseUrl, bearerToken: props.bearerToken, investigationId: props.investigationId };
  const [offers, setOffers] = useState<RuleDatasetOffer[] | null>(null);
  const [choice, setChoice] = useState("");
  const [dataset, setDataset] = useState<RuleDatasetOffer | null>(null);
  const [saved, setSaved] = useState<TypologyRule | null>(null);
  const [tested, setTested] = useState<RuleTestResult | null>(null);
  // ADR-146 decision 3: *Show as BPMN* draws the files saved beside the draft, read-only.
  const [bpmn, setBpmn] = useState<string | null>(null);
  useEffect(() => {
    setBpmn(null);
    if (!saved) return;
    readRuleBpmn(api, saved.id)
      .then(setBpmn)
      .catch(() => setBpmn(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saved]);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const author = props.level === "author";

  useEffect(() => {
    if (!author) return;
    listRuleDatasets(api)
      .then((found) => setOffers(Array.isArray(found) ? found : []))
      .catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.apiBaseUrl, props.bearerToken, props.investigationId, author]);

  if (!author) {
    return (
      <p className="label" style={{ margin: 0 }}>
        A case Author writes the case&apos;s rules.
      </p>
    );
  }

  const act = (what: () => Promise<void>) => {
    setBusy(true);
    setProblem(null);
    what()
      .catch((e: Error) => setProblem(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <section aria-label="Write a rule on a dataset" style={{ display: "grid", gap: "var(--sp-12)", maxWidth: 880 }}>
      <h3 className="value" style={{ margin: 0 }}>
        Write a rule on a dataset
      </h3>
      {problem && (
        <p role="alert" style={{ color: "var(--error)", margin: 0 }}>
          {problem}
        </p>
      )}
      {!dataset ? (
        offers === null ? (
          <p className="label">Reading the datasets…</p>
        ) : offers.length === 0 ? (
          <p className="label">This case reads no dataset a rule may watch.</p>
        ) : (
          <form
            aria-label="Choose the dataset"
            onSubmit={(e) => {
              e.preventDefault();
              setDataset(offers.find((o) => o.id === choice) ?? null);
            }}
            style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end", flexWrap: "wrap" }}
          >
            <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
              The dataset this rule watches
              <Select aria-label="The dataset this rule watches" value={choice} onChange={(e) => setChoice(e.target.value)}>
                <option value="">Choose one…</option>
                {offers.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.kind === "composite" ? `${o.name} (composite)` : o.name}
                  </option>
                ))}
              </Select>
            </label>
            <Button type="submit" disabled={!choice}>
              Choose the dataset
            </Button>
            <span className="label">It is chosen once and never changed.</span>
          </form>
        )
      ) : (
        <>
          <p className="label" style={{ margin: 0 }}>
            Watching <span className="value">{dataset.name}</span>. Its conditions are offered from this dataset&apos;s own model.
          </p>
          <SentenceBuilder
            apiBaseUrl={props.apiBaseUrl}
            bearerToken={props.bearerToken}
            investigationId={props.investigationId}
            level={props.level}
            isAdministrator={false}
            patterns={props.patterns}
            onDeployed={() => undefined}
            editor={{
              dataset,
              ruleId: saved?.id,
              onSaved: (rule) => {
                setSaved(rule);
                setTested(null);
                props.onChanged(`Saved the draft of “${rule.name}”. Test it before you make it live.`);
              },
            }}
          />
          {saved && (
            <section aria-label="The draft" style={{ display: "grid", gap: "var(--sp-8)" }}>
              <p className="label" style={{ margin: 0 }}>
                “{saved.name}” is a draft: it does not run until it is made live.
              </p>
              <span style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
                <Button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    act(async () => {
                      setTested(await testRuleDraft(api, saved.id));
                    })
                  }
                >
                  Test on the last 30 days
                </Button>
                {props.canMakeLive && (
                  <Button
                    type="button"
                    disabled={busy || tested === null}
                    onClick={() =>
                      act(async () => {
                        const made = await makeRuleLive(api, saved.id);
                        setSaved(made);
                        props.onChanged(
                          made.status === "active" && !made.pending_action
                            ? `“${made.name}” is live.`
                            : `“${made.name}” waits for a second person's approval before it goes live.`,
                        );
                      })
                    }
                  >
                    Make live
                  </Button>
                )}
              </span>
              {bpmn && <ShowAsBpmn bpmnXml={bpmn} />}
              {tested && (
                <p className="value" role="status" aria-label="Test result" style={{ margin: 0 }}>
                  {testWords(tested)} Counted as you, over what you may see. Nothing was raised.
                </p>
              )}
              {tested === null && <p className="label" style={{ margin: 0 }}>A rule goes live only once this draft is tested.</p>}
              {dataset.second_person && (
                <p className="label" style={{ margin: 0 }}>
                  {dataset.name} asks for a second person: making it live waits for another Author to approve it.
                </p>
              )}
            </section>
          )}
        </>
      )}
    </section>
  );
}
