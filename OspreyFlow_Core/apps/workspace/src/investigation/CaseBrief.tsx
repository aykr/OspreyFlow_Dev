// The open case's brief (ADR-128 decision 3, script chapter 1), in the Cases drawer beside the case's
// other settings: the priority information requirement and up to twenty information requirements,
// each open or answered and each linked to what answers it (a saved trend, a saved pattern, an
// assessment, a canvas view). Every reader of the case reads it; only its Author edits, and the
// Conduit refuses anyone else whatever is shown here (the edit controls follow `canChangeCase`, as
// the case's domain models do).
//
// Rule 3: the server leaves out an attachment this reader may not read, and this panel adds nothing
// in its place: no placeholder, no count, no word about attachments for a requirement that shows
// none. Rule 5: a requirement is marked answered only by the person pressing its own button, which
// sends the one status request; no other control sends a status.
//
// Keyboard (rule 13): every control is a native button, textarea or select, in reading order. Add,
// Edit and Attach open their field with focus in it; Ctrl+Enter saves it, Escape cancels it, and
// either returns focus to the button that opened it. `keyboard/case-brief.spec.ts` proves it.
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "../design/primitives/Button";
import { canChangeCase, type Rights } from "../rights/visibility";
import {
  KIND_CHOICES,
  MAX_REQUIREMENTS,
  MAX_TEXT_CHARS,
  addRequirement,
  attach,
  candidatesFor,
  detach,
  editRequirement,
  readBrief,
  removeRequirement,
  setPriority,
  setStatus,
  type AttachmentKind,
  type BriefApi,
  type Candidate,
  type CaseBriefView,
  type RequirementStatus,
} from "./briefApi";
import { listCases } from "./cases";

export interface CaseBriefProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The person's rights (`GET /v1/me/rights`); the edits are offered only with `share_case`. */
  rights?: Rights;
  /** Opens what an attachment points at (a trend, a saved pattern, an assessment, a canvas view). */
  onOpenAttachment?: (kind: AttachmentKind, id: string) => void;
}

const KIND_WORD: Record<AttachmentKind, string> = {
  trend: "trend",
  pattern: "pattern",
  assessment: "assessment",
  view: "view",
};

interface Attaching {
  requirementId: string;
  kind: AttachmentKind | "";
  /** `null` while the choices are being read. */
  options: Candidate[] | null;
  choice: string;
}

const boxStyle = { width: "100%", boxSizing: "border-box", resize: "vertical" } as const;

/** The brief of one case. It is keyed by the case, so opening another case starts it afresh: the
 * previous case's brief, its edit rights, an open Add box and any change still in flight stay with
 * the case they were made in and cannot reach this one. */
export function CaseBrief(props: CaseBriefProps) {
  return <CaseBriefOfCase key={props.investigationId} {...props} />;
}

function CaseBriefOfCase({ apiBaseUrl, bearerToken, investigationId, rights = null, onOpenAttachment }: CaseBriefProps) {
  const api: BriefApi = { apiBaseUrl, bearerToken, investigationId };
  const [brief, setBrief] = useState<CaseBriefView | null>(null);
  const [canEdit, setCanEdit] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editingPriority, setEditingPriority] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [attaching, setAttaching] = useState<Attaching | null>(null);
  // The control that should take focus once the next render has put it on the page.
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;
    readBrief({ apiBaseUrl, bearerToken, investigationId })
      .then((read) => {
        if (cancelled) return;
        setBrief(read);
        setProblem(null);
      })
      .catch((error: unknown) => !cancelled && setProblem(error instanceof Error ? error.message : String(error)));
    listCases(apiBaseUrl, bearerToken)
      .then((cases) => !cancelled && setCanEdit(canChangeCase(rights, cases.find((c) => c.id === investigationId)?.level)))
      .catch(() => !cancelled && setCanEdit(false));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, rights]);

  useEffect(() => {
    if (focusKey === null) return;
    root.current?.querySelector<HTMLElement>(`[data-focus="${focusKey}"]`)?.focus();
    setFocusKey(null);
  }, [focusKey, brief, editing, editingPriority, adding, attaching, confirming]);

  /** One change: sent, and the brief the server answers shown. A refusal is said in its own words
   * and leaves the brief as it was. Returns whether it was made. */
  const change = useCallback(
    async (send: () => Promise<CaseBriefView>): Promise<boolean> => {
      if (busy) return false;
      setBusy(true);
      setProblem(null);
      try {
        setBrief(await send());
        return true;
      } catch (error) {
        setProblem(error instanceof Error ? error.message : String(error));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  const onBoxKey = (save: () => void, cancel: () => void) => (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      save();
    }
  };

  const savePriority = async () => {
    if (editingPriority === null) return;
    if (await change(() => setPriority(api, editingPriority))) {
      setEditingPriority(null);
      setFocusKey("priority");
    }
  };
  const cancelPriority = () => {
    setEditingPriority(null);
    setFocusKey("priority");
  };

  const saveAdd = async () => {
    if (adding === null || !adding.trim()) return;
    if (await change(() => addRequirement(api, adding))) {
      setAdding(null);
      setFocusKey("add");
    }
  };
  const cancelAdd = () => {
    setAdding(null);
    setFocusKey("add");
  };

  const saveEdit = async () => {
    if (!editing || !editing.text.trim()) return;
    const { id, text } = editing;
    if (await change(() => editRequirement(api, id, text))) {
      setEditing(null);
      setFocusKey(`edit-${id}`);
    }
  };
  const cancelEdit = () => {
    if (!editing) return;
    const { id } = editing;
    setEditing(null);
    setFocusKey(`edit-${id}`);
  };

  const mark = async (id: string, status: RequirementStatus) => {
    if (await change(() => setStatus(api, id, status))) setFocusKey(`status-${id}`);
  };

  const remove = async (id: string) => {
    if (await change(() => removeRequirement(api, id))) {
      setConfirming(null);
      setFocusKey("add");
    }
  };

  // After a detach, focus goes to the next attachment's Detach button, else the previous one's, else
  // the requirement's Attach button: not to the page, which the removed button would leave it on.
  const detachOne = async (
    requirementId: string,
    held: readonly { kind: AttachmentKind; id: string }[],
    kind: AttachmentKind,
    attachmentId: string,
  ) => {
    const at = held.findIndex((a) => a.kind === kind && a.id === attachmentId);
    const neighbour = held[at + 1] ?? held[at - 1];
    if (await change(() => detach(api, requirementId, kind, attachmentId))) {
      setFocusKey(neighbour ? `detach-${requirementId}-${neighbour.kind}:${neighbour.id}` : `attach-${requirementId}`);
    }
  };

  const openAttach = (requirementId: string) => {
    setConfirming(null);
    setEditing(null);
    setAttaching({ requirementId, kind: "", options: [], choice: "" });
  };
  const chooseKind = async (kind: AttachmentKind | "") => {
    if (!attaching) return;
    const requirementId = attaching.requirementId;
    if (kind === "") {
      setAttaching({ requirementId, kind, options: [], choice: "" });
      return;
    }
    setAttaching({ requirementId, kind, options: null, choice: "" });
    try {
      const held = new Set(
        brief?.requirements.find((r) => r.id === requirementId)?.attachments.filter((a) => a.kind === kind).map((a) => a.id),
      );
      const offered = (await candidatesFor(api, kind)).filter((c) => !held.has(c.id));
      setAttaching((now) => (now && now.kind === kind ? { ...now, options: offered } : now));
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
      setAttaching((now) => (now && now.kind === kind ? { ...now, options: [] } : now));
    }
  };
  const saveAttach = async () => {
    if (!attaching || attaching.kind === "" || attaching.choice === "") return;
    const { requirementId, kind, choice } = attaching;
    if (await change(() => attach(api, requirementId, kind, choice))) {
      setAttaching(null);
      setFocusKey(`attach-${requirementId}`);
    }
  };
  const cancelAttach = () => {
    if (!attaching) return;
    const { requirementId } = attaching;
    setAttaching(null);
    setFocusKey(`attach-${requirementId}`);
  };

  const requirements = brief?.requirements ?? [];

  return (
    <section ref={root} aria-label="Brief" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="label" style={{ margin: 0 }}>
        Brief
      </h3>
      {brief === null && !problem && <span className="label">Loading…</span>}
      {problem && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {problem}
        </span>
      )}
      {brief !== null && (
        <>
          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span className="label">Priority information requirement</span>
            {editingPriority !== null ? (
              <>
                <textarea
                  className="input"
                  aria-label="Priority information requirement"
                  rows={3}
                  maxLength={MAX_TEXT_CHARS}
                  value={editingPriority}
                  disabled={busy}
                  autoFocus
                  onChange={(e) => setEditingPriority(e.target.value)}
                  onKeyDown={onBoxKey(() => void savePriority(), cancelPriority)}
                  style={boxStyle}
                />
                <span style={{ display: "flex", gap: "var(--sp-8)" }}>
                  <Button variant="primary" disabled={busy} onClick={() => void savePriority()}>
                    Save
                  </Button>
                  <Button disabled={busy} onClick={cancelPriority}>
                    Cancel
                  </Button>
                </span>
              </>
            ) : (
              <>
                {brief.priority ? (
                  <p style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{brief.priority}</p>
                ) : (
                  <p style={{ margin: 0, color: "var(--text-tertiary)" }}>No priority information requirement is set.</p>
                )}
                {canEdit && (
                  <span>
                    <Button data-focus="priority" onClick={() => setEditingPriority(brief.priority)}>
                      Edit the priority requirement
                    </Button>
                  </span>
                )}
              </>
            )}
          </div>

          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span className="label">Information requirements</span>
            {requirements.length === 0 ? (
              <p style={{ margin: 0, color: "var(--text-tertiary)" }}>No information requirements yet.</p>
            ) : (
              <ol
                aria-label="Information requirements"
                style={{ margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-8)" }}
              >
                {requirements.map((r, index) => {
                  const n = index + 1;
                  return (
                    <li key={r.id}>
                      <div style={{ display: "grid", gap: "var(--sp-4)" }}>
                        <span className="label">{r.status === "answered" ? "Answered" : "Open"}</span>
                        {editing?.id === r.id ? (
                          <>
                            <textarea
                              className="input"
                              aria-label={`Requirement ${n}`}
                              rows={3}
                              maxLength={MAX_TEXT_CHARS}
                              value={editing.text}
                              disabled={busy}
                              autoFocus
                              onChange={(e) => setEditing({ id: r.id, text: e.target.value })}
                              onKeyDown={onBoxKey(() => void saveEdit(), cancelEdit)}
                              style={boxStyle}
                            />
                            <span style={{ display: "flex", gap: "var(--sp-8)" }}>
                              <Button variant="primary" disabled={busy || !editing.text.trim()} onClick={() => void saveEdit()}>
                                Save
                              </Button>
                              <Button disabled={busy} onClick={cancelEdit}>
                                Cancel
                              </Button>
                            </span>
                          </>
                        ) : (
                          <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{r.text}</div>
                        )}

                        {r.attachments.length > 0 && (
                          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
                            <span className="label">Answered by</span>
                            <ul
                              aria-label={`Attachments of requirement ${n}`}
                              style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}
                            >
                              {r.attachments.map((a) => (
                                <li key={`${a.kind}:${a.id}`} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                                  <Button
                                    aria-label={`Open ${KIND_WORD[a.kind]}: ${a.title}`}
                                    disabled={!onOpenAttachment}
                                    onClick={() => onOpenAttachment?.(a.kind, a.id)}
                                  >
                                    {a.title}
                                  </Button>
                                  {canEdit && (
                                    <Button
                                      data-focus={`detach-${r.id}-${a.kind}:${a.id}`}
                                      aria-label={`Detach ${KIND_WORD[a.kind]}: ${a.title}`}
                                      disabled={busy}
                                      onClick={() => void detachOne(r.id, r.attachments, a.kind, a.id)}
                                    >
                                      Detach
                                    </Button>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {canEdit && editing?.id !== r.id && (
                          <span style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
                            {confirming === r.id ? (
                              <>
                                <Button disabled={busy} onClick={() => void remove(r.id)} aria-label={`Confirm remove requirement ${n}`}>
                                  Confirm remove
                                </Button>
                                <Button
                                  aria-label={`Keep requirement ${n}`}
                                  onClick={() => {
                                    setConfirming(null);
                                    setFocusKey(`remove-${r.id}`);
                                  }}
                                >
                                  Keep
                                </Button>
                              </>
                            ) : (
                              <>
                                <Button
                                  data-focus={`status-${r.id}`}
                                  disabled={busy}
                                  aria-label={r.status === "answered" ? `Reopen requirement ${n}` : `Mark requirement ${n} answered`}
                                  onClick={() => void mark(r.id, r.status === "answered" ? "open" : "answered")}
                                >
                                  {r.status === "answered" ? "Reopen" : "Mark answered"}
                                </Button>
                                <Button
                                  data-focus={`edit-${r.id}`}
                                  aria-label={`Edit requirement ${n}`}
                                  onClick={() => {
                                    setAttaching(null);
                                    setEditing({ id: r.id, text: r.text });
                                  }}
                                >
                                  Edit
                                </Button>
                                <Button
                                  data-focus={`attach-${r.id}`}
                                  aria-label={`Attach to requirement ${n}`}
                                  onClick={() => openAttach(r.id)}
                                >
                                  Attach…
                                </Button>
                                <Button
                                  data-focus={`remove-${r.id}`}
                                  aria-label={`Remove requirement ${n}`}
                                  onClick={() => {
                                    setAttaching(null);
                                    setConfirming(r.id);
                                  }}
                                >
                                  Remove
                                </Button>
                              </>
                            )}
                          </span>
                        )}

                        {canEdit && attaching?.requirementId === r.id && (
                          <fieldset
                            aria-label={`Attach to requirement ${n}`}
                            style={{ display: "grid", gap: "var(--sp-4)", border: "1px solid var(--border-subtle)", borderRadius: "var(--r-control)", padding: "var(--sp-8)" }}
                            onKeyDown={(e) => {
                              if (e.key === "Escape") {
                                e.preventDefault();
                                cancelAttach();
                              }
                            }}
                          >
                            <label className="label" htmlFor={`brief-attach-kind-${r.id}`}>
                              Kind of attachment
                            </label>
                            <select
                              id={`brief-attach-kind-${r.id}`}
                              className="input"
                              aria-label="Kind of attachment"
                              value={attaching.kind}
                              disabled={busy}
                              autoFocus
                              onChange={(e) => void chooseKind(e.target.value as AttachmentKind | "")}
                            >
                              <option value="">Choose…</option>
                              {KIND_CHOICES.map((k) => (
                                <option key={k.value} value={k.value}>
                                  {k.label}
                                </option>
                              ))}
                            </select>
                            {attaching.kind !== "" && attaching.options === null && <span className="label">Loading…</span>}
                            {attaching.kind !== "" && attaching.options !== null && attaching.options.length === 0 && (
                              <span className="label">Nothing of this kind to attach.</span>
                            )}
                            {attaching.kind !== "" && attaching.options !== null && attaching.options.length > 0 && (
                              <select
                                className="input"
                                aria-label="What to attach"
                                value={attaching.choice}
                                disabled={busy}
                                onChange={(e) => setAttaching({ ...attaching, choice: e.target.value })}
                              >
                                <option value="">Choose…</option>
                                {attaching.options.map((o) => (
                                  <option key={o.id} value={o.id}>
                                    {o.label}
                                  </option>
                                ))}
                              </select>
                            )}
                            <span style={{ display: "flex", gap: "var(--sp-8)" }}>
                              <Button variant="primary" disabled={busy || attaching.choice === ""} onClick={() => void saveAttach()}>
                                Attach
                              </Button>
                              <Button disabled={busy} onClick={cancelAttach}>
                                Cancel
                              </Button>
                            </span>
                          </fieldset>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}

            {canEdit && requirements.length >= MAX_REQUIREMENTS && (
              <span className="label">A brief holds at most {MAX_REQUIREMENTS} requirements.</span>
            )}
            {canEdit && requirements.length < MAX_REQUIREMENTS && adding === null && (
              <span>
                <Button data-focus="add" onClick={() => setAdding("")}>
                  Add a requirement
                </Button>
              </span>
            )}
            {canEdit && adding !== null && (
              <>
                <textarea
                  className="input"
                  aria-label="New information requirement"
                  rows={3}
                  maxLength={MAX_TEXT_CHARS}
                  value={adding}
                  disabled={busy}
                  autoFocus
                  onChange={(e) => setAdding(e.target.value)}
                  onKeyDown={onBoxKey(() => void saveAdd(), cancelAdd)}
                  style={boxStyle}
                />
                <span style={{ display: "flex", gap: "var(--sp-8)" }}>
                  <Button variant="primary" disabled={busy || !adding.trim()} onClick={() => void saveAdd()}>
                    Add
                  </Button>
                  <Button disabled={busy} onClick={cancelAdd}>
                    Cancel
                  </Button>
                </span>
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
