// The trend calls (ADR-113 stage 5): the builder's options, a preview, and the saved trends. The
// shapes are the generated ones; a refusal is said in words, with its choices.
import type {
  TrendDefinition,
  TrendDefinitionInput,
  TrendFigures,
  TrendLimitExceededBody,
  TrendOptions,
} from "../../../../packages/schemas/generated";
import type { ReportsApi } from "./api";
import { fieldOf, refusal, send, type Reply } from "./caseHttp";

function trendFailure(reply: Reply, what: string): Error {
  if (reply.status === 409 && fieldOf(reply.body, "error") === "limit_exceeded") {
    const body = reply.body as TrendLimitExceededBody;
    return new Error(
      `This trend would have ${body.would_be} ${body.cap_kind}, past its limit of ${body.cap}. ` +
        "Choose a shorter period, a monthly interval, or fewer series.",
    );
  }
  return refusal(reply, what);
}

export async function fetchTrendOptions(api: ReportsApi): Promise<TrendOptions> {
  const reply = await send(api, "GET", "trends/options");
  if (!reply.ok) throw trendFailure(reply, "read what a trend can be built from");
  return reply.body as TrendOptions;
}

export async function previewTrend(api: ReportsApi, definition: TrendDefinitionInput): Promise<TrendFigures> {
  const reply = await send(api, "POST", "trends/preview", definition);
  if (!reply.ok) throw trendFailure(reply, "preview this trend");
  return reply.body as TrendFigures;
}

export async function saveTrend(api: ReportsApi, definition: TrendDefinitionInput): Promise<TrendDefinition> {
  const reply = await send(api, "POST", "trends", definition);
  if (!reply.ok) throw trendFailure(reply, "save a trend");
  return reply.body as TrendDefinition;
}

export async function listTrends(api: ReportsApi): Promise<TrendDefinition[]> {
  const reply = await send(api, "GET", "trends");
  if (!reply.ok) throw trendFailure(reply, "read the saved trends");
  return reply.body as TrendDefinition[];
}

export async function fetchTrendFigures(api: ReportsApi, trendId: string): Promise<TrendFigures> {
  const reply = await send(api, "GET", `trends/${encodeURIComponent(trendId)}/figures`);
  if (!reply.ok) throw trendFailure(reply, "draw this trend");
  return reply.body as TrendFigures;
}

export async function deleteTrend(api: ReportsApi, trendId: string): Promise<void> {
  const reply = await send(api, "DELETE", `trends/${encodeURIComponent(trendId)}`);
  if (!reply.ok) throw trendFailure(reply, "delete this trend");
}
