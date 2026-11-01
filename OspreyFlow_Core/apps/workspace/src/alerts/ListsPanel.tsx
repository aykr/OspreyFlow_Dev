// The Monitoring place's Lists tab (`06_DECISIONS.md` ADR-133 decision 4, stage (c)): each screening
// list the deployment subscribes to — its connector, version, number of entries, last update, licence,
// and why its last refresh failed, in words. Whoever may load screening lists (an administrator or a
// data engineer, ADR-112's `load_screening_lists`) also subscribes to a list, refreshes one, and reads
// what each refresh changed, re-screened and raised; everyone else reads the lists alone, since those
// counts are taken across every case in the deployment (rule 7). The Conduit refuses whatever a stale
// view offers anyway.
import { useCallback, useEffect, useState } from "react";
import type {
  ScreeningLists,
  ScreeningListsOverview,
  ScreeningListStatus,
  ScreeningSubscriptionInput,
} from "../../../../packages/schemas/generated";
import { Button, Input, Select } from "../design/primitives";
import {
  listScreeningLists,
  manageScreeningLists,
  refreshScreeningList,
  setListSchedule,
  subscribeScreeningList,
  type ListsApi,
} from "./api";
import { when } from "./names";
import { WEEKDAY_WORDS } from "./sentence";

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
};

/** A list's state in words: never read, failing, or read at its version. */
export function listState(list: ScreeningListStatus): string {
  if (list.failure) return list.failure;
  if (!list.version) return "Not yet read: refresh it to load its first version.";
  return "Up to date with its last refresh.";
}

const FIELD = { display: "grid", gap: "var(--sp-4)" } as const;

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
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

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

  const refresh = (listName: string) => {
    setProblem(null);
    setBusy(listName);
    refreshScreeningList({ apiBaseUrl, bearerToken }, listName)
      .then((update) => {
        setSaid(`${listName}: ${update.words}`);
        reload();
      })
      .catch((e: Error) => setProblem(e.message))
      .finally(() => setBusy(null));
  };

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
        {said && (
          <p role="status" className="label" style={{ margin: 0 }}>
            {said}
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
                {canManage && <th>Refresh</th>}
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
                  </td>
                  <td>{list.version ?? "—"}</td>
                  <td style={{ textAlign: "right" }}>{(list.entries ?? 0).toLocaleString("en-GB")}</td>
                  <td>{list.updated_at ? when(list.updated_at) : "—"}</td>
                  <td style={list.failure ? { color: "var(--error)" } : undefined}>{listState(list)}</td>
                  <td>{scheduleState(list)}</td>
                  {canManage && (
                    <td>
                      <Button
                        aria-label={`Refresh now: ${list.list_name}`}
                        disabled={busy !== null}
                        onClick={() => refresh(list.list_name)}
                      >
                        {busy === list.list_name ? "Refreshing…" : "Refresh now"}
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {canManage ? (
        <>
          <Refreshes updates={refreshes} />
          {lists.length > 0 && (
            <ScheduleForm
              {...props}
              lists={lists}
              onSaved={(words) => {
                setSaid(words);
                reload();
              }}
            />
          )}
          <SubscribeForm
            {...props}
            onSubscribed={(listName) => {
              setSaid(`Subscribed to “${listName}”. Refresh it to read its first version.`);
              reload();
            }}
          />
        </>
      ) : (
        <p className="label" style={{ margin: 0 }}>
          An administrator or a data engineer subscribes to a list and refreshes it.
        </p>
      )}
    </div>
  );
}

function Refreshes({ updates }: { updates: ScreeningLists["updates"] }) {
  return (
    <section aria-label="Latest refreshes" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="value" style={{ margin: 0 }}>
        Latest refreshes
      </h3>
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

function SubscribeForm(props: ListsPanelProps & { onSubscribed: (listName: string) => void }) {
  const [name, setName] = useState("");
  const [source, setSource] = useState<Source>("ofac_sdn");
  const [location, setLocation] = useState("");
  const [dataset, setDataset] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <form
      aria-label="Subscribe to a list"
      onSubmit={(e) => {
        e.preventDefault();
        setProblem(null);
        subscribeScreeningList(props, {
          list_name: name.trim(),
          source,
          location: location.trim(),
          dataset: dataset.trim() || null,
          use: "local_development",
        })
          .then((made) => {
            setName("");
            setLocation("");
            setDataset("");
            props.onSubscribed(made.list_name);
          })
          .catch((err: Error) => setProblem(err.message));
      }}
      style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}
    >
      <h3 className="value" style={{ margin: 0 }}>
        Subscribe to a list
      </h3>
      <label className="label" style={FIELD}>
        List name
        <Input aria-label="List name" value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label className="label" style={FIELD}>
        Connector
        <Select aria-label="Connector" value={source} onChange={(e) => setSource(e.target.value as Source)}>
          {(Object.keys(CONNECTORS) as Source[]).map((key) => (
            <option key={key} value={key}>
              {CONNECTORS[key]}
            </option>
          ))}
        </Select>
      </label>
      <label className="label" style={FIELD}>
        File in the ingest folder
        <Input
          aria-label="File in the ingest folder"
          placeholder="lists/SDN.CSV"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          required
        />
      </label>
      <label className="label" style={FIELD}>
        Real dataset it is (empty for one of OspreyFlow&apos;s synthetic lists)
        <Input aria-label="Real dataset" placeholder="ofac_sdn" value={dataset} onChange={(e) => setDataset(e.target.value)} />
      </label>
      <p className="label" style={{ margin: 0 }}>
        A real list loads only on a device whose own exceptions file names its dataset; check its licence first.
      </p>
      {problem && (
        <p role="alert" style={{ color: "var(--error)", margin: 0 }}>
          {problem}
        </p>
      )}
      <Button type="submit" variant="primary" disabled={!name.trim() || !location.trim()}>
        Subscribe
      </Button>
    </form>
  );
}

/** ADR-133 Amendment 3 item 4, built with stage (d): a list refreshed every day or every week at an
 * hour, as the person who sets it. Each slot is refused, in words, if they no longer may load lists. */
function ScheduleForm(props: ListsApi & { lists: ScreeningListStatus[]; onSaved: (words: string) => void }) {
  const [listName, setListName] = useState(props.lists[0]?.list_name ?? "");
  const [every, setEvery] = useState<"none" | "daily" | "weekly">("daily");
  const [weekday, setWeekday] = useState("1");
  const [hour, setHour] = useState("5");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = () => {
    setBusy(true);
    setProblem(null);
    const schedule =
      every === "none"
        ? null
        : { every, hour: Number(hour), weekday: every === "weekly" ? Number(weekday) : null };
    setListSchedule(props, listName, schedule)
      .then((status) =>
        props.onSaved(
          status.schedule_words
            ? `“${listName}” is refreshed ${status.schedule_words}, as you.`
            : `“${listName}” is refreshed by hand only.`,
        ),
      )
      .catch((e: Error) => setProblem(e.message))
      .finally(() => setBusy(false));
  };
  return (
    <section aria-label="Refresh schedule" style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}>
      <h3 className="value" style={{ margin: 0 }}>
        Refresh schedule
      </h3>
      <p className="label" style={{ margin: 0 }}>
        A scheduled refresh runs as you. If you no longer hold the right to load screening lists, each
        refresh is refused and says so in the list&apos;s refreshes; nothing is read.
      </p>
      <label className="label" style={FIELD}>
        List
        <Select aria-label="List to schedule" value={listName} onChange={(e) => setListName(e.target.value)}>
          {props.lists.map((l) => (
            <option key={l.list_name} value={l.list_name}>
              {l.list_name}
            </option>
          ))}
        </Select>
      </label>
      <label className="label" style={FIELD}>
        Refreshed
        <Select aria-label="Refreshed" value={every} onChange={(e) => setEvery(e.target.value as typeof every)}>
          <option value="none">by hand only</option>
          <option value="daily">every day</option>
          <option value="weekly">every week</option>
        </Select>
      </label>
      {every === "weekly" && (
        <label className="label" style={FIELD}>
          On
          <Select aria-label="Refresh day" value={weekday} onChange={(e) => setWeekday(e.target.value)}>
            {WEEKDAY_WORDS.map((day, i) => (
              <option key={day} value={String(i + 1)}>
                {day}
              </option>
            ))}
          </Select>
        </label>
      )}
      {every !== "none" && (
        <label className="label" style={FIELD}>
          At (Europe/London)
          <Select aria-label="Refresh hour" value={hour} onChange={(e) => setHour(e.target.value)}>
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={String(h)}>
                {`${String(h).padStart(2, "0")}:00`}
              </option>
            ))}
          </Select>
        </label>
      )}
      {problem && (
        <p role="alert" style={{ color: "var(--error)", margin: 0 }}>
          {problem}
        </p>
      )}
      <Button disabled={busy || !listName} onClick={save}>
        Save the schedule
      </Button>
    </section>
  );
}
