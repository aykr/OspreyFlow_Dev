// Prints one guide's page to PDF for `tools/docs_pdf.py` (ADR-114 Amendment 26): Playwright's
// Chromium, because the plain headless shell cannot number its pages, and a contents page needs
// the numbers it points to. Each page carries the guide's name, its version and its number; the
// PDF carries bookmarks from the headings.
//
//   node tools/print_pdf.mjs <core folder> <page.html> <out.pdf> <footer text> [chromium path]
//
// The footer has no colour of its own (CLAUDE.md: none outside the tokens, which the footer cannot
// read); it prints in the default.
import { createRequire } from "node:module";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [core, html, pdf, footer, executablePath] = process.argv.slice(2);
if (!core || !html || !pdf || footer === undefined) {
  console.error("usage: print_pdf.mjs <core> <page.html> <out.pdf> <footer> [chromium]");
  process.exit(2);
}
const { chromium } = createRequire(join(core, "package.json"))("@playwright/test");

const escaped = footer.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const browser = await chromium.launch(executablePath ? { executablePath } : {});
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(html).href, { waitUntil: "load" });
  await page.pdf({
    path: pdf,
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    outline: true,
    tagged: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate:
      '<div style="font-size:8pt;width:100%;margin:0 16mm;display:flex;justify-content:space-between">' +
      `<span>${escaped}</span><span><span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
  });
} finally {
  await browser.close();
}
