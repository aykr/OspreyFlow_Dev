// The Monitoring place's Connection strength tab (ADR-139 decision 3): the influencers in force in
// this case; the case's own override, which its Author changes (no second person: it changes only
// this case, and is audited); and, for whoever holds `manage_strength_influencers`, the
// installation-wide set — its versions, the one waiting for a second person (approve, or send it back
// with words; never one's own), and a new version to propose. Every blank is a closed choice from the
// ontology, or a number, or a value of the record's property: never an expression (rule 8).
//
// It lives in Monitoring, beside the rules: influencers change what the rules on strength judge, and
// both are for the analysts who hold the right, not only the administrator.
//
// ADR-139 Amendment 2: an influencer may be triggered by a dataset as well as by a record, and may
// change a pair linked through a shared value; the case's Author may switch the case's composition
// (standard, or the client's parity sum) for a demonstration; an installation version chooses its
// composition and rarity measure, by the same maker–checker.
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  ActiveInfluencer,
  CaseInfluencers,
  EdgeTypeDef,
  EntityTypeDef,
  InfluencerSetHistory,
  InfluencerSetVersion,
  StrengthInfluencer,
} from "../../../../packages/schemas/generated";
import { linkTypeName } from "../canvas/linkLabel";
import { Button, Checkbox, Input, Select } from "../design/primitives";
import {
  approveInfluencers,
  fetchCaseInfluencers,
  fetchInfluencerHistory,
  proposeInfluencers,
  saveCaseInfluencers,
  sendBackInfluencers,
} from "./api";
import {
  andList,
  COMPOSITION_LABEL,
  compositionWords,
  influencerWords,
  layerWords,
  MEASURE_LABEL,
  SHARED_VALUE,
  SHARED_VALUE_LABEL,
  type Composition,
  type LinkName,
  type RarityMeasure,
} from "./words";

export interface StrengthPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  accountId: string | null;
  /** ADR-139's `manage_strength_influencers`: the installation-wide set is offered. */
  canManage: boolean;
  entityTypes: readonly EntityTypeDef[];
  edgeTypes: readonly EdgeTypeDef[];
  /** Told when what is in force in this case may have changed, so the legend is read again. */
  onChanged?: () => void;
}

const CHANGES: { value: StrengthInfluencer["change"]; label: string }[] = [
  { value: "add", label: "Add a boost before the curve" },
  { value: "multiply", label: "Multiply the score before the curve" },
  { value: "floor", label: "At least this strong" },
  { value: "exclude", label: "No stronger than its stored weight" },
];

const SIZE_DEFAULT: Record<string, number> = { add: 0.1348, multiply: 1.5, floor: 0.5, exclude: 0 };

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

function slug(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64) || "influencer"
  );
}

/** One influencer being written: the closed choices the ontology offers, and a size. */
function InfluencerForm({
  idPrefix,
  entityTypes,
  edgeTypes,
  onAdd,
}: {
  idPrefix: string;
  entityTypes: readonly EntityTypeDef[];
  edgeTypes: readonly EdgeTypeDef[];
  onAdd: (influencer: StrengthInfluencer) => void;
}) {
  const [label, setLabel] = useState("");
  const [linkTypes, setLinkTypes] = useState<string[]>([]);
  const [when, setWhen] = useState<"always" | "record" | "dataset">("always");
  const triggered = when === "record";
  const [dataset, setDataset] = useState("");
  const [entityType, setEntityType] = useState(entityTypes[0]?.name ?? "");
  const declared = entityTypes.find((e) => e.name === entityType);
  const properties = declared?.properties ?? [];
  const [property, setProperty] = useState("");
  const chosenProperty = properties.find((p) => p.name === property);
  const [values, setValues] = useState<string[]>([]);
  const [typedValue, setTypedValue] = useState("");
  const [change, setChange] = useState<StrengthInfluencer["change"]>("add");
  const [size, setSize] = useState(SIZE_DEFAULT.add ?? 0.1348);
  const [problem, setProblem] = useState<string | null>(null);

  const add = () => {
    const recordValues = (chosenProperty?.values?.length ? values : [typedValue.trim()]).filter(Boolean);
    const datasets = [dataset.trim()].filter(Boolean);
    const trigger = triggered
      ? { entity_type: entityType, property, values: recordValues }
      : when === "dataset"
        ? { kind: "dataset", datasets }
        : null;
    if (!label.trim()) return setProblem("Give it a label: the legend shows it.");
    if (linkTypes.length === 0) return setProblem("Choose at least one link type it changes.");
    if (triggered && (!property || recordValues.length === 0)) {
      return setProblem("Choose the record's property and at least one value that triggers it.");
    }
    if (when === "dataset" && datasets.length === 0) {
      return setProblem("Name the dataset whose links it changes.");
    }
    if (linkTypes.includes(SHARED_VALUE) && (triggered || change !== "add")) {
      return setProblem("A pair linked through a shared value takes an added boost, triggered by a dataset or always.");
    }
    setProblem(null);
    onAdd({
      id: slug(label),
      label: label.trim(),
      link_types: linkTypes,
      trigger: trigger as StrengthInfluencer["trigger"],
      change,
      size: change === "exclude" ? 0 : size,
      enabled: true,
    } as StrengthInfluencer);
    setLabel("");
    setLinkTypes([]);
    setValues([]);
    setTypedValue("");
    setDataset("");
  };

  return (
    <fieldset className="strength-panel__form">
      <legend>Add an influencer</legend>
      <label className="strength-panel__field">
        <span>Label in the legend</span>
        <Input aria-label="Label in the legend" value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      <fieldset className="strength-panel__choices">
        <legend>Link types it changes</legend>
        {edgeTypes
          .filter((t) => !t.system)
          .map((t) => (
            <label key={t.name} className="strength-panel__choice">
              <Checkbox
                id={`${idPrefix}-link-${t.name}`}
                checked={linkTypes.includes(t.name)}
                onChange={() =>
                  setLinkTypes((held) => (held.includes(t.name) ? held.filter((x) => x !== t.name) : [...held, t.name]))
                }
              />
              {linkTypeName(t.name, edgeTypes)}
            </label>
          ))}
        <label className="strength-panel__choice">
          <Checkbox
            id={`${idPrefix}-link-${SHARED_VALUE}`}
            checked={linkTypes.includes(SHARED_VALUE)}
            onChange={() =>
              setLinkTypes((held) =>
                held.includes(SHARED_VALUE) ? held.filter((x) => x !== SHARED_VALUE) : [...held, SHARED_VALUE],
              )
            }
          />
          {SHARED_VALUE_LABEL}
        </label>
      </fieldset>
      <label className="strength-panel__field">
        <span>When it applies</span>
        <Select aria-label="When it applies" value={when} onChange={(e) => setWhen(e.target.value as typeof when)}>
          <option value="always">Always: these are direct links</option>
          <option value="record">When a record evidences the link</option>
          <option value="dataset">When the link is in a dataset</option>
        </Select>
      </label>
      {when === "dataset" && (
        <label className="strength-panel__field">
          <span>Dataset it is in</span>
          <Input aria-label="Dataset it is in" value={dataset} onChange={(e) => setDataset(e.target.value)} />
        </label>
      )}
      {triggered && (
        <>
          <label className="strength-panel__field">
            <span>Kind of record</span>
            <Select
              aria-label="Kind of record"
              value={entityType}
              onChange={(e) => {
                setEntityType(e.target.value);
                setProperty("");
                setValues([]);
              }}
            >
              {entityTypes.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </Select>
          </label>
          <label className="strength-panel__field">
            <span>Its property</span>
            <Select aria-label="Its property" value={property} onChange={(e) => setProperty(e.target.value)}>
              <option value="">Choose a property</option>
              {properties.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </label>
          {chosenProperty?.values?.length ? (
            <fieldset className="strength-panel__choices">
              <legend>Values that trigger it</legend>
              {chosenProperty.values.map((v) => (
                <label key={v} className="strength-panel__choice">
                  <Checkbox
                    checked={values.includes(v)}
                    onChange={() => setValues((held) => (held.includes(v) ? held.filter((x) => x !== v) : [...held, v]))}
                  />
                  {v.replace(/_/g, " ")}
                </label>
              ))}
            </fieldset>
          ) : (
            property && (
              <label className="strength-panel__field">
                <span>Value that triggers it</span>
                <Input aria-label="Value that triggers it" value={typedValue} onChange={(e) => setTypedValue(e.target.value)} />
              </label>
            )
          )}
        </>
      )}
      <label className="strength-panel__field">
        <span>Change</span>
        <Select
          aria-label="Change"
          value={change}
          onChange={(e) => {
            const next = e.target.value as StrengthInfluencer["change"];
            setChange(next);
            setSize(SIZE_DEFAULT[next ?? "add"] ?? 0);
          }}
        >
          {CHANGES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </Select>
      </label>
      {change !== "exclude" && (
        <label className="strength-panel__field">
          <span>Size</span>
          <Input
            aria-label="Size"
            type="number"
            step="0.01"
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
          />
        </label>
      )}
      {problem && <p className="strength-panel__problem">{problem}</p>}
      <Button onClick={add}>Add this influencer</Button>
    </fieldset>
  );
}

function InfluencerList({
  influencers,
  linkName,
  onRemove,
}: {
  influencers: readonly StrengthInfluencer[];
  linkName: LinkName;
  onRemove?: (id: string) => void;
}) {
  if (influencers.length === 0) return <p className="strength-panel__muted">None.</p>;
  return (
    <ul className="strength-panel__list">
      {influencers.map((i) => (
        <li key={i.id}>
          <span>
            <strong>{i.label}</strong> {influencerWords(i, linkName)}
            {i.note ? ` (${i.note})` : ""}
          </span>
          {onRemove && (
            <Button aria-label={`Remove ${i.label}`} onClick={() => onRemove(i.id)}>
              Remove
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

function versionWords(version: InfluencerSetVersion): string {
  const by = version.proposed_by_name ?? "someone";
  const decided = version.decided_by_name ?? "someone";
  const on = DAY.format(new Date(version.proposed_at));
  if (version.status === "pending") return `Proposed by ${by} on ${on}; waiting for a second person.`;
  if (version.status === "sent_back") {
    return `Proposed by ${by} on ${on}; sent back by ${decided}${version.decision_words ? `: “${version.decision_words}”` : ""}.`;
  }
  return `Proposed by ${by} on ${on}; approved by ${decided}${version.in_force ? "; in force" : ""}.`;
}

export function StrengthPanel(props: StrengthPanelProps) {
  const { apiBaseUrl, bearerToken, investigationId, accountId, canManage, entityTypes, edgeTypes } = props;
  const linkName: LinkName = useCallback(
    (type: string) => linkTypeName(type, edgeTypes),
    [edgeTypes],
  );
  const [found, setFound] = useState<CaseInfluencers | null>(null);
  const [history, setHistory] = useState<InfluencerSetHistory | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [read, setRead] = useState(0);
  // The case's own override being written.
  const [added, setAdded] = useState<StrengthInfluencer[]>([]);
  const [switchedOff, setSwitchedOff] = useState<string[]>([]);
  // ADR-139 Amendment 2: the case's own composition ("" = as the installation chooses).
  const [caseComposition, setCaseComposition] = useState<Composition | "">("");
  const [proposalComposition, setProposalComposition] = useState<Composition | "">("");
  const [proposalMeasure, setProposalMeasure] = useState<RarityMeasure | "">("");
  // A new installation-wide version being written.
  const [proposal, setProposal] = useState<StrengthInfluencer[] | null>(null);
  const [proposalWords, setProposalWords] = useState("");
  const [sendBackWords, setSendBackWords] = useState("");

  useEffect(() => {
    let cancelled = false;
    setProblem(null);
    void fetchCaseInfluencers(apiBaseUrl, bearerToken, investigationId)
      .then((got) => {
        if (cancelled) return;
        setFound(got);
        setAdded([...(got.override?.added ?? [])]);
        setSwitchedOff([...(got.override?.switched_off ?? [])]);
        setCaseComposition((got.override?.composition ?? "") as Composition | "");
      })
      .catch((err: unknown) => !cancelled && setProblem(err instanceof Error ? err.message : String(err)));
    if (canManage) {
      void fetchInfluencerHistory(apiBaseUrl, bearerToken)
        .then((got) => !cancelled && setHistory(got))
        .catch((err: unknown) => !cancelled && setProblem(err instanceof Error ? err.message : String(err)));
    }
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, canManage, read]);

  const done = (words: string) => {
    setSaid(words);
    setRead((n) => n + 1);
    props.onChanged?.();
  };
  const failed = (err: unknown) => setProblem(err instanceof Error ? err.message : String(err));

  // What a case may switch off: the influencers in force that are not its own.
  const switchable = useMemo(() => {
    const inForce = (found?.legend.influencers ?? []).filter((a) => a.layer !== "case").map((a) => a.influencer);
    const off = (found?.legend.switched_off ?? []).map((id) => ({ id, label: id }) as StrengthInfluencer);
    return [...inForce, ...off.filter((o) => !inForce.some((i) => i.id === o.id))];
  }, [found]);

  const inForceVersion = history?.versions.find((v) => v.in_force) ?? null;
  const waiting = history?.versions.find((v) => v.status === "pending") ?? null;
  const ownWaiting = waiting !== null && waiting.proposed_by === accountId;

  return (
    <div className="strength-panel">
      <section aria-labelledby="strength-in-force">
        <h3 id="strength-in-force" className="strength-panel__heading">
          In force in this case
        </h3>
        {problem && <p className="strength-panel__problem">{problem}</p>}
        {said && (
          <p className="strength-panel__said" role="status">
            {said}
          </p>
        )}
        {found ? (
          <>
            <ul className="strength-panel__list" aria-label="Influencers in force">
              {found.legend.influencers.map((a: ActiveInfluencer) => (
                <li key={a.influencer.id}>
                  <span>
                    <strong>{a.influencer.label}</strong> {influencerWords(a.influencer, linkName)} ({layerWords(a)})
                  </span>
                </li>
              ))}
            </ul>
            <p className="strength-panel__muted">
              Direct links: {found.legend.direct_link_types.length ? andList(found.legend.direct_link_types.map(linkName)) : "none"}.{" "}
              {found.legend.rarity_note}
            </p>
            <p className="strength-panel__muted" aria-label="Composition in force">
              {compositionWords(found.legend)}
            </p>
          </>
        ) : (
          !problem && <p className="strength-panel__muted">Reading the influencers in force…</p>
        )}
      </section>

      {found?.can_override && (
        <section aria-labelledby="strength-case-own">
          <h3 id="strength-case-own" className="strength-panel__heading">
            This case's own influencers
          </h3>
          <p className="strength-panel__muted">
            As this case's Author you may add influencers for this case, or switch off installation-wide ones here.
            No second person is needed: it changes only this case, and it is recorded in the audit.
          </p>
          <InfluencerList influencers={added} linkName={linkName} onRemove={(id) => setAdded((held) => held.filter((i) => i.id !== id))} />
          {switchable.length > 0 && (
            <fieldset className="strength-panel__choices">
              <legend>Switched off in this case</legend>
              {switchable.map((i) => (
                <label key={i.id} className="strength-panel__choice">
                  <Checkbox
                    checked={switchedOff.includes(i.id)}
                    onChange={() =>
                      setSwitchedOff((held) => (held.includes(i.id) ? held.filter((x) => x !== i.id) : [...held, i.id]))
                    }
                  />
                  {i.label}
                </label>
              ))}
            </fieldset>
          )}
          <label className="strength-panel__field">
            <span>How strength is worked out in this case</span>
            <Select
              aria-label="How strength is worked out in this case"
              value={caseComposition}
              onChange={(e) => setCaseComposition(e.target.value as Composition | "")}
            >
              <option value="">As the installation chooses</option>
              <option value="standard">{COMPOSITION_LABEL.standard}: the stored weight with the influencers</option>
              <option value="client_parity">
                {COMPOSITION_LABEL.client_parity}: rarity plus the adds, as the client works it out
              </option>
            </Select>
          </label>
          <InfluencerForm
            idPrefix="case"
            entityTypes={entityTypes}
            edgeTypes={edgeTypes}
            onAdd={(i) => setAdded((held) => [...held.filter((h) => h.id !== i.id), i])}
          />
          <Button
            variant="primary"
            onClick={() =>
              void saveCaseInfluencers(apiBaseUrl, bearerToken, investigationId, {
                added,
                switched_off: switchedOff,
                // Sent only when chosen: an override without one is exactly the body it was.
                ...(caseComposition ? { composition: caseComposition } : {}),
                words: "",
              })
                .then(() => done("This case's influencers are saved."))
                .catch(failed)
            }
          >
            Save this case's influencers
          </Button>
        </section>
      )}

      {canManage && history && (
        <section aria-labelledby="strength-installation">
          <h3 id="strength-installation" className="strength-panel__heading">
            Installation-wide influencers
          </h3>
          <p className="strength-panel__muted">
            A new version takes effect only when a second person with the right approves it. Every version is kept.
          </p>
          {inForceVersion ? (
            <p className="strength-panel__muted">
              Version {inForceVersion.version} is in force. {versionWords(inForceVersion)}
            </p>
          ) : (
            <p className="strength-panel__muted">No version approved yet: the shipped defaults are in force.</p>
          )}
          {waiting && (
            <div className="strength-panel__waiting" aria-label={`Version ${waiting.version}, waiting`}>
              <p className="strength-panel__heading">Version {waiting.version}, waiting</p>
              <p className="strength-panel__muted">{versionWords(waiting)}</p>
              {waiting.words && <p className="strength-panel__muted">“{waiting.words}”</p>}
              <InfluencerList influencers={waiting.influencers} linkName={linkName} />
              <Button
                variant="primary"
                disabled={ownWaiting}
                aria-describedby={ownWaiting ? "strength-own-waiting" : undefined}
                onClick={() =>
                  void approveInfluencers(apiBaseUrl, bearerToken, waiting.version)
                    .then(() => done(`Version ${waiting.version} is approved and in force.`))
                    .catch(failed)
                }
              >
                Approve version {waiting.version}
              </Button>
              {ownWaiting && (
                <p id="strength-own-waiting" className="strength-panel__muted">
                  You proposed it, so a second person with the right must approve it.
                </p>
              )}
              <label className="strength-panel__field">
                <span>Why it goes back (required)</span>
                <Input
                  aria-label="Why it goes back (required)"
                  value={sendBackWords}
                  onChange={(e) => setSendBackWords(e.target.value)}
                />
              </label>
              <Button
                disabled={!sendBackWords.trim()}
                onClick={() =>
                  void sendBackInfluencers(apiBaseUrl, bearerToken, waiting.version, sendBackWords.trim())
                    .then(() => {
                      setSendBackWords("");
                      done(`Version ${waiting.version} is sent back.`);
                    })
                    .catch(failed)
                }
              >
                {ownWaiting ? "Withdraw it" : "Send it back"}
              </Button>
            </div>
          )}
          {!waiting && proposal === null && (
            <Button
              onClick={() =>
                setProposal([
                  ...(inForceVersion?.influencers ?? history.defaults),
                ])
              }
            >
              Propose a new version
            </Button>
          )}
          {!waiting && proposal !== null && (
            <div className="strength-panel__proposal">
              <p className="strength-panel__heading">The new version</p>
              <InfluencerList
                influencers={proposal}
                linkName={linkName}
                onRemove={(id) => setProposal((held) => (held ?? []).filter((i) => i.id !== id))}
              />
              <InfluencerForm
                idPrefix="installation"
                entityTypes={entityTypes}
                edgeTypes={edgeTypes}
                onAdd={(i) => setProposal((held) => [...(held ?? []).filter((h) => h.id !== i.id), i])}
              />
              <label className="strength-panel__field">
                <span>Composition</span>
                <Select
                  aria-label="Composition"
                  value={proposalComposition}
                  onChange={(e) => setProposalComposition(e.target.value as Composition | "")}
                >
                  <option value="">As shipped ({COMPOSITION_LABEL[(history.default_composition ?? "standard") as Composition]})</option>
                  <option value="standard">{COMPOSITION_LABEL.standard}</option>
                  <option value="client_parity">{COMPOSITION_LABEL.client_parity}</option>
                </Select>
              </label>
              <label className="strength-panel__field">
                <span>Rarity measure</span>
                <Select
                  aria-label="Rarity measure"
                  value={proposalMeasure}
                  onChange={(e) => setProposalMeasure(e.target.value as RarityMeasure | "")}
                >
                  <option value="">As shipped ({MEASURE_LABEL[(history.default_rarity_measure ?? "share") as RarityMeasure]})</option>
                  <option value="share">{MEASURE_LABEL.share}</option>
                  <option value="idf">{MEASURE_LABEL.idf}</option>
                </Select>
              </label>
              <label className="strength-panel__field">
                <span>Why, for the approver</span>
                <Input aria-label="Why, for the approver" value={proposalWords} onChange={(e) => setProposalWords(e.target.value)} />
              </label>
              <Button
                variant="primary"
                onClick={() =>
                  void proposeInfluencers(apiBaseUrl, bearerToken, proposal, proposalWords, {
                    composition: proposalComposition || null,
                    rarity_measure: proposalMeasure || null,
                  })
                    .then((v) => {
                      setProposal(null);
                      setProposalWords("");
                      done(`Version ${v.version} is proposed; it waits for a second person's approval.`);
                    })
                    .catch(failed)
                }
              >
                Propose for approval
              </Button>
              <Button onClick={() => setProposal(null)}>Cancel</Button>
            </div>
          )}
          {history.versions.length > 0 && (
            <details className="strength-panel__history">
              <summary>Every version ({history.versions.length})</summary>
              <ol>
                {history.versions.map((v) => (
                  <li key={v.version}>
                    Version {v.version}: {versionWords(v)}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </section>
      )}
    </div>
  );
}
