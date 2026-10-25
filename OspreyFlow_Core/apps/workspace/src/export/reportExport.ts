// Report export — Phase 8 Stage 4h, `02_GLASS_FRONTEND.md` §10.1 ("Report — a self-contained
// HTML document... assembles the investigation's judgement/gap/assumption content with their own
// cited evidence inline, styled against `design/tokens.css`'s light theme — chosen over a PDF
// pipeline deliberately so this build does not need to own a PDF-rendering dependency, printable
// to PDF by the recipient at their own discretion") and §10.3 (the mark carried both visibly, as
// a header/footer stamp, and as an embedded structured field).
//
// Every judgement/gap/assumption passed in is rendered — no cap, no slice. Never truncating a
// result silently is satisfied here by construction rather than by a
// typed `limit_exceeded` escape hatch: unlike a working-set query, a report assembles a bounded,
// already-fetched list the caller chose (via the same handling gate `ExportPanel.tsx` already
// applies before this function is ever called), so there is no unbounded server-side result to
// cap in the first place.
import type { Assumption, IntelligenceGap, Judgement } from "../../../../packages/schemas/generated";
import type { Yardstick } from "../assessment/api";
import { manifestSentence, type ExportManifest, type ExportMark } from "./api";

export interface ReportArtefactInput {
  judgements: Judgement[];
  gaps: IntelligenceGap[];
  assumptions: Assumption[];
  yardstick: Yardstick;
  mark: ExportMark;
  manifest: ExportManifest;
  /** The case's name, for the title and heading; the id when it is not known. */
  caseName?: string;
  /** How a cited node is named — as the canvas names it. Absent: by its id. A reader of the
   * report has neither the canvas nor the ids' meaning (9 October 2026). */
  citationLabel?: (id: string) => string;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** A judgement's probability band, resolved against the yardstick's own bands — the "cited
 * evidence inline" requirement extended to the judgement's own scale, not just its citations,
 * since a bare band name ("B4") means nothing without the yardstick that defines it. */
function bandLabel(yardstick: Yardstick, band: string): string {
  const found = yardstick.bands.find((b) => b.label === band);
  return found ? `${found.label} (${found.lower}–${found.upper})` : band;
}

function citationsHtml(ids: readonly string[], citationLabel: (id: string) => string): string {
  return ids
    .map((id) => `<span class="citation" data-id="${escapeHtml(id)}">${escapeHtml(citationLabel(id))}</span>`)
    .join(", ");
}

function renderJudgement(
  judgement: Judgement,
  yardstick: Yardstick,
  citationLabel: (id: string) => string,
): string {
  const supporting = judgement.supporting ?? [];
  const contradicting = judgement.contradicting ?? [];
  return `
    <article class="judgement">
      <p class="statement">${escapeHtml(judgement.statement)}</p>
      <p class="meta">
        <span class="band">${escapeHtml(bandLabel(yardstick, judgement.probability_band))}</span>
        · <span class="author">${escapeHtml(judgement.author_name ?? judgement.author)}</span>
        · <span class="value">${escapeHtml(judgement.created_at)}</span>
      </p>
      ${
        supporting.length > 0
          ? `<p class="citations"><strong>Supporting:</strong> ${citationsHtml(supporting, citationLabel)}</p>`
          : ""
      }
      ${
        contradicting.length > 0
          ? `<p class="citations"><strong>Contradicting:</strong> ${citationsHtml(contradicting, citationLabel)}</p>`
          : ""
      }
    </article>`;
}

function renderGap(gap: IntelligenceGap): string {
  return `
    <article class="gap">
      <p class="statement">${escapeHtml(gap.question)}</p>
      <p class="meta">
        <span class="status">${escapeHtml(gap.status ?? "open")}</span>
        · <span class="author">${escapeHtml(gap.raised_by_name ?? gap.raised_by)}</span>
        · <span class="value">${escapeHtml(gap.created_at)}</span>
      </p>
    </article>`;
}

function renderAssumption(assumption: Assumption): string {
  return `
    <article class="assumption">
      <p class="statement">${escapeHtml(assumption.statement)}</p>
      <p class="meta"><strong>If false:</strong> ${escapeHtml(assumption.if_false_impact)}</p>
      <p class="meta"><span class="value">${escapeHtml(assumption.created_at)}</span></p>
    </article>`;
}

/** The mark's own fields as HTML data attributes on the header/footer stamp — the "visible"
 * half of §10.3's "carried both visibly and as an embedded structured field" requirement. */
function markStampHtml(mark: ExportMark): string {
  return `${escapeHtml(mark.osprey_mark)} · ${escapeHtml(mark.investigation_id)} · ${escapeHtml(mark.handling_level)} · ${escapeHtml(mark.exported_at)}`;
}

function manifestHtml(manifest: ExportManifest): string {
  const sentence = manifestSentence(manifest);
  return sentence === null ? "" : `<p class="manifest">${escapeHtml(sentence)}</p>`;
}

/** Pure: assembles a self-contained HTML document — every style inline, no external asset, no
 * network request the recipient's own browser would need to make to render it correctly. Styled
 * against `spec/design/tokens.css`'s own light-theme ramp (`[data-theme="light"]`), the theme
 * that file itself names for print/report use, values copied verbatim rather than linked, since a
 * standalone document cannot depend on this repo's own stylesheet still existing at read time. */
export function buildReportArtefact(input: ReportArtefactInput): string {
  const { judgements, gaps, assumptions, yardstick, mark, manifest } = input;
  const caseName = input.caseName ?? mark.investigation_id;
  const citationLabel = input.citationLabel ?? ((id: string) => id);
  const stamp = markStampHtml(mark);
  const markField = JSON.stringify(mark);

  return `<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8" />
<title>OspreyFlow intelligence report — ${escapeHtml(caseName)}</title>
<meta name="osprey-export-mark" content='${markField.replace(/'/g, "&#39;")}' />
<script type="application/json" id="osprey-export-mark">${markField}</script>
<style>
  :root {
    --n0:#ffffff; --n1:#f7fbfc; --n2:#f1f4f5; --n3:#e8eced;
    --n4:#dde0e1; --n6:#bbbebf; --n7:#a2a5a6; --n9:#66696a; --n10:#4b4e4e; --n11:#191b1c;
    --brass:#8a6318; --border:#bbbebf; --border-strong:#a2a5a6;
    --surface-app:var(--n1); --surface-panel:var(--n2);
    --text-primary:var(--n11); --text-secondary:var(--n10); --text-tertiary:var(--n9);
    --ui:'Atkinson Hyperlegible Next','Atkinson Hyperlegible',system-ui,sans-serif;
    --mono:'IBM Plex Mono',ui-monospace,monospace;
  }
  html, body { margin:0; padding:0; }
  body {
    background: var(--surface-app);
    color: var(--text-primary);
    font-family: var(--ui);
    font-size: 14px;
    line-height: 20px;
    padding: 32px;
    max-width: 800px;
    margin: 0 auto;
  }
  .value { font-family: var(--mono); font-variant-numeric: tabular-nums; }
  header.osprey-stamp, footer.osprey-stamp {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-tertiary);
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
    margin-bottom: 24px;
  }
  footer.osprey-stamp { border-bottom: none; border-top: 1px solid var(--border); margin-top: 32px; padding-top: 8px; margin-bottom: 0; }
  h1 { font-size: 23px; line-height: 30px; font-weight: 700; }
  h2 { font-size: 19px; line-height: 26px; font-weight: 600; margin-top: 32px; }
  article { background: var(--surface-panel); border: 1px solid var(--border); border-radius: 4px; padding: 12px; margin-bottom: 12px; }
  .statement { font-weight: 600; margin-bottom: 4px; }
  .meta, .citations, .manifest { color: var(--text-secondary); font-size: 13px; }
</style>
</head>
<body>
<header class="osprey-stamp">${stamp}</header>
<h1>Intelligence report — ${escapeHtml(caseName)}</h1>
${manifestHtml(manifest)}
<h2>Judgements</h2>
${judgements.length > 0 ? judgements.map((j) => renderJudgement(j, yardstick, citationLabel)).join("\n") : "<p>No judgements recorded.</p>"}
<h2>Intelligence gaps</h2>
${gaps.length > 0 ? gaps.map(renderGap).join("\n") : "<p>No gaps recorded.</p>"}
<h2>Assumptions</h2>
${assumptions.length > 0 ? assumptions.map(renderAssumption).join("\n") : "<p>No assumptions recorded.</p>"}
<footer class="osprey-stamp">${stamp}</footer>
</body>
</html>
`;
}
