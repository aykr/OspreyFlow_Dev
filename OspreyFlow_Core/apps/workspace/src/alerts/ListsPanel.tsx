// The Monitoring place's Lists tab (`06_DECISIONS.md` ADR-133 decision 4, stage (c)): each screening
// list the deployment subscribes to — its connector, version, number of entries, last update, licence,
// and why its last refresh failed, in words. Whoever may load screening lists (an administrator or a
// data engineer, ADR-112's `load_screening_lists`) also subscribes to a list, refreshes one, and reads
// what each refresh changed, and what it re-screened and raised in their own unit alone (the owner's
// answer of 1 November 2026: the Conduit's store counts the reader's unit, rule 7); everyone else reads
// the lists alone. The Conduit refuses whatever a stale view offers anyway.
import { useCallback, useEffect, useState } from "react";
import type {
  ScreeningLists,
  ScreeningListsOverview,
  ScreeningListStatus,
  ScreeningSubscriptionInput,
} from "../../../../packages/schemas/generated";
import {
  listScreeningLists,
  manageScreeningLists,
  type ListsApi,
} from "./api";
import { when } from "./names";

/** ADR-133 stage (d): a list's refresh schedule in words, or that it is refreshed by hand. */
export function scheduleState(list: ScreeningListStatus): string {
  if (!list.schedule_words) return "By hand only";
  return `Refreshed ${list.schedule_words}${list.next_refresh ? `; next ${when(list.next_refresh)}` : ""}`;
}

type Source = ScreeningSubscriptionInput["source"];

/** Each connector by the list it reads. */
export const CONNECTORS: Record<Source, string> = {
  ofac_sdn: "OFAC SDN list (US Treasury)",
  ofsi_consolidated: "HM Treasury OFSI consolidated list (closed 28 January 2026)",
  un_consolidated: "UN Security Council consolidated list",
  eu_consolidated: "EU consolidated financial sanctions list",
  opensanctions: "OpenSanctions (FollowTheMoney entities)",
  uk_sanctions_list: "UK Sanctions List (FCDO)",
};

/** ADR-133 Amendment 6: the connectors whose publisher has closed the list they read, with the words
 * the Conduit says beside such a list (`screening_refresh.CLOSED_LISTS`), held in step by
 * `test_the_glass_says_the_same_closed_list_words_as_the_conduit`. The subscribe form says it before
 * any list exists. */
export const CLOSED_LISTS: Partial<Record<Source, string>> = {
  ofsi_consolidated:
    "this connector reads a closed list: the OFSI Consolidated List closed on 28 January 2026 and is no longer updated, and the FCDO's UK Sanctions List is now the only source of UK designations",
};

/** The owner's answer of 1 November 2026 (ADR-133 Amendment 3): the connectors whose licence for a
 * customer's screening is not confirmed, each with the reason. They read OspreyFlow's synthetic lists
 * only; the Conduit refuses a real one. The words are the Conduit's own (`screening_refresh.
 * LICENCE_NOT_CONFIRMED`), held in step by `test_the_glass_says_the_same_licence_reasons_as_the_conduit`;
 * a list row says the reason the Conduit sends with it. */
export const LICENCE_NOT_CONFIRMED: Partial<Record<Source, string>> = {
  un_consolidated:
    "no open licence was found for the UN consolidated list, and the UN's general terms allow personal, non-commercial use only; its terms are to be confirmed with the UN",
  opensanctions:
    "OpenSanctions is CC BY-NC 4.0, and screening in a business is commercial use, which needs OpenSanctions' own data licence",
};

/** A list's state in words: never read, failing, or read at its version. */
export function listState(list: ScreeningListStatus): string {
  if (list.failure) return list.failure;
  if (!list.version) return "Not yet read: it is refreshed in the Ingest Studio's Sources.";
  return "Up to date with its last refresh.";
}

export interface ListsPanelProps extends ListsApi {
  /** ADR-112: holds `load_screening_lists`. */
  canManage: boolean;
}

export function ListsPanel(props: ListsPanelProps) {
  const { apiBaseUrl, bearerToken, canManage } = props;
  // The lists from either route; the refreshes from the administrator's alone (rule 7).
  const [found, setFound] = useState<Pick<ScreeningListsOverview, "lists"> | null>(null);
  const [refreshes, setRefreshes] = useState<ScreeningLists["updates"]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  const reload = useCallback(() => {
    const api = { apiBaseUrl, bearerToken };
    const read: Promise<Pick<ScreeningListsOverview, "lists">> = canManage
      ? manageScreeningLists(api).then((managed) => {
          setRefreshes(managed.updates);
          return managed;
        })
      : listScreeningLists(api);
    read.then(setFound).catch((e: Error) => setProblem(e.message));
  }, [apiBaseUrl, bearerToken, canManage]);
  useEffect(reload, [reload]);

  const lists = found?.lists ?? [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16)" }}>
      <section aria-label="Screening lists" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h3 className="value" style={{ margin: 0 }}>
          Screening lists
        </h3>
        <p className="label" style={{ margin: 0 }}>
          Each list is read through its connector from a file in the ingest folder. A new version re-screens
          every customer against the entries that changed, and raises an alert for each new match — a
          suggestion for a person to confirm, never a finding.
        </p>
        {problem && (
          <p role="alert" style={{ color: "var(--error)", margin: 0 }}>
            {problem}
          </p>
        )}
        {found !== null && lists.length === 0 && <p className="label">No screening list is subscribed yet.</p>}
        {lists.length > 0 && (
          <table className="table" aria-label="Screening lists and their versions">
            <thead>
              <tr>
                <th>List</th>
                <th>Version</th>
                <th style={{ textAlign: "right" }}>Entries</th>
                <th>Last update</th>
                <th>State</th>
                <th>Schedule</th>
              </tr>
            </thead>
            <tbody>
              {lists.map((list) => (
                <tr key={list.list_name}>
                  <td>
                    <span className="value">{list.list_name}</span>
                    <br />
                    <span className="label">
                      {CONNECTORS[list.source]}
                      {list.synthetic ? " · synthetic" : list.dataset ? ` · real data (${list.dataset})` : ""}
                    </span>
                    <br />
                    <span className="label">Licence: {list.licence}</span>
                    {list.closed_note && (
                      <>
                        <br />
                        <span className="label" style={{ fontWeight: 600 }}>
                          {`Closed list: ${list.closed_note}.`}
                        </span>
                      </>
                    )}
                    {list.licence_confirmed === false && (
                      <>
                        <br />
                        <span className="label" style={{ fontWeight: 600 }}>
                          {`Licence not confirmed: ${list.licence_note ?? "its terms are to be confirmed"}. Synthetic lists only.`}
                        </span>
                      </>
                    )}
                  </td>
                  <td>{list.version ?? "—"}</td>
                  <td style={{ textAlign: "right" }}>{(list.entries ?? 0).toLocaleString("en-GB")}</td>
                  <td>{list.updated_at ? when(list.updated_at) : "—"}</td>
                  <td style={list.failure ? { color: "var(--error)" } : undefined}>{listState(list)}</td>
                  <td>{scheduleState(list)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {/* ADR-133 Amendment 9 (the owner's ruling of 9 November 2026; L2.11's carry): lists are the
          Studio's now, imported, mapped and refreshed in Sources. This tab reads them, and no longer
          adds, imports, refreshes or schedules one; it goes once rules and re-screening read the
          Studio's lists. */}
      <p className="label" style={{ margin: 0 }}>
        Screening lists are imported, mapped and refreshed in the Ingest Studio&apos;s Sources. This tab shows them; it no longer adds or refreshes one.
      </p>
      {canManage && <Refreshes updates={refreshes} />}
    </div>
  );
}

function Refreshes({ updates }: { updates: ScreeningLists["updates"] }) {
  return (
    <section aria-label="Latest refreshes" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="value" style={{ margin: 0 }}>
        Latest refreshes
      </h3>
      <p className="label" style={{ margin: 0 }}>
        Customers re-screened and alerts raised are counted in your own unit only.
      </p>
      {updates.length === 0 ? (
        <p className="label" style={{ margin: 0 }}>
          No list has been refreshed yet.
        </p>
      ) : (
        <ul aria-label="Refreshes, newest first" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {updates.map((u) => (
            <li key={u.id} style={{ borderBottom: "1px solid var(--border-subtle)", padding: "var(--sp-4) 0" }}>
              <span className="value">
                {u.list_name} · {when(u.at)}
                {u.trigger === "schedule" ? " · on its schedule" : ""}
              </span>
              <br />
              <span className="label" style={u.outcome === "failed" || u.outcome === "refused" ? { color: "var(--error)" } : undefined}>
                {u.words}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
