import type { PageModule } from "../../server/pages.js";

/** The one throw-away page of the foundation's tests: a real `FUNCTIONS.yaml` row's id, a GET that shows a table and a POST. */
export const FIXTURE_ROWS = [
  { name: "alpha", count: 3 },
  { name: "beta", count: 5 },
];

export function fixturePage(calls: { handled: number } = { handled: 0 }): PageModule {
  return {
    id: "studio-frame",
    path: "/_fixture/page",
    methods: ["GET", "POST"],
    handler: (req, res) => {
      calls.handled += 1;
      if (req.method === "POST") {
        res.redirect(303, "/_fixture/page");
        return;
      }
      res.render("fixture-page", { rows: FIXTURE_ROWS, page: "fixture", csrfToken: req.session.auth?.csrfToken });
    },
  };
}
