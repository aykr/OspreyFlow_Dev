// GG2c, case 1: the working set's delta client is the package's, reached through its one public entry (the
// path `@ospreyflow/glass-shared` resolves to, `package.json`'s `exports["."]`), so a page module can hold the
// live working set without reaching into the React workspace. It drives a fake socket end to end through that
// entry, not only names the export, so a re-export of the wrong module or a stub fails here too.
import { describe, expect, it } from "vitest";

import * as pkg from "../index";
import type { SocketLike, WorkingSetDelta } from "../index";

describe("the package's public entry exports the delta client", () => {
  it("names each export the two front ends import", () => {
    expect(typeof pkg.connectDeltaClient).toBe("function");
    expect(typeof pkg.isWorkingSetDelta).toBe("function");
    expect(typeof pkg.isViewOverCap).toBe("function");
  });

  it("drives a socket through the entry: asks for a snapshot on open, then applies steps in order", () => {
    const sent: string[] = [];
    const socket: SocketLike = {
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null,
      send: (data) => sent.push(data),
      close: () => {},
    };
    const deltas: WorkingSetDelta[] = [];
    const client = pkg.connectDeltaClient(() => socket, { onDelta: (d) => deltas.push(d) });
    socket.onopen?.();
    expect(sent).toEqual([JSON.stringify({ last_acknowledged_seq: null })]);
    socket.onmessage?.({ data: JSON.stringify({ seq: 1, op: "snapshot", nodes: [], edges: [], filtered_count: 0 }) });
    socket.onmessage?.({ data: JSON.stringify({ seq: 2, op: "add", nodes: [], edges: [] }) });
    expect(deltas.map((d) => d.seq)).toEqual([1, 2]);
    expect(client.lastSeq).toBe(2);
  });
});
