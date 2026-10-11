// Who can open this case (ADR-052 §9, the Share panel): everyone sees their own level; the case's
// Author sees who holds which level, gives an account a level and takes it away. An account is named
// by its id — a person's or a dashboard's, as the Admin area shows it (ADR-052 P3, ADR-111). The
// Conduit enforces all of it; nothing here is a control.
import { useCallback, useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { Select } from "../design/primitives/Select";
import { type CaseAccess, LEVEL_NAMES, caseAccess, grantCaseAccess, removeCaseAccess } from "./access";
import type { AccessLevel } from "./cases";

export interface CaseAccessPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

const LEVELS: AccessLevel[] = ["viewer", "editor", "author"];

export function CaseAccessPanel({ apiBaseUrl, bearerToken, investigationId }: CaseAccessPanelProps) {
  const [access, setAccess] = useState<CaseAccess | null>(null);
  const [unshared, setUnshared] = useState(false);
  const [account, setAccount] = useState("");
  const [level, setLevel] = useState<AccessLevel>("viewer");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(
    () =>
      caseAccess(apiBaseUrl, bearerToken, investigationId).then((found) => {
        setUnshared(found === null);
        setAccess(found);
      }),
    [apiBaseUrl, bearerToken, investigationId],
  );

  useEffect(() => {
    load().catch((err: unknown) => setProblem(err instanceof Error ? err.message : String(err)));
  }, [load]);

  async function act(change: () => Promise<void>): Promise<void> {
    setBusy(true);
    setProblem(null);
    try {
      await change();
      await load();
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const grants = access?.grants ? Object.entries(access.grants) : null;
  const authors = grants?.filter(([, held]) => held === "author").length ?? 0;
  const nameOf = (id: string) => access?.names?.[id];

  if (unshared) return null;
  return (
    <section aria-label="Who can open this case" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="label" style={{ margin: 0 }}>
        Who can open this case
      </h3>
      {access === null && !problem && <span className="label">Loading…</span>}
      {access && (
        <p style={{ margin: 0 }}>
          {access.your_level ? `You are its ${LEVEL_NAMES[access.your_level]}.` : "You hold no level on it."}
        </p>
      )}
      {grants && (
        <ul aria-label="Accounts with access" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
          {grants.map(([id, held]) => {
            const name = nameOf(id);
            const label = name ?? id;
            // The last Author stays: removing them would leave nobody to manage the case.
            const lastAuthor = held === "author" && authors <= 1;
            return (
              <li key={id} style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
                <span style={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>
                  {label}
                  {name && <span className="label identifier" style={{ display: "block" }}>{id}</span>}
                </span>
                <span className="label">{LEVEL_NAMES[held]}</span>
                {!lastAuthor && (
                  <Button
                    aria-label={`Remove ${label}'s access`}
                    disabled={busy}
                    onClick={() => void act(() => removeCaseAccess(apiBaseUrl, bearerToken, investigationId, id))}
                  >
                    Remove
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {grants && (
        <form
          aria-label="Give an account access"
          style={{ display: "grid", gap: "var(--sp-4)" }}
          onSubmit={(event) => {
            event.preventDefault();
            void act(async () => {
              await grantCaseAccess(apiBaseUrl, bearerToken, investigationId, account, level);
              setAccount("");
            });
          }}
        >
          <label className="label" htmlFor="case-access-account">
            Account id
          </label>
          <Input
            id="case-access-account"
            value={account}
            disabled={busy}
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => setAccount(event.target.value)}
          />
          <span className="label">A person's or a dashboard's account id, as the Admin area shows it.</span>
          <label className="label" htmlFor="case-access-level">
            Level
          </label>
          <Select
            id="case-access-level"
            value={level}
            disabled={busy}
            onChange={(event) => setLevel(event.target.value as AccessLevel)}
          >
            {LEVELS.map((option) => (
              <option key={option} value={option}>
                {LEVEL_NAMES[option]}
              </option>
            ))}
          </Select>
          <span>
            <Button type="submit" variant="primary" disabled={busy || !account.trim()}>
              Give access
            </Button>
          </span>
        </form>
      )}
      {problem && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {problem}
        </span>
      )}
    </section>
  );
}
