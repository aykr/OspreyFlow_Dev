// Every jsdom test starts in a desktop-sized window (1440px): jsdom's own default (1024) is narrower
// than the workspace's docking breakpoint (1200, DESIGN.md v0.3 §5a, ADR-115 E4), which would put
// every test in the narrow layout by accident. A test of the narrow layout sets its own width.
if (typeof window !== "undefined") {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 1440 });
}
