// Where a not-yet-accepted finding sits in the shown text (ADR-098 Amendment 1): its locator's
// `char span start-end`, taken only when the words at that place hash to the candidate's own
// `excerpt_hash` — the same "a locator never points at something else" check the server makes
// (`services/api/document_reader.py`). A span that fails it, falls outside the shown text (the
// reader shows the first 4,000 characters), or overlaps an earlier one is left undrawn; its list
// row still shows the finding.
import type { EmailCandidate } from "../inspector/linkEventsApi";

export interface PendingSpan {
  start: number;
  end: number;
  entity_type: string;
}

const CHAR_SPAN = /^char span (\d+)-(\d+)$/;

async function sha256Hex(words: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(words));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function pendingSpansIn(
  text: string,
  candidates: readonly EmailCandidate[],
): Promise<PendingSpan[]> {
  const located: PendingSpan[] = [];
  for (const candidate of candidates) {
    if (candidate.status !== "pending" || !candidate.locator || !candidate.excerpt_hash) continue;
    const match = CHAR_SPAN.exec(candidate.locator);
    if (!match) continue;
    const start = Number(match[1]);
    const end = Number(match[2]);
    if (start < 0 || end <= start || end > text.length) continue;
    if ((await sha256Hex(text.slice(start, end))) !== candidate.excerpt_hash) continue;
    located.push({ start, end, entity_type: candidate.entity_type });
  }
  located.sort((a, b) => a.start - b.start);
  const spans: PendingSpan[] = [];
  let cursor = 0;
  for (const span of located) {
    if (span.start >= cursor) {
      spans.push(span);
      cursor = span.end;
    }
  }
  return spans;
}
