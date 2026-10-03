import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import type { LinkNote } from "../../../../packages/schemas/generated";
import {
  LinkNotesError,
  addLinkNote,
  editLinkNote,
  listLinkNotes,
  removeLinkNote,
} from "./linkNotesApi";

/** The same limit the server holds (`services/api/link_notes.py::MAX_NOTE_CHARS`). */
export const MAX_NOTE_CHARS = 4000;
/** The count of characters left appears this far from the limit, not before. */
const SHOW_COUNT_FROM = 3500;

export interface LinkNotesProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The selected link's id — the working set's own edge id. */
  edgeId: string;
}

type Load = { state: "loading" } | { state: "ready" } | { state: "refused"; message: string };

function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

function sentence(error: unknown, doing: "saved" | "removed"): string {
  if (error instanceof LinkNotesError) {
    if (error.kind === "invalid" || error.kind === "not_yours") return error.message;
    if (error.kind === "link_not_found") {
      return `The note could not be ${doing}: this link is no longer in your view.`;
    }
    if (error.kind === "note_not_found") return "That note has already gone.";
    if (error.kind === "forbidden") {
      return `The note could not be ${doing}. You can read notes in this case but not change them.`;
    }
  }
  return `The note could not be ${doing}. Try again.`;
}

function Remaining({ text }: { text: string }) {
  if (text.length < SHOW_COUNT_FROM) return null;
  return (
    <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
      {MAX_NOTE_CHARS - text.length} characters left
    </span>
  );
}

/** The Inspector's **Notes** section for a selected link (`02_GLASS_FRONTEND.md` §2, ADR-075):
 * several dated plain-text notes, newest first, each with who wrote it. Everyone who can see the
 * link sees them; only the author edits or deletes their own. Notes are text, never markup. */
export function LinkNotes({ apiBaseUrl, bearerToken, investigationId, edgeId }: LinkNotesProps) {
  const [notes, setNotes] = useState<LinkNote[]>([]);
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    let current = true;
    setLoad({ state: "loading" });
    setNotes([]);
    setDraft("");
    setProblem(null);
    setEditing(null);
    setConfirming(null);
    listLinkNotes(apiBaseUrl, bearerToken, investigationId, edgeId).then(
      (found) => {
        if (!current) return;
        setNotes(found);
        setLoad({ state: "ready" });
      },
      (error: unknown) => {
        if (!current) return;
        setLoad({
          state: "refused",
          message:
            error instanceof LinkNotesError && error.kind === "link_not_found"
              ? "This link is not in your view, so its notes cannot be shown."
              : "The notes could not be loaded. Select the link again to retry.",
        });
      },
    );
    return () => {
      current = false;
    };
  }, [apiBaseUrl, bearerToken, investigationId, edgeId]);

  const focusEdit = useCallback((id: string) => {
    window.setTimeout(() => {
      listRef.current?.querySelector<HTMLElement>(`[data-note-edit="${id}"]`)?.focus();
    }, 0);
  }, []);

  const add = async () => {
    if (!draft.trim() || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const added = await addLinkNote(apiBaseUrl, bearerToken, investigationId, edgeId, draft);
      setNotes((existing) => [added, ...existing]);
      setDraft("");
    } catch (error) {
      setProblem(sentence(error, "saved"));
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    if (!editing || !editing.text.trim() || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const saved = await editLinkNote(
        apiBaseUrl,
        bearerToken,
        investigationId,
        edgeId,
        editing.id,
        editing.text,
      );
      setNotes((existing) => existing.map((n) => (n.id === saved.id ? saved : n)));
      setEditing(null);
      focusEdit(saved.id);
    } catch (error) {
      setProblem(sentence(error, "saved"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (busy) return;
    setBusy(true);
    setProblem(null);
    try {
      await removeLinkNote(apiBaseUrl, bearerToken, investigationId, edgeId, id);
      setNotes((existing) => existing.filter((n) => n.id !== id));
      setConfirming(null);
    } catch (error) {
      setProblem(sentence(error, "removed"));
    } finally {
      setBusy(false);
    }
  };

  const onDraftKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void add();
    }
  };

  const onEditKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      const id = editing?.id;
      setEditing(null);
      if (id) focusEdit(id);
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void saveEdit();
    }
  };

  return (
    <section aria-label="Notes" style={{ marginTop: "var(--sp-16)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)", color: "var(--text-secondary)" }}>
        Notes{load.state === "ready" && notes.length > 0 ? ` (${notes.length})` : ""}
      </h3>

      {load.state === "loading" && (
        <p style={{ color: "var(--text-tertiary)" }}>Loading notes…</p>
      )}

      {load.state === "refused" && (
        <p role="alert" style={{ color: "var(--text-secondary)" }}>
          {load.message}
        </p>
      )}

      {load.state === "ready" && (
        <>
          <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: "var(--sp-4) 0" }}>
            Everyone who can see this link sees its notes. A note has no marking of its own: it
            takes the link&rsquo;s, so do not put in a note anything more sensitive than the link.
          </p>

          <label
            htmlFor="link-note-new"
            style={{ display: "block", fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}
          >
            New note
          </label>
          <textarea
            id="link-note-new"
            className="input"
            rows={3}
            maxLength={MAX_NOTE_CHARS}
            value={draft}
            disabled={busy}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onDraftKey}
            style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
          />
          <div
            style={{
              display: "flex",
              gap: "var(--sp-8)",
              alignItems: "center",
              justifyContent: "space-between",
              marginTop: "var(--sp-4)",
            }}
          >
            <Remaining text={draft} />
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !draft.trim()}
              onClick={() => void add()}
            >
              Add note
            </button>
          </div>

          {problem && (
            <p role="alert" style={{ color: "var(--text-secondary)" }}>
              {problem}
            </p>
          )}

          {notes.length === 0 ? (
            <p style={{ color: "var(--text-tertiary)" }}>No notes on this link yet.</p>
          ) : (
            <ul
              ref={listRef}
              style={{ listStyle: "none", margin: "var(--sp-8) 0 0", padding: 0, display: "grid", gap: "var(--sp-8)" }}
            >
              {notes.map((n) => (
                <li
                  key={n.id}
                  style={{
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--r-control)",
                    padding: "var(--sp-8)",
                  }}
                >
                  {editing?.id === n.id ? (
                    <>
                      <label
                        htmlFor={`link-note-edit-${n.id}`}
                        style={{ display: "block", fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}
                      >
                        Note text
                      </label>
                      <textarea
                        id={`link-note-edit-${n.id}`}
                        className="input"
                        rows={3}
                        maxLength={MAX_NOTE_CHARS}
                        value={editing.text}
                        disabled={busy}
                        autoFocus
                        onChange={(e) => setEditing({ id: n.id, text: e.target.value })}
                        onKeyDown={onEditKey}
                        style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
                      />
                      <div style={{ display: "flex", gap: "var(--sp-8)", marginTop: "var(--sp-4)", alignItems: "center" }}>
                        <Remaining text={editing.text} />
                        <span style={{ flex: 1 }} />
                        <button
                          type="button"
                          className="btn"
                          onClick={() => {
                            setEditing(null);
                            focusEdit(n.id);
                          }}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="btn btn--primary"
                          disabled={busy || !editing.text.trim()}
                          onClick={() => void saveEdit()}
                        >
                          Save
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="value" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                        {n.body}
                      </div>
                      <div style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", marginTop: "var(--sp-4)" }}>
                        {n.author} · {when(n.created_at)}
                        {n.edited_at ? ` · edited ${when(n.edited_at)}` : ""}
                      </div>
                      {n.mine && (
                        <div style={{ display: "flex", gap: "var(--sp-8)", marginTop: "var(--sp-4)" }}>
                          {confirming === n.id ? (
                            <>
                              <button
                                type="button"
                                className="btn"
                                disabled={busy}
                                onClick={() => void remove(n.id)}
                              >
                                Confirm delete
                              </button>
                              <button type="button" className="btn" onClick={() => setConfirming(null)}>
                                Cancel
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                className="btn"
                                data-note-edit={n.id}
                                aria-label="Edit note"
                                onClick={() => {
                                  setConfirming(null);
                                  setEditing({ id: n.id, text: n.body });
                                }}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="btn"
                                aria-label="Delete note"
                                onClick={() => setConfirming(n.id)}
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
