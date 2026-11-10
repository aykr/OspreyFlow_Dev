"""What marks an alert as a scheduled load's notice (ADR-110 Amendment 3 point 1, Amendment 19),
in a module of its own so the alert store and the scheduler both read it without importing each
other.

A notice is any alert whose `rule_id` is `schedule:<recipe id>` and that has no typology: the shape
the scheduler has always written, so a notice written before Amendment 19 is one too."""

#: The `rule_id` prefix of a schedule notice.
NOTICE_RULE_PREFIX = "schedule:"
