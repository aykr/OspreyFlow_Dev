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

// ADR-124 U6b (Amendment 9): a view past the cap.
describe("a view_over_cap step", () => {
  const wouldBe = {
    error: "limit_exceeded",
    cap_kind: "nodes",
    cap: 50_000,
    would_be: 50_001,
    options: ["branch", "filter", "promote_to_batch"],
  };

  it("reaches onViewOverCap, advances no sequence and trips no gap", () => {
    const socket = fakeSocket();
    const deltas: WorkingSetDelta[] = [];
    const seen: unknown[] = [];
    const gaps: number[] = [];
    const client = connectDeltaClient(() => socket, {
      onDelta: (d) => deltas.push(d),
      onViewOverCap: (w) => seen.push(w),
      onGapDetected: (expected) => gaps.push(expected),
    });
    socket.receive({ seq: 1, op: "snapshot", nodes: [], edges: [] });
    socket.receive({ seq: 9, op: "view_over_cap", would_be: wouldBe });

    expect(seen).toEqual([wouldBe]);
    expect(gaps).toEqual([]);
    expect(client.lastSeq).toBe(1);
    expect(deltas.map((d) => d.op)).toEqual(["snapshot"]);
    expect(socket.sent).toEqual([]);

    // The step after it is judged against the sequence as it was, not against the number it carried.
    socket.receive({ seq: 2, op: "add", nodes: [], edges: [] });
    expect(gaps).toEqual([]);
    expect(deltas.map((d) => d.op)).toEqual(["snapshot", "add"]);
  });

  it("is not an error when nothing is listening", () => {
    const socket = fakeSocket();
    const errors: unknown[] = [];
    connectDeltaClient(() => socket, { onDelta: () => {}, onError: (e) => errors.push(e) });

    socket.receive({ seq: 3, op: "view_over_cap", would_be: wouldBe });

    expect(errors).toEqual([]);
  });

  it("is dropped, never applied as a delta, whatever it says", () => {
    const socket = fakeSocket();
    const deltas: WorkingSetDelta[] = [];
    connectDeltaClient(() => socket, { onDelta: (d) => deltas.push(d) });

    socket.receive({ seq: 1, op: "view_over_cap", would_be: wouldBe });

    expect(deltas).toEqual([]);
  });

  it("is answered by a resync with no last sequence when the reader tries again", () => {
    const socket = fakeSocket();
    const client = connectDeltaClient(() => socket, { onDelta: () => {} });
    socket.receive({ seq: 4, op: "snapshot", nodes: [], edges: [] });

    client.requestResync(null);

    expect(socket.sent).toEqual([JSON.stringify({ last_acknowledged_seq: null })]);
  });

  it("is still the case that a real gap after a snapshot asks for a resync from the last sequence", () => {
    const socket = fakeSocket();
    const gaps: number[] = [];
    connectDeltaClient(() => socket, { onDelta: () => {}, onGapDetected: (e) => gaps.push(e) });
    socket.receive({ seq: 1, op: "snapshot", nodes: [], edges: [] });
    socket.receive({ seq: 5, op: "view_over_cap", would_be: wouldBe });
    socket.receive({ seq: 7, op: "add", nodes: [], edges: [] });

    expect(gaps).toEqual([2]);
    expect(socket.sent).toEqual([JSON.stringify({ last_acknowledged_seq: 1 })]);
  });
});
