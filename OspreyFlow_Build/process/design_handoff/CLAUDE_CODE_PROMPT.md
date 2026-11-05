# Prompt for Claude Code

Copy everything below the line into Claude Code, run from the root of the OspreyFlow repository. Before you start, unzip the handoff folder to `design/handoff/` in the repo.

---

You're implementing a design handoff for OspreyFlow. The designs are in `design/handoff/`. Read `design/handoff/README.md` in full before writing any code.

## Ground rules

1. `design/handoff/DESIGN.md` is the binding design contract. Copy it to the repo root as `DESIGN.md`, and use only the colours, fonts, sizes, spacing steps and radii it declares.
   - If you need a value that isn't in it, stop and ask me. Don't invent one.
   - Map its tokens to our existing theming layer. Keep the names it uses, such as `--surface-panel` and `--brass`.
2. The `.dc.html` files are **design references**, not code to ship. Open them in a browser to see the intended look and behaviour, then rebuild them in our stack using our existing component patterns.
   - Don't copy their inline styles.
   - Don't import `support.js` or `image-slot.js` into the product.
3. Before you build anything, find where each part of the product lives in our codebase. Then reply with a table mapping each design file to the route, component or file you'll change, and wait for me to confirm it.

## Which file is for which part of the product

| Design file | Product surface | Who sees it | Likely location (confirm) |
|---|---|---|---|
| `OspreyFlow Welcome.dc.html` | Public welcome and sign-in page, before authentication | Everyone | Unauthenticated landing route and sign-in component |
| `OspreyFlow Home.dc.html` | Home after sign-in: the app launcher for Glass, Ingest Studio and Admin console | Signed-in users, filtered by role | The post-login route that currently shows the three app buttons |
| `OspreyFlow Workspace.dc.html` | Glass analyst workspace: graph canvas, Inspector, Query, Case, timeline | Analysts | Glass app shell and graph view |
| `Workspace Design Review.md` | Acceptance checks for the Glass workspace refactor | n/a | Use as the definition of done for the workspace |
| `DESIGN.md` | Tokens and rules for every surface, including Ingest Studio and Admin | n/a | Repo root |
| `assets/screen-*.jpg` | Screenshots used on the welcome page only | n/a | Static assets for the welcome page |

Ingest Studio and the Admin console have no screen designs in this package. Don't redesign them. Only make sure they pick up the shared tokens, the marking strip and the header from `DESIGN.md`.

## Things to get right

- **Sign-in and identity.** Our architecture says credentials are typed only at the identity provider (OIDC code flow with PKCE).
  - Wire "Continue with organisation sign-in" to that flow.
  - If the email-or-username form can't post directly to the identity provider, tell me before you build it. It may belong in the identity provider's own hosted login theme rather than in our app.
  - Keep the validation messages and the three card states (Sign in, Reset your password, Check your email) exactly as written in the README.
- **Roles on the home page.** Build the launcher from the session's real roles and rights. Don't hard-code it.
  - A panel for an app the user can't use shows the "You need the … role" message.
  - The "Needs your attention" rows come from real sources: the alert queue, held rows and report-sync status. If an endpoint doesn't exist, use a typed stub and list it for me.
- **Protective marking.** The marking strip comes from deployment config (`OFFICIAL`, `OFFICIAL-SENSITIVE` or none) and appears on every surface.
- **Brass.** Use it only for the single primary action in a region, for focus rings, and for the selected-node ring. Active tabs and views must not use brass.
- **Mono.** Use the mono font for every identifier, timestamp, count, hash and key cap.
- **Accessibility.**
  - Every interactive element gets a visible focus ring, and touch targets are at least 24×24px.
  - The graph canvas is fully operable by keyboard: `/` focuses search, the arrow keys move between nodes, `Enter` opens the Inspector, `Esc` clears the selection, and `?` opens the welcome panel.
  - `prefers-reduced-motion` must be respected.
- **Responsive behaviour.** Match the breakpoints in the README. In particular, below a 1200px viewport, Glass's right panel becomes an overlay that starts closed.

## Order of work (one PR each)

1. **Tokens.** `DESIGN.md` at the root, the token layer for both themes, fonts (Atkinson Hyperlegible Next and IBM Plex Mono), and the marking strip and header shared by every surface.
2. **Welcome and sign-in page.**
3. **Home page after sign-in**, with role gating.
4. **Glass workspace shell.** Work through the P0 and P1 items in `Workspace Design Review.md`, then match `OspreyFlow Workspace.dc.html`.

## After each PR

- Run `npx impeccable detect src/`. Report every finding that isn't listed as an exception in `DESIGN.md` §9.
- Give me a short list of anything you couldn't match, and why.
- Don't mark anything as done until you've opened it in both dark and light themes, at 1440px and at 924px wide.
