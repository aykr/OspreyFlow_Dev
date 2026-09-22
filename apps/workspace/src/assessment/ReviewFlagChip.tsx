// `Judgement.flagged_for_review`/`flag_reason` rendering — `02_GLASS_FRONTEND.md` §9.4: "A
// judgement flagged for review... surfaces as a status chip on its own row." The same
// "worthless if invisible" discipline `watches/StatusBadge.tsx`'s own header comment already
// states for a stopped monitor, applied here: the chip alone would tell a reader *that*
// something changed but not *what* — `flag_reason` renders as plain text beneath it, always
// visible, never hidden behind a hover-only tooltip (a keyboard/screen-reader user gets nothing
// from hover), per `02_GLASS_FRONTEND.md` §7's own copy rule ("Errors say what happened and what
// to do", applied here to a flag rather than an error).
export interface ReviewFlagChipProps {
  reason: string;
}

export function ReviewFlagChip({ reason }: ReviewFlagChipProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <span
        className="value"
        style={{
          alignSelf: "flex-start",
          padding: "2px var(--sp-8)",
          borderRadius: "999px",
          background: "color-mix(in srgb, var(--warning) 16%, transparent)",
          color: "var(--warning)",
          fontWeight: 600,
          textTransform: "uppercase",
          fontSize: "var(--fs-11)",
        }}
      >
        Flagged for review
      </span>
      <p className="label" style={{ margin: 0 }}>
        {reason}
      </p>
    </div>
  );
}
