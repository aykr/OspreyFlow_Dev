// *Saved views* (ADR-144 decisions 3 and 5; ADR-145 Amendment 17): the case's views this reader may see, their own
// and those shared with the case, each opened from its row. Only a view's creator is offered *Share
// with the case* (while it is private) and *Delete* (asked once: deleting a view deletes nothing on
// the case). Under the GOV.UK brand it is a GOV.UK summary list with a *Private* or *Shared* tag
// (decision 7). It starts with the whole case, marked *Open now* while no saved view is open; the saved view open now
// is marked so and offers no *Open*; a view saved under the Glass's default name says, under it, its first item as
// the Conduit names it for this reader (`first_item`) and when it was saved (the owner's exception, 14 November 2026).
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
  /** The view open now, if one is, marked "Open now"; with none, the whole case is. */
  openViewId?: string | null;
  /** The whole case's *Open*, offered while a saved view is open: what the strip's *Back to the whole case* does
   * (the App's). Without it, the whole case is listed and offers no *Open*. */
  onOpenWholeCase?: () => void;
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

/** The name the Glass gives a view of the selection by default (`GlassCanvas`'s `defaultViewName`). */
const DEFAULT_NAME = /^Selection of [\d,]+ nodes?$/;
const SAVED_AT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });

/** Under a view saved with the default name: its first item, as this reader may see it, and when it was saved. */
function toldApart(view: CaseView): string | null {
  if (!DEFAULT_NAME.test(view.name)) return null;
  const when = SAVED_AT.format(new Date(view.created_at));
  return view.first_item ? `${view.first_item} · saved ${when}` : `Saved ${when}`;
}

export function ViewsPanel({ apiBaseUrl, bearerToken, caseId, me, openViewId = null, onOpenWholeCase, onOpen, onDeleted, refreshKey = 0, takeFocus = false }: ViewsPanelProps) {
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
      Saved views in this case
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
        <dl className="govuk-summary-list govuk-summary-list--no-border" aria-label="Saved views">
          <div className="govuk-summary-list__row" data-view-id="whole-case">
            <dt className="govuk-summary-list__key">The whole case</dt>
            <dd className="govuk-summary-list__value">
              {openViewId === null && <strong className="govuk-tag govuk-tag--blue">Open now</strong>}
            </dd>
            <dd className="govuk-summary-list__actions">
              {openViewId !== null && onOpenWholeCase && <WholeCaseOpen govuk onOpen={onOpenWholeCase} />}
            </dd>
          </div>
          {views.map((view) => (
            <div key={view.id} className="govuk-summary-list__row" data-view-id={view.id}>
              <dt className="govuk-summary-list__key">
                {view.name}
                {toldApart(view) && <span className="govuk-body-s case-views__apart">{toldApart(view)}</span>}
              </dt>
              <dd className="govuk-summary-list__value">
                <strong className={view.shared ? "govuk-tag govuk-tag--green" : "govuk-tag govuk-tag--grey"}>
                  {view.shared ? "Shared" : "Private"}
                </strong>
                {view.id === openViewId && <strong className="govuk-tag govuk-tag--blue case-views__open-now">Open now</strong>}
              </dd>
              <dd className="govuk-summary-list__actions">
                <Actions
                  govuk
                  isOpen={view.id === openViewId}
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
        <ul aria-label="Saved views" className="case-views__list">
          <li className="case-views__row" data-view-id="whole-case">
            <span className="case-views__line">
              <span className="case-views__name">The whole case</span>
              {openViewId === null && <span className="view-tag view-tag--open">Open now</span>}
            </span>
            {openViewId !== null && onOpenWholeCase && <WholeCaseOpen govuk={false} onOpen={onOpenWholeCase} />}
          </li>
          {views.map((view) => (
            <li key={view.id} className="case-views__row" data-view-id={view.id}>
              <span className="case-views__line">
                <span className="case-views__name" title={view.name}>
                  {view.name}
                </span>
                <span className={view.shared ? "view-tag view-tag--shared" : "view-tag"}>{view.shared ? "Shared" : "Private"}</span>
                {view.id === openViewId && <span className="view-tag view-tag--open">Open now</span>}
              </span>
              {toldApart(view) && <span className="caption case-views__apart">{toldApart(view)}</span>}
              <Actions
                govuk={false}
                isOpen={view.id === openViewId}
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
  /** The saved view open now: it offers no *Open* (ADR-145 Amendment 17). */
  isOpen?: boolean;
  view: CaseView;
  mine: boolean;
  asking: Asking;
  onOpen: () => void;
  onShare: () => void;
  onAskDelete: () => void;
  onDelete: () => void;
  onCancel: () => void;
}

/** The whole case's *Open*, while a saved view is open: the strip's *Back to the whole case*, from the list. */
function WholeCaseOpen({ govuk, onOpen }: { govuk: boolean; onOpen: () => void }) {
  return (
    <span className="case-views__actions">
      <button type="button" className={govuk ? "govuk-link case-views__link" : "btn btn--quiet case-views__button"} aria-label="Open the whole case" onClick={onOpen}>
        Open
      </button>
    </span>
  );
}

function Actions({ govuk, isOpen = false, view, mine, asking, onOpen, onShare, onAskDelete, onDelete, onCancel }: ActionsProps) {
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
      {!isOpen && (
        <button type="button" className={action} aria-label={`Open ${view.name}`} onClick={onOpen}>
          Open
        </button>
      )}
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
