/**
 * What ends a browser that stops sending part-way through a body (slice PL10, round 3).
 *
 * `start.ts` switches Node's whole-request timeout off, so that a long upload is not cut for its length (the brief:
 * Node's own timeouts must not cut a long upload or a long read short). That leaves a body being read with no limit
 * on it. The limit that replaces it is a STALL timer: no byte of the browser's body for `ms` (nginx's
 * `client_body_timeout`, 60 seconds, is the same measure). A body that keeps arriving, however slowly and however
 * long in all, is never cut. Two places need it, and each has its own clock:
 *
 *  - the forwarder reads a browser's body itself (`untilStalled`): the clock runs only while it is WAITING for the
 *    browser's next piece, never while it is waiting on the Conduit to take the last one (a slow Conduit holds the
 *    browser back, and that is not the browser stalling; the Conduit's own silence is the upstream timer's);
 *  - a page route's body is read by `express.urlencoded` (`pageBodyStall`): small, and never held back by anything
 *    downstream, so the clock is the count of bytes the socket has read.
 */
import type { NextFunction, Request, RequestHandler, Response } from "express";

import { isV1Path, rawPathOf } from "./v1.js";

/** Sixty seconds, as nginx's `client_body_timeout`. */
export const DEFAULT_BODY_STALL_MS = 60_000;

/** The browser sent nothing for the stall time while a body was expected. */
export class BodyStalled extends Error {}

/** The same pieces as `source`, but throws `BodyStalled` if the next one takes longer than `ms` to arrive. */
export async function* untilStalled(source: AsyncIterable<Buffer>, ms: number): AsyncGenerator<Buffer> {
  const iterator = source[Symbol.asyncIterator]();
  try {
    for (;;) {
      let timer: NodeJS.Timeout | undefined;
      const next = iterator.next();
      next.catch(() => undefined); // if the timer wins, this one's later outcome is nobody's
      const silence = new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          reject(new BodyStalled());
        }, ms);
      });
      let step: IteratorResult<Buffer>;
      try {
        step = await Promise.race([next, silence]);
      } finally {
        clearTimeout(timer);
      }
      if (step.done) return;
      yield step.value;
    }
  } finally {
    // Not awaited: with a piece still pending, a return would wait for it.
    void iterator.return?.()?.catch(() => undefined);
  }
}

/**
 * For every path but `/v1` (the forwarder reads its own): a request whose body goes silent for `ms` has its
 * connection ended. No answer is written: a browser that has stopped sending is not waiting for one.
 */
export function pageBodyStall(ms: number): RequestHandler {
  return (req: Request, res: Response, next: NextFunction): void => {
    const declared = req.headers["content-length"];
    const hasBody = (declared !== undefined && declared !== "0") || req.headers["transfer-encoding"] !== undefined;
    if (!hasBody || isV1Path(rawPathOf(req))) {
      next();
      return;
    }
    const socket = req.socket;
    let seen = socket.bytesRead;
    let lastMoved = Date.now();
    const timer = setInterval(
      () => {
        if (socket.bytesRead !== seen) {
          seen = socket.bytesRead;
          lastMoved = Date.now();
        } else if (Date.now() - lastMoved >= ms) {
          clearInterval(timer);
          req.destroy();
        }
      },
      Math.max(5, Math.floor(ms / 4)),
    );
    const stop = (): void => clearInterval(timer);
    req.once("end", stop);
    req.once("close", stop);
    res.once("close", stop);
    next();
  };
}
