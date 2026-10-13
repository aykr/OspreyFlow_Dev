// ADR-110 decision 7: a schedule chosen as hourly, daily, on weekdays or weekly at a time — or as an
// advanced cron expression — and the cron expression it is saved as. The Conduit explains and
// validates whatever is saved (`POST /v1/ingest/schedule-preview`); this only turns choices into the
// expression and an expression back into the choice it came from.

export type ScheduleChoice =
  | { kind: "none" }
  | { kind: "hourly"; minute: number }
  | { kind: "daily"; time: string }
  | { kind: "weekdays"; time: string }
  | { kind: "weekly"; day: number; time: string }
  | { kind: "cron"; cron: string };

const TIME = /^([01]\d|2[0-3]):([0-5]\d)$/;

function hm(time: string): [number, number] | null {
  const match = TIME.exec(time);
  return match ? [Number(match[1]), Number(match[2])] : null;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** The expression a choice is saved as; `null` for none, or for a time that is not a time. */
export function cronOf(choice: ScheduleChoice): string | null {
  switch (choice.kind) {
    case "none":
      return null;
    case "hourly":
      return Number.isInteger(choice.minute) && choice.minute >= 0 && choice.minute < 60 ? `${choice.minute} * * * *` : null;
    case "cron":
      return choice.cron.trim() || null;
    default: {
      const at = hm(choice.time);
      if (!at) return null;
      const [hour, minute] = at;
      const day = choice.kind === "daily" ? "*" : choice.kind === "weekdays" ? "1-5" : String(choice.day);
      return `${minute} ${hour} * * ${day}`;
    }
  }
}

/** The choice an expression came from; anything not one of the plain shapes is advanced. */
export function choiceOf(cron: string | null | undefined): ScheduleChoice {
  const text = (cron ?? "").trim();
  if (!text) return { kind: "none" };
  const fields = text.split(/\s+/);
  if (fields.length === 5) {
    const [minute = "", hour = "", dom = "", month = "", dow = ""] = fields;
    const plain = (s: string, max: number) => /^\d{1,2}$/.test(s) && Number(s) <= max;
    if (dom === "*" && month === "*" && plain(minute, 59)) {
      if (hour === "*" && dow === "*") return { kind: "hourly", minute: Number(minute) };
      if (plain(hour, 23)) {
        const time = `${pad(Number(hour))}:${pad(Number(minute))}`;
        if (dow === "*") return { kind: "daily", time };
        if (dow === "1-5") return { kind: "weekdays", time };
        if (/^[0-6]$/.test(dow)) return { kind: "weekly", day: Number(dow), time };
      }
    }
  }
  return { kind: "cron", cron: text };
}
