// The rule editor (`06_DECISIONS.md` ADR-146 decision 3 and Amendment 6, L2.11): a rule names one
// dataset, chosen first and never changed; its *When / If / Then* is the sentence builder's, its
// conditions offered from that dataset's live model alone; saved as a draft, which never runs; *Test*
// runs the draft over the dataset's last 30 days as the person testing; *Make live* follows only a
// test of this draft, at once or, where the dataset's policy asks, on a second person's approval.
// Where its alerts go is said before saving.
import { useEffect, useState } from "react";
import type { RuleDatasetOffer, RuleSentence, RuleTestResult, SavedPattern, TypologyRule } from "../../../../packages/schemas/generated";
import { Button, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import { listRuleDatasets, makeRuleLive, readRuleBpmn, readRuleDraft, testRuleDraft, type AlertsApi } from "./api";
import { ShowAsBpmn } from "./ruleStandards/ShowAsBpmn";
import { SentenceBuilder } from "./SentenceBuilder";

export interface RuleEditorProps extends AlertsApi {
  level: AccessLevel | null;
  patterns: SavedPattern[];
  /** Whether the reader may make a rule live (`deploy_rules`); writing and testing a draft is
   * `author_rules`, which the server checks either way. */
  canMakeLive: boolean;
  onChanged: (words: string) => void;
  /** ADR-146 decision 5: a rule's row opens its editor, on its own dataset, at its draft if it has
   * one, else as it runs. */
  opening?: TypologyRule | null;
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
  const [saved, setSaved] = useState<TypologyRule | null>(props.opening ?? null);
  const [initial, setInitial] = useState<{ name: string; sentence: RuleSentence } | undefined>(undefined);
  const [ready, setReady] = useState(!props.opening);
  // An opened draft tested before: when (its count is its tester's alone, rule 7).
  const [testedAt, setTestedAt] = useState<string | null>(null);
  // Whether there is a draft to test and make live: a live rule opened without one has none.
  const [hasDraft, setHasDraft] = useState(false);
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
      .then((found) => {
        const offered = Array.isArray(found) ? found : [];
        setOffers(offered);
        const opening = props.opening;
        if (!opening) return;
        // The rule's own dataset, fixed: one the case no longer reads is said, not guessed.
        const own = offered.find((o) => o.id === opening.dataset_id) ?? null;
        if (!own) {
          setProblem("This rule's dataset is not one this case reads now, so it cannot be changed here.");
          return;
        }
        setDataset(own);
        return readRuleDraft(api, opening.id).then((draft) => {
          const from = (draft?.params ?? opening.params) as unknown as { sentence: RuleSentence };
          setInitial({ name: draft?.name ?? opening.name, sentence: from.sentence });
          setTestedAt(draft?.tested_at ?? null);
          setHasDraft(draft !== null || opening.status === "draft");
          setReady(true);
        });
      })
      .catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.apiBaseUrl, props.bearerToken, props.investigationId, author, props.opening?.id]);

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
          {ready && <SentenceBuilder
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
              initial,
              onSaved: (rule) => {
                setSaved(rule);
                setTested(null);
                setTestedAt(null);
                setHasDraft(true);
                props.onChanged(`Saved the draft of “${rule.name}”. Test it before you make it live.`);
              },
            }}
          />}
          {saved && !hasDraft && (
            <p className="label" style={{ margin: 0 }}>
              “{saved.name}” is live as it stands. Change it and save a draft to test the change before it goes live.
            </p>
          )}
          {saved && hasDraft && (
            <section aria-label="The draft" style={{ display: "grid", gap: "var(--sp-8)" }}>
              <p className="label" style={{ margin: 0 }}>
                {saved.status === "active"
                  ? `“${saved.name}” runs as it stands; this draft of it goes live only once tested and made live.`
                  : `“${saved.name}” is a draft: it does not run until it is made live.`}
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
                    disabled={busy || (tested === null && testedAt === null)}
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
              {tested === null && testedAt !== null && (
                <p className="label" style={{ margin: 0 }}>
                  This draft was tested on {new Date(testedAt).toLocaleDateString("en-GB")}.
                </p>
              )}
              {tested === null && testedAt === null && (
                <p className="label" style={{ margin: 0 }}>A rule goes live only once this draft is tested.</p>
              )}
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
