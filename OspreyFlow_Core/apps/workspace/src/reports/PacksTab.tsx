// The Packs tab (ADR-113 stage 5): assemble a case's report pack from trends, assessments and
// notes, put the items in order, publish it as an immutable version, withdraw a version, and
// export it. Items arrive already counted and marked for this reader; what is withheld from them is
// said once, in a sentence with no number, never which.
import { useEffect, useState } from "react";

import type { AddPackItem, Judgement, PackDraft, PackHistory, PackVersionSummary, ReportPack, TrendDefinition } from "../../../../packages/schemas/generated";
import { Button, Input, Select } from "../design/primitives";
import type { ReportsApi } from "./api";
import { ExportControl } from "./ExportControl";
import { PackItemView } from "./PackItemView";
import { formatDay, WITHHELD_ITEMS_SENTENCE } from "./packText";
import {
  addItem,
  createPack,
  fetchClassifications,
  fetchHistory,
  getDraft,
  listJudgements,
  listPacks,
  publishPack,
  refreshItem,
  removeItem,
  reorderItems,
  withdrawVersion,
} from "./packsApi";
import { listTrends } from "./trendsApi";

type Kind = "trend" | "assessment" | "note";

/** The newest version still standing, or null while the pack is only a draft. */
function liveVersion(pack: ReportPack): PackVersionSummary | null {
  const live = (pack.versions ?? []).filter((v) => !v.withdrawn_at);
  return live.length === 0 ? null : live.reduce((a, b) => (b.version > a.version ? b : a));
}

function versionWords(v: PackVersionSummary): string {
  // ADR-106: the name the server resolved, or the id when it had none.
  const base = `Version ${v.version}, published ${formatDay(v.published_at)} by ${v.published_by_name ?? v.published_by}`;
  return v.withdrawn_at ? `${base}, withdrawn by ${v.withdrawn_by_name ?? v.withdrawn_by ?? "an administrator"}: ${v.withdrawal_reason ?? "no reason was given"}` : base;
}

export interface PacksTabProps {
  api: ReportsApi;
  canExport: boolean;
  print?: (html: string) => void;
}

export function PacksTab({ api, canExport, print }: PacksTabProps) {
  const [packs, setPacks] = useState<ReportPack[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [draft, setDraft] = useState<PackDraft | null>(null);
  const [history, setHistory] = useState<PackHistory | null>(null);
  const [trends, setTrends] = useState<TrendDefinition[]>([]);
  const [judgements, setJudgements] = useState<Judgement[]>([]);
  const [classifications, setClassifications] = useState<string[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [kind, setKind] = useState<Kind>("trend");
  const [trendId, setTrendId] = useState("");
  const [judgementId, setJudgementId] = useState("");
  const [noteText, setNoteText] = useState("");
  const [noteMarking, setNoteMarking] = useState("");
  const [withdrawing, setWithdrawing] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fail = (e: unknown) => setProblem((e as Error).message);

  useEffect(() => {
    let live = true;
    listPacks(api).then((p) => live && setPacks(p)).catch((e: Error) => live && setProblem(e.message));
    listTrends(api).then((t) => live && setTrends(t)).catch(() => live && setTrends([]));
    listJudgements(api).then((j) => live && setJudgements(j)).catch(() => live && setJudgements([]));
    fetchClassifications(api).then((c) => live && setClassifications(c)).catch((e: Error) => live && setProblem(e.message));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId]);

  async function open(packId: string) {
    setChosen(packId);
    setHistory(null);
    setWithdrawing(null);
    setProblem(null);
    setNotice(null);
    try {
      setDraft(await getDraft(api, packId));
    } catch (e) {
      setDraft(null);
      fail(e);
    }
  }

  /** After a change, read the pack and the list again so the screen says what the server holds. */
  async function reload(packId: string) {
    const [list, fresh] = await Promise.all([listPacks(api), getDraft(api, packId)]);
    setPacks(list);
    setDraft(fresh);
    setHistory(null);
  }

  async function act(work: () => Promise<void>) {
    setProblem(null);
    setNotice(null);
    try {
      await work();
    } catch (e) {
      fail(e);
    }
  }

  const create = () =>
    act(async () => {
      const made = await createPack(api, newTitle.trim());
      setNewTitle("");
      setPacks(await listPacks(api));
      await open(made.id);
      setNotice(`Created “${made.title}”.`);
    });

  const move = (at: number, by: -1 | 1) =>
    act(async () => {
      if (!draft) return;
      const ids = draft.items.map((i) => i.id);
      const other = at + by;
      const a = ids[at];
      const b = ids[other];
      if (a === undefined || b === undefined) return;
      ids[at] = b;
      ids[other] = a;
      setDraft(await reorderItems(api, draft.pack.id, ids));
    });

  const addableItem = (): AddPackItem | null => {
    if (kind === "trend") return trendId ? { kind: "trend", trend_id: trendId } : null;
    if (kind === "assessment") return judgementId ? { kind: "assessment", judgement_id: judgementId } : null;
    return noteText.trim() !== "" && noteMarking !== "" ? { kind: "note", text: noteText.trim(), classification: noteMarking } : null;
  };
  const toAdd = addableItem();

  const add = () =>
    act(async () => {
      if (!draft || !toAdd) return;
      await addItem(api, draft.pack.id, toAdd);
      setNoteText("");
      setNoteMarking("");
      setTrendId("");
      setJudgementId("");
      await reload(draft.pack.id);
      setNotice("Added to the pack.");
    });

  const publish = () =>
    act(async () => {
      if (!draft) return;
      const done = await publishPack(api, draft.pack.id);
      await reload(draft.pack.id);
      setNotice(`Published version ${done.version}.`);
    });

  const withdraw = (version: number) =>
    act(async () => {
      if (!draft) return;
      await withdrawVersion(api, draft.pack.id, version, reason.trim());
      setWithdrawing(null);
      setReason("");
      await reload(draft.pack.id);
      setNotice(`Withdrew version ${version}.`);
    });

  const toggleHistory = () =>
    act(async () => {
      if (!draft) return;
      setHistory(history ? null : await fetchHistory(api, draft.pack.id));
    });

  const live = draft ? liveVersion(draft.pack) : null;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-16)", display: "grid", gridTemplateColumns: "minmax(16rem, 22rem) 1fr", gap: "var(--sp-16)", alignContent: "start", alignItems: "start" }}>
      <section aria-label="Packs" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h3 className="value" style={{ margin: 0 }}>Packs</h3>
        {packs.length === 0 && <p className="label" style={{ margin: 0 }}>No packs have been made in this case yet.</p>}
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
          {packs.map((p) => {
            const v = liveVersion(p);
            return (
              <li key={p.id}>
                <Button aria-pressed={chosen === p.id} onClick={() => void open(p.id)}>
                  {`${p.title} · ${v ? `Published v${v.version}` : "Draft"}`}
                </Button>
              </li>
            );
          })}
        </ul>
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          New pack title
          <Input value={newTitle} maxLength={120} onChange={(e) => setNewTitle(e.target.value)} />
        </label>
        <div>
          <Button disabled={newTitle.trim() === ""} onClick={() => void create()}>Create pack</Button>
        </div>
      </section>

      <section aria-label="Pack" style={{ display: "grid", gap: "var(--sp-12)", alignContent: "start" }}>
        {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
        {notice && <p role="status" style={{ margin: 0 }}>{notice}</p>}
        {!draft && !problem && <p className="label" style={{ margin: 0 }}>Choose a pack, or make one, to see it here.</p>}
        {draft && (
          <>
            <h3 style={{ margin: 0 }}>{draft.pack.title}</h3>
            {draft.marking && <p className="label" style={{ margin: 0 }}>{`Marked ${draft.marking}`}</p>}
            {(draft.pack.versions ?? []).length > 0 && (
              <ul aria-label="Versions" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
                {(draft.pack.versions ?? []).map((v) => (
                  <li key={v.version} style={{ display: "grid", gap: "var(--sp-4)" }}>
                    <span>{versionWords(v)}</span>
                    {!v.withdrawn_at && withdrawing !== v.version && (
                      <span>
                        <Button onClick={() => { setWithdrawing(v.version); setReason(""); }}>{`Withdraw version ${v.version}`}</Button>
                      </span>
                    )}
                    {withdrawing === v.version && (
                      <span style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end", flexWrap: "wrap" }}>
                        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
                          Reason for withdrawing
                          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
                        </label>
                        <Button variant="primary" disabled={reason.trim() === ""} onClick={() => void withdraw(v.version)}>Withdraw</Button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {draft.withheld && <p style={{ margin: 0 }}>{WITHHELD_ITEMS_SENTENCE}</p>}
            {draft.items.length === 0 && <p className="label" style={{ margin: 0 }}>This pack has no items you can see yet.</p>}
            {draft.items.map((item, at) => (
              <PackItemView key={item.id} item={item}>
                <Button disabled={at === 0} onClick={() => void move(at, -1)}>Move up</Button>
                <Button disabled={at === draft.items.length - 1} onClick={() => void move(at, 1)}>Move down</Button>
                {item.kind === "trend" && (
                  <Button onClick={() => void act(async () => { await refreshItem(api, draft.pack.id, item.id); await reload(draft.pack.id); setNotice("The snapshot was refreshed."); })}>
                    Refresh
                  </Button>
                )}
                <Button onClick={() => void act(async () => { await removeItem(api, draft.pack.id, item.id); await reload(draft.pack.id); })}>Remove</Button>
              </PackItemView>
            ))}

            <fieldset style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-8)" }}>
              <legend className="label">Add an item</legend>
              <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
                Item kind
                <Select aria-label="Item kind" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
                  <option value="trend">Trend</option>
                  <option value="assessment">Assessment</option>
                  <option value="note">Note</option>
                </Select>
              </label>
              {kind === "trend" && (
                <Select aria-label="Saved trend" value={trendId} onChange={(e) => setTrendId(e.target.value)}>
                  <option value="">{trends.length === 0 ? "No trends are saved in this case" : "Choose a saved trend"}</option>
                  {trends.map((t) => (
                    <option key={t.id} value={t.id}>{t.title}</option>
                  ))}
                </Select>
              )}
              {kind === "assessment" && (
                <Select aria-label="Assessment" value={judgementId} onChange={(e) => setJudgementId(e.target.value)}>
                  <option value="">{judgements.length === 0 ? "No assessments have been recorded in this case" : "Choose an assessment"}</option>
                  {judgements.map((j) => (
                    <option key={j.id} value={j.id}>{j.statement}</option>
                  ))}
                </Select>
              )}
              {kind === "note" && (
                <>
                  <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
                    Note
                    <textarea className="input" rows={3} value={noteText} onChange={(e) => setNoteText(e.target.value)} />
                  </label>
                  <Select aria-label="Note marking" value={noteMarking} onChange={(e) => setNoteMarking(e.target.value)}>
                    <option value="">Choose a marking</option>
                    {classifications.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </Select>
                  {noteText.trim() !== "" && noteMarking === "" && (
                    <p className="label" style={{ margin: 0 }}>Choose a marking for the note: it is never marked for you.</p>
                  )}
                </>
              )}
              <div>
                <Button disabled={toAdd === null} onClick={() => void add()}>Add item</Button>
              </div>
            </fieldset>

            <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
              <Button variant="primary" onClick={() => void publish()}>Publish</Button>
              <Button aria-pressed={history !== null} onClick={() => void toggleHistory()}>{history ? "Hide history" : "Show history"}</Button>
            </div>
            {history && (
              <section aria-label="History" style={{ display: "grid", gap: "var(--sp-8)" }}>
                <h4 style={{ margin: 0 }}>Earlier snapshots</h4>
                {history.earlier_snapshots.length === 0 && <p className="label" style={{ margin: 0 }}>Nothing in this pack has been replaced yet.</p>}
                {history.earlier_snapshots.map((s) => (
                  <PackItemView key={s.id} item={s} replacedNote />
                ))}
                {history.withheld && <p style={{ margin: 0 }}>{WITHHELD_ITEMS_SENTENCE}</p>}
              </section>
            )}
            {canExport && live && <ExportControl api={api} packId={draft.pack.id} print={print} />}
          </>
        )}
      </section>
    </div>
  );
}
