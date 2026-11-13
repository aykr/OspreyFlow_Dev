// *Views in this case* (ADR-144 decisions 3 and 5): the case's views this reader may see, their own
// and those shared with the case, each opened from its row. Only a view's creator is offered *Share
// with the case* (while it is private) and *Delete* (asked once: deleting a view deletes nothing on
// the case). Under the GOV.UK brand it is a GOV.UK summary list with a *Private* or *Shared* tag
// (decision 7).
//
// It enforces nothing: the Conduit lists only the views this reader may see, and refuses a share or
// a delete by anyone but the creator. A member is never shown another's private view because the
// server never sends it; the panel draws what it is given.
import { useCallback, useEffect, useRef, useState } from "react";

import { currentBrand } from "../brand/brand";
import "./views.css";
import { type CaseView, deleteView, listViews, shareView } from "./viewsApi";

export interface ViewsPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  caseId: string;
  /** The signed-in account (`sub`): the creator of a view is offered its share and delete. */
  me: string;
  /** The view open now, if one is, marked "open now". */
  openViewId?: string | null;
  onOpen: (view: CaseView) => void;
  /** A view was deleted: if it is the one open, the caller goes back to the case. */
  onDeleted?: (viewId: string) => void;
  /** Bumped by the caller after it saves a view, so the list is read again. */
  refreshKey?: number;
  /** Opened by the case line's *Views in this case* (ADR-145 Amendment 15): the panel takes focus, so the list is
   * where the person is. */
  takeFocus?: boolean;
}

type Asking = { id: string; what: "delete" } | null;

export function ViewsPanel({ apiBaseUrl, bearerToken, caseId, me, openViewId = null, onOpen, onDeleted, refreshKey = 0, takeFocus = false }: ViewsPanelProps) {
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    if (takeFocus) section.current?.focus();
  }, [takeFocus]);
  const [views, setViews] = useState<CaseView[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [asking, setAsking] = useState<Asking>(null);
  const govuk = currentBrand() === "govuk";

  const load = useCallback(() => {
    let cancelled = false;
    listViews(apiBaseUrl, bearerToken, caseId)
      .then((listed) => {
        if (cancelled) return;
        setViews(listed);
        setProblem(null);
      })
      .catch((failure: unknown) => {
        if (cancelled) return;
        setViews([]);
        setProblem(failure instanceof Error ? failure.message : "The views could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, caseId]);

  useEffect(() => load(), [load, refreshKey]);

  async function share(view: CaseView): Promise<void> {
    const done = await shareView(apiBaseUrl, bearerToken, caseId, view.id);
    if (!done.ok) {
      setProblem(done.message);
      return;
    }
    setProblem(null);
    setViews((current) => (current ?? []).map((v) => (v.id === view.id ? { ...v, shared: true } : v)));
  }

  async function remove(view: CaseView): Promise<void> {
    const done = await deleteView(apiBaseUrl, bearerToken, caseId, view.id);
    if (!done.ok) {
      setProblem(done.message);
      return;
    }
    setProblem(null);
    setAsking(null);
    setViews((current) => (current ?? []).filter((v) => v.id !== view.id));
    onDeleted?.(view.id);
  }

  const heading = (
    <h3 id={`views-in-${caseId}`} className={govuk ? "govuk-heading-s" : "label"} style={{ margin: 0 }}>
      Views in this case
    </h3>
  );

  if (views === null) {
    return (
      <section ref={section} tabIndex={-1} aria-labelledby={`views-in-${caseId}`} className="case-views">
        {heading}
        <p className={govuk ? "govuk-body-s" : "caption"}>Loading the views…</p>
      </section>
    );
  }

  return (
    <section ref={section} tabIndex={-1} aria-labelledby={`views-in-${caseId}`} className={govuk ? "case-views case-views--govuk" : "case-views"}>
      {heading}
      {views.length === 0 && problem ? null : views.length === 0 ? (
        <p className={govuk ? "govuk-body-s" : "caption"}>
          No views yet. Select nodes on the canvas and choose <em>Save as a view</em>.
        </p>
      ) : govuk ? (
        <dl className="govuk-summary-list govuk-summary-list--no-border" aria-label="Views in this case">
          {views.map((view) => (
            <div key={view.id} className="govuk-summary-list__row" data-view-id={view.id}>
              <dt className="govuk-summary-list__key">
                {view.name}
                {view.id === openViewId && <span className="govuk-body-s"> (open now)</span>}
              </dt>
              <dd className="govuk-summary-list__value">
                <strong className={view.shared ? "govuk-tag govuk-tag--green" : "govuk-tag govuk-tag--grey"}>
                  {view.shared ? "Shared" : "Private"}
                </strong>
              </dd>
              <dd className="govuk-summary-list__actions">
                <Actions
                  govuk
                  view={view}
                  mine={view.created_by === me}
                  asking={asking}
                  onOpen={() => onOpen(view)}
                  onShare={() => void share(view)}
                  onAskDelete={() => setAsking({ id: view.id, what: "delete" })}
                  onDelete={() => void remove(view)}
                  onCancel={() => setAsking(null)}
                />
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <ul aria-label="Views in this case" className="case-views__list">
          {views.map((view) => (
            <li key={view.id} className="case-views__row" data-view-id={view.id}>
              <span className="case-views__line">
                <span className="case-views__name" title={view.name}>
                  {view.name}
                </span>
                <span className={view.shared ? "view-tag view-tag--shared" : "view-tag"}>{view.shared ? "Shared" : "Private"}</span>
                {view.id === openViewId && <span className="caption">open now</span>}
              </span>
              <Actions
                govuk={false}
                view={view}
                mine={view.created_by === me}
                asking={asking}
                onOpen={() => onOpen(view)}
                onShare={() => void share(view)}
                onAskDelete={() => setAsking({ id: view.id, what: "delete" })}
                onDelete={() => void remove(view)}
                onCancel={() => setAsking(null)}
              />
            </li>
          ))}
        </ul>
      )}
      {problem && (
        <p role="alert" className={govuk ? "govuk-error-message" : "case-views__problem"}>
          {problem}
        </p>
      )}
    </section>
  );
}

interface ActionsProps {
  govuk: boolean;
  view: CaseView;
  mine: boolean;
  asking: Asking;
  onOpen: () => void;
  onShare: () => void;
  onAskDelete: () => void;
  onDelete: () => void;
  onCancel: () => void;
}

function Actions({ govuk, view, mine, asking, onOpen, onShare, onAskDelete, onDelete, onCancel }: ActionsProps) {
  // ADR-145 Amendment 14 decision 1 (the owner, 13 November 2026: Open covered the Private tag and the
  // buttons wrapped to four lines in the 360 px Cases drawer): under GOV.UK a row's actions are GOV.UK links,
  // as a summary list's actions are, on one line under the view's name and tag. The question before a delete
  // keeps GOV.UK's buttons: it is the one place a choice is made.
  const action = govuk ? "govuk-link case-views__link" : "btn btn--quiet case-views__button";
  const button = govuk ? "govuk-button govuk-button--secondary case-views__button" : "btn btn--quiet case-views__button";
  if (asking?.id === view.id) {
    return (
      <span className="case-views__confirm" role="group" aria-label={`Delete ${view.name}?`}>
        <span className={govuk ? "govuk-body-s" : "caption"}>
          Delete this view? Nothing on the case is deleted with it.
        </span>
        <button type="button" className={govuk ? "govuk-button govuk-button--warning case-views__button" : "btn btn--quiet case-views__button case-views__danger"} onClick={onDelete}>
          Delete view
        </button>
        <button type="button" className={button} onClick={onCancel}>
          Cancel
        </button>
      </span>
    );
  }
  return (
    <span className="case-views__actions">
      <button type="button" className={action} aria-label={`Open ${view.name}`} onClick={onOpen}>
        Open
      </button>
      {mine && !view.shared && (
        <button type="button" className={action} aria-label={`Share with the case: ${view.name}`} onClick={onShare}>
          Share with the case
        </button>
      )}
      {mine && (
        <button type="button" className={action} aria-label={`Delete ${view.name}`} onClick={onAskDelete}>
          Delete
        </button>
      )}
    </span>
  );
}
