| 2026-11-10 | Build (T3b) | T3's contrast probe had carried limits:
- three points a line box;
- SVG ink read from `color`;
- an SVG label always unmeasurable over its own box;
- inert and outer shadows unseen;
- a white page assumed;
- an unchecked findings file.

My first T3b build (6e18acc) made SVG shapes under a label's words into surfaces, and merger-c2's review found three silent passes there:
- the shape laid under the words' own opacity;
- only `fill` read, so strokes, lines and images were taken as fills;
- the shape's filter, mask and group opacity skipped.

It also found the shadow reach built once, before the probe scrolled, and a point cap that thinned the sampling silently. Two of my browser plants first changed the page itself, so axe decided them before the gate saw them. Once a text was covered, axe gave `bgOverlap` instead of "partly obscured", so decision 3's own reason could not be planted under a cover. | The probe samples every 8px along a node's own words, lifts pointer events and `inert`, and reads the browser's `Canvas` and SVG `fill`. The under-path is a fail-closed allowlist: a plain filled shape, judged with `isPointInFill` and `isPointInStroke` in its own coordinates and laid at the ancestor it shares with the words. Past 600 points a node is unmeasurable. Each plant was made at the real call site, with a control where a branch needed proving. A plant that moves the page is redone, not counted. | `src/color/textContrast.test.ts` (28; V1 to V5, W1, W2 red; V3′ honestly green); browser plants Q1, Q3 to Q7, MP1 to MP3 and Q7′, with controls for the sparse sampling and inert (`process/lanes/rules-b/t3b/RED_RECORD.md`). Show as BPMN's 12 listings off; 78 looks and 140 findings listed. Hash: recorded at merge. |
