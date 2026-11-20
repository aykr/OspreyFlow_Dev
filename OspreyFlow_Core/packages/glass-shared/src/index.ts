// The Glass's plain TypeScript, kept once for both front ends (ADR-152 decision 6): logic, stores, the panel
// pattern, the Conduit client, the keyboard action registry, structural types for the map and graph.
//
// It exports nothing yet. Slices PL4 B to E move the React workspace's plain leaves in, one behaviour-preserving
// change at a time (invariant I11); each adds its exports here.
//
// What it must never import, as a value or as a type (I1, I13):
//   react, react-dom, react/jsx-runtime        no React, so `pages` can use it (ADR-152 decision 1)
//   sigma, @sigma/*, maplibre-gl               the drawing libraries are bound by each front end's own modules
// Two checks hold that: `scripts/no_react_check.mjs` and `scripts/version_isolation_check.mjs` (what a bundle
// reaches) and the `no-restricted-imports` block for this folder in `eslint.config.js` (what a source file
// names, a type import included: a bundler drops a type-only import, so only the lint rule sees it).
export {};
