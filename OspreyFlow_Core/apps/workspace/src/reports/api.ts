// The Reports view's calls (`06_DECISIONS.md` ADR-111): the case's figures and the feed. The shape
// is the generated one, so a change on the server is a type error here, never a silent drift.
import type { ReportFigures, ReportLimitExceeded } from "../../../../packages/schemas/generated";

export interface ReportsApi {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

function caseUrl(api: ReportsApi, path: string): string {
  return `${api.apiBaseUrl}/v1/investigations/${encodeURIComponent(api.investigationId)}/${path}`;
}

const NUMBER = new Intl.NumberFormat("en-GB");

/** A refusal, said in words — never a bare status. */
async function failure(response: Response): Promise<Error> {
  const body = (await response.json().catch(() => ({}))) as Partial<ReportLimitExceeded> & { error?: string };
  if (body.error === "limit_exceeded" && body.cap !== undefined && body.would_be !== undefined) {
    const what = body.cap_kind === "customers" ? "customers" : "alerts";
    return new Error(
      `This report would count ${NUMBER.format(body.would_be)} ${what}, past its limit of ` +
        `${NUMBER.format(body.cap)}. Choose a shorter period.`,
    );
  }
  if (response.status === 404) return new Error("This case is not one you can open.");
  return new Error(`The report could not be read (${response.status}).`);
}

export async function fetchReport(api: ReportsApi, weeks: number): Promise<ReportFigures> {
  const response = await fetch(caseUrl(api, `reports?weeks=${weeks}`), {
    headers: { Authorization: `Bearer ${api.bearerToken}` },
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as ReportFigures;
}

/** The feed as CSV, the file a dashboard would pull — each read is in the export ledger. */
export async function fetchFeedCsv(api: ReportsApi, weeks: number): Promise<Blob> {
  const response = await fetch(caseUrl(api, `reports/feed?weeks=${weeks}&format=csv`), {
    headers: { Authorization: `Bearer ${api.bearerToken}` },
  });
  if (!response.ok) throw await failure(response);
  return response.blob();
}
