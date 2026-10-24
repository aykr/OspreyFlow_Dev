// ADR-124 U2b: a server that still sends a `notice` step has it dropped quietly. It is not an
// error. The server stamps it with the previous step's own number (`app.py` `seq=delta.seq`,
// `service.py` `seq=top_seq`), so it takes no place in the sequence and the next step is not
// mistaken for a gap.
import { describe, expect, it } from "vitest";

import { connectDeltaClient, type SocketLike } from "./deltaClient";
import type { WorkingSetDelta } from "./models";

function fakeSocket(): SocketLike & { receive: (message: unknown) => void; sent: string[] } {
  const socket = {
    onopen: null,
    onclose: null,
    onerror: null,
    onmessage: null,
    sent: [] as string[],
    send(data: string) {
      this.sent.push(data);
    },
    close() {},
    receive(message: unknown) {
      socket.onmessage?.({ data: JSON.stringify(message) });
    },
  } as SocketLike & { receive: (message: unknown) => void; sent: string[] };
  return socket;
}

describe("a notice step from a server that still sends one", () => {
  it("is dropped without an error, a delta, a gap or a resync, and the next step follows on", () => {
    const socket = fakeSocket();
    const deltas: WorkingSetDelta[] = [];
    const errors: unknown[] = [];
    const gaps: number[] = [];
    connectDeltaClient(() => socket, {
      onDelta: (d) => deltas.push(d),
      onError: (e) => errors.push(e),
      onGapDetected: (expected) => gaps.push(expected),
    });
    socket.receive({ seq: 1, op: "snapshot", nodes: [], edges: [], filtered_count: 4 });
    socket.receive({ seq: 2, op: "add", nodes: [], edges: [] });
    socket.receive({ seq: 2, op: "notice", level: "warning", message: "4 item(s) withheld", count: 4 });
    socket.receive({ seq: 3, op: "add", nodes: [], edges: [] });

    expect(errors).toEqual([]);
    expect(gaps).toEqual([]);
    expect(deltas.map((d) => d.op)).toEqual(["snapshot", "add", "add"]);
    expect(socket.sent).toEqual([]);
  });
});
