// ADR-114 Amendment 42, in a real browser: Chromium answers the key on one name only (Playwright's
// httpCredentials, limited to that origin), then visits the other two. Run by chromium_onepass.py.
import { createRequire } from "node:module";
const require = createRequire(new URL("../../../../../OspreyFlow_Core/package.json", import.meta.url));
const { chromium } = require("@playwright/test");
const [port, host, user, key] = process.argv.slice(2);
const names = [host, `id.${host}`, `bi.${host}`];
const browser = await chromium.launch({ args: [`--host-resolver-rules=MAP *.gate.localhost 127.0.0.1`] });
for (const first of names) {
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    httpCredentials: { username: user, password: key, origin: `https://${first}:${port}` },
  });
  const page = await context.newPage();
  const statuses = [];
  for (const name of [first, ...names.filter((n) => n !== first)]) {
    const answer = await page.goto(`https://${name}:${port}/`);
    statuses.push(`${name}=${answer.status()}`);
  }
  const cookies = (await context.cookies()).filter((c) => c.name === "osprey_pass");
  console.log(`answered on ${first}: ${statuses.join(" ")}; pass cookies kept: ${cookies.map((c) => c.domain).join(", ")}`);
  await context.close();
}
const none = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await none.newPage();
const refused = [];
for (const name of names) refused.push(`${name}=${(await page.goto(`https://${name}:${port}/`)).status()}`);
console.log(`no key given: ${refused.join(" ")}`);
await browser.close();
