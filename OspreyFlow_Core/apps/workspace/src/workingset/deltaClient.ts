// The delta client — `spec/03_CONDUIT_MIDDLEWARE.md` §3.2's wire protocol,
// Drives `WorkingSetDelta` messages off a
// `/v1/investigations/{id}/stream` WebSocket into `workingset/store.ts`'s
// `applyDelta`.
//
// **Transport auth is not solved here.** `services/api/app.py`'s
// `_authenticate_websocket` reads the bearer token from the
// `Authorization` header, which a browser's native `WebSocket` constructor
// cannot set — only a query parameter, a cookie, or a `Sec-WebSocket-
// Protocol` subprotocol token can cross that boundary from a real browser.
// This module accepts a `createSocket` factory precisely so the caller
// supplies whatever transport can authenticate (the `ws` package with
// custom headers in tests and in this checkpoint; a browser-viable scheme
// is Checkpoint 2's decision to make, not this module's to guess at).
//
// **Gap detection is this client's job, not just the server's.** A
// reconnect's `last_acknowledged_seq` handshake is the obvious case the
// server already resolves (`WorkingSetService.sync`). The one this module
// exists to close is the live case: `notify.py`'s Valkey Pub/Sub delivery
// to an *already-connected* socket is at-most-once, so a dropped message
// mid-session is a real possibility a naive client — one that just trusts
// every incoming `seq` is `lastSeq + 1` — would silently miss. This client
// checks that invariant on every non-snapshot delta and, on a violation,
// drops the out-of-order delta and requests an explicit resync over the
// same socket rather than applying something it cannot place correctly.
import type { DeltaViewOverCap, LimitExceeded, WorkingSetDelta } from "./models";

const DELTA_OPS = new Set(["add", "remove", "replace_edge", "reproject", "snapshot"]);

/** A server that still sends the retired `notice` step (ADR-124): it is dropped quietly. The server
 * stamps it with the previous step's own number, so it neither advances nor checks the sequence. */
function isRetiredNotice(value: unknown): value is { op: "notice"; seq: number } {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { op?: unknown }).op === "notice" &&
    typeof (value as { seq?: unknown }).seq === "number"
  );
}

/** A reader's own view of the case is past a cap (ADR-124 decision 2): sent in place of a snapshot
 * or a delta, and carrying the sequence number of what it replaces, so it takes no place in this
 * client's sequence and is never applied as a delta. */
export function isViewOverCap(value: unknown): value is DeltaViewOverCap {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { op?: unknown }).op === "view_over_cap" &&
    typeof (value as { seq?: unknown }).seq === "number" &&
    typeof (value as { would_be?: unknown }).would_be === "object"
  );
}

export function isWorkingSetDelta(value: unknown): value is WorkingSetDelta {
  return (
    typeof value === "object" &&
    value !== null &&
    "op" in value &&
    typeof (value as { op: unknown }).op === "string" &&
    DELTA_OPS.has((value as { op: string }).op) &&
    "seq" in value &&
    typeof (value as { seq: unknown }).seq === "number"
  );
}

/** The minimal surface this module needs from a WebSocket — satisfied by
 * both the browser's native `WebSocket` and the `ws` package's client. */
export interface SocketLike {
  onopen: (() => void) | null;
  onclose: ((event: { code: number; reason: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface DeltaClientHandlers {
  onDelta: (delta: WorkingSetDelta) => void;
  /** The reader's own view is past a cap (`view_over_cap`): their figure, for the dialog. The
   * server then sends nothing more on this connection until `requestResync(null)`. */
  onViewOverCap?: (wouldBe: LimitExceeded) => void;
  onOpen?: () => void;
  onClose?: (event: { code: number; reason: string }) => void;
  onError?: (error: unknown) => void;
  /** Fires when this client detects a live-push gap and asks the server
   * to resync — observable for tests; the resulting `snapshot` reaches
   * `onDelta` like any other delta once the server replies. */
  onGapDetected?: (expectedSeq: number, actualSeq: number) => void;
}

export interface DeltaClient {
  close: () => void;
  requestResync: (lastAcknowledgedSeq: number | null) => void;
  readonly lastSeq: number | null;
}

export function connectDeltaClient(
  createSocket: () => SocketLike,
  handlers: DeltaClientHandlers,
  initialLastAcknowledgedSeq: number | null = null,
): DeltaClient {
  const socket = createSocket();
  let lastSeq: number | null = null;

  function requestResync(lastAcknowledgedSeq: number | null): void {
    socket.send(JSON.stringify({ last_acknowledged_seq: lastAcknowledgedSeq }));
  }

  socket.onopen = () => {
    requestResync(initialLastAcknowledgedSeq);
    handlers.onOpen?.();
  };

  socket.onmessage = (event) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(String(event.data));
    } catch (error) {
      handlers.onError?.(error);
      return;
    }
    if (isRetiredNotice(parsed)) return; // dropped: it takes no place in the sequence
    if (isViewOverCap(parsed)) {
      // Neither advances `lastSeq` nor is checked against it (it carries the number of what it
      // replaces), and it is never applied as a delta.
      handlers.onViewOverCap?.(parsed.would_be);
      return;
    }
    if (!isWorkingSetDelta(parsed)) {
      handlers.onError?.(new Error(`not a WorkingSetDelta: ${String(event.data)}`));
      return;
    }
    const delta = parsed;

    if (delta.op !== "snapshot" && lastSeq !== null && delta.seq !== lastSeq + 1) {
      handlers.onGapDetected?.(lastSeq + 1, delta.seq);
      requestResync(lastSeq);
      return; // drop the out-of-order delta — the resync's snapshot will fix state
    }

    lastSeq = delta.seq;
    handlers.onDelta(delta);
  };

  socket.onclose = (event) => handlers.onClose?.(event);
  socket.onerror = (event) => handlers.onError?.(event);

  return {
    close: () => socket.close(),
    requestResync,
    get lastSeq() {
      return lastSeq;
    },
  };
}
