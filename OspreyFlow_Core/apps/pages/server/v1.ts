/**
 * What is a `/v1` path, and how a refusal on one is worded. Shared by the anti-forgery check, the gate and the
 * forwarder (ADR-152 decision 5; slice PL10), so that all three read the same raw path the same way.
 */
import type { Request, Response } from "express";

/** The request target's path as the browser wrote it: before any decoding, tidying or routing. */
export function rawPathOf(req: Pick<Request, "originalUrl">): string {
  const target = req.originalUrl;
  const query = target.indexOf("?");
  return query < 0 ? target : target.slice(0, query);
}

/** True for `/v1` and anything under `/v1/`, and only in lower case: no tidying of the path decides what it is. */
export function isV1Path(rawPath: string): boolean {
  return rawPath === "/v1" || rawPath.startsWith("/v1/");
}

/**
 * A refusal on a `/v1` path, in the Conduit's own shape (`{"detail": "..."}`, which the Glass reads). Words
 * for a person, never a reason that names the service's insides.
 */
export function refuseJson(res: Response, status: number, detail: string): void {
  res.status(status).json({ detail });
}
