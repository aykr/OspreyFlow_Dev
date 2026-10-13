// The version and the last update check, in words (ADR-114 decision 13, Amendment 8 point 2). The
// check is run on the host (`ospreyflow update --check`), and so is the update: the Glass says what
// to run there and runs nothing.
import type { UpdateNotice } from "../../../../packages/schemas/generated";

export interface UpdateWords {
  tone: "available" | "plain" | "problem";
  headline: string;
  detail: string;
}

const HOST = "On the machine OspreyFlow runs on:";

function when(iso: string): string {
  const at = new Date(iso);
  const day = at.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const time = at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  return `Checked ${day} at ${time} UTC.`;
}

export function updateWords(version: string | null | undefined, update: UpdateNotice | null | undefined): UpdateWords {
  if (!update) {
    return { tone: "plain", headline: "Not checked for updates yet.", detail: `${HOST} ospreyflow update --check` };
  }
  if (update.problem) {
    return { tone: "problem", headline: "The last update check could not answer.", detail: `${when(update.checked_at)} ${update.problem}` };
  }
  if ((version ?? update.current).startsWith("dev-")) {
    return {
      tone: "plain",
      headline: "This deployment builds from its checkout; it moves with git pull and ospreyflow start --build.",
      detail: `${when(update.checked_at)} The newest release is ${update.latest}.`,
    };
  }
  if (update.update_available) {
    return { tone: "available", headline: `${update.latest} is available.`, detail: `${when(update.checked_at)} ${HOST} ospreyflow update` };
  }
  return { tone: "plain", headline: `Up to date: ${update.current} is the newest release.`, detail: when(update.checked_at) };
}
