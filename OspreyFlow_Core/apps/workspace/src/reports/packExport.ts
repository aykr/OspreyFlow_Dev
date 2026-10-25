// A pack exported as a document the browser prints to PDF (ADR-113 stage 5). No PDF library: the
// manifest the Conduit returns becomes a self-contained, print-styled page, and the person saves
// the PDF from the browser's own print dialogue. Every page carries THAT item's own marking, top
// and bottom — never the pack's level — and every interpolated string is escaped.
import type { PackExport, PackItem } from "../../../../packages/schemas/generated";
import { KIND_LABEL, formatDay, formatNumber, periodKey, periodsOf, trendSentence } from "./packText";
import { manifestSentence } from "../export/api";

const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ESCAPES[c] ?? c);
}

// The light-theme ramp of `design/tokens.css` (`[data-theme="light"]`), restated as `reportExport.ts`
// does: a standalone print document cannot link this repository's stylesheet.
const STYLE = `
:root { --n0:#ffffff; --n7:#a2a5a6; --n9:#66696a; --n11:#191b1c; }
@page { margin: 18mm; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--n0); color: var(--n11); font: 11pt/1.45 Georgia, "Times New Roman", serif; }
.page { page-break-after: always; break-after: page; min-height: 240mm; display: flex; flex-direction: column; gap: 8mm; }
.page:last-child { page-break-after: auto; break-after: auto; }
.banner { border: 1.5pt solid var(--n11); padding: 2mm 4mm; text-align: center; font: bold 10pt Helvetica, Arial, sans-serif; letter-spacing: 0.08em; text-transform: uppercase; }
.banner-bottom { margin-top: auto; }
h1 { font-size: 24pt; margin: 20mm 0 4mm; }
h2 { font-size: 15pt; margin: 0; }
.kind { font: 9pt Helvetica, Arial, sans-serif; text-transform: uppercase; letter-spacing: 0.08em; color: var(--n9); }
.mark, .notice { margin: 0; }
.notice { border-left: 3pt solid var(--n11); padding-left: 4mm; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; }
th, td { border-bottom: 0.5pt solid var(--n7); padding: 1mm 2mm; text-align: left; }
td.num, th.num { text-align: right; }
`;

function trendTable(item: PackItem): string {
  const figures = item.trend;
  if (!figures) return "";
  const row = (period: string, series: string, value: number) =>
    `<tr><td>${escapeHtml(formatDay(period))}</td><td>${escapeHtml(series)}</td>` +
    `<td class="num">${escapeHtml(formatNumber(value))}</td></tr>`;
  const rows = periodsOf(figures)
    .map((period) => {
      const here = figures.result.points.filter((p) => periodKey(p.period_start) === period);
      return here.length === 0 ? row(period, "No events", 0) : here.map((p) => row(period, p.series ?? "", p.value)).join("");
    })
    .join("");
  return (
    `<p>${escapeHtml(trendSentence(figures))}.</p>` +
    `<p class="mark">As at ${escapeHtml(formatDay(figures.as_of))}.</p>` +
    `<table><thead><tr><th>Period starting</th><th>Series</th><th class="num">Value</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`
  );
}

function itemContent(item: PackItem): string {
  if (item.kind === "trend") return trendTable(item);
  if (item.kind === "assessment" && item.assessment) {
    return `<p>${escapeHtml(item.assessment.statement)}</p><p class="mark">Probability band: ${escapeHtml(item.assessment.probability_band)}.</p>`;
  }
  if (item.kind === "entity" && item.entity) {
    return `<p><strong>${escapeHtml(item.entity.name)}</strong> (${escapeHtml(item.entity.entity_type)})</p><p>${escapeHtml(item.entity.caption)}</p>`;
  }
  return `<p>${escapeHtml(item.note ?? "")}</p>`;
}

function itemHeading(item: PackItem): string {
  if (item.kind === "trend") return item.trend?.definition.title ?? "Trend";
  if (item.kind === "assessment") return "Assessment";
  if (item.kind === "entity") return item.entity?.name ?? "Entity";
  return "Note";
}

function itemPage(item: PackItem): string {
  const banner = `Marked ${escapeHtml(item.marking)}`;
  return (
    `<section class="page item" data-item-id="${escapeHtml(item.id)}">` +
    `<div class="banner banner-top">${banner}</div>` +
    `<div class="kind">${escapeHtml(KIND_LABEL[item.kind])}</div>` +
    `<h2>${escapeHtml(itemHeading(item))}</h2>` +
    itemContent(item) +
    `<div class="banner banner-bottom">${banner}</div>` +
    `</section>`
  );
}

/** The whole print document: a cover, then one page for each item in the manifest. */
export function packPrintHtml(manifest: PackExport): string {
  const { mark } = manifest;
  // A yes or no (ADR-124 decision 9), in the pack's own words; nothing under `omit`, where it is null.
  const withheldSentence = manifestSentence(manifest, "pack");
  // The cover is a printed page too: it carries the highest marking exported, top and bottom.
  const coverBanner = (where: "top" | "bottom") => `<div class="banner banner-${where}">Marked ${escapeHtml(mark.handling_level)}</div>`;
  const cover =
    `<section class="page cover">` +
    coverBanner("top") +
    `<h1>${escapeHtml(manifest.title)}</h1>` +
    `<p class="notice">Version ${manifest.version}, published ${escapeHtml(formatDay(manifest.published_at))} by ${escapeHtml(manifest.published_by_name ?? manifest.published_by)}</p>` +
    `<p class="notice">Exported by ${escapeHtml(mark.exported_by_name ?? mark.exported_by)} on ${escapeHtml(formatDay(mark.exported_at))}; ` +
    `handling level ${escapeHtml(mark.handling_level)}; OspreyFlow export ${escapeHtml(manifest.ledger_entry_id)}</p>` +
    (withheldSentence !== null ? `<p class="notice">${escapeHtml(withheldSentence)}</p>` : "") +
    (mark.rests_on_retracted_evidence ? `<p class="notice">This pack rests on evidence since retracted or corrected.</p>` : "") +
    coverBanner("bottom") +
    `</section>`;
  return (
    `<!doctype html><html lang="en-GB"><head><meta charset="utf-8">` +
    `<title>${escapeHtml(manifest.title)}</title><style>${STYLE}</style></head><body>` +
    cover +
    manifest.items.map(itemPage).join("") +
    `</body></html>`
  );
}

/** The default way to print: a hidden frame, written and printed, then taken away. */
export function printInFrame(html: string): void {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;width:0;height:0;border:0;visibility:hidden;";
  document.body.appendChild(frame);
  const win = frame.contentWindow;
  if (!win) {
    frame.remove();
    throw new Error("The print window could not be opened. Allow this page to print and try again.");
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
  win.addEventListener("afterprint", () => frame.remove());
  setTimeout(() => {
    win.focus();
    win.print();
  }, 0);
}
