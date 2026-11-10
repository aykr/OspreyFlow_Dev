# Draft for the orchestrator: ADR-146 amendment, "Stored to the standards" as built (L2.11a)

Not in `spec/` (the orchestrator's file). This draft is for a reserved number; rules-b does not write it.

**Status.** Proposed by rules-b, 10 November 2026, from L2.11a. It is agreed with the rules lane by
message.

**Decision.**
1. **The files.**
   - A rule's BPMN 2.0 process is exactly three elements, a start event, a business-rule task and an
     end event, joined by two sequence flows, with BPMN DI for its drawing.
   - Its DMN 1.3 decision is one decision table of one rule. The *If*'s property conditions are its
     columns, each cell written in one FEEL form: a quoted word, a list of them, `> n`, `< n` (digits,
     never an exponent), or a `date and time` range.
   - Everything else goes in `osprey:` extension elements (namespace `https://ospreyflow.org/schema/rule/1`):
     the subject's type, a drawn area, the relationship, frequency and strength, when the rule runs, its
     limits, its *Then* (severity, team, scope) and its declared dataset (`osprey:rule dataset`, an opaque
     OspreyFlow dataset id).
   - The codec is `packages/rule_standards`, one function per side.
2. **Only what OspreyFlow runs.** An import holding anything else is refused, naming each item:
   - any element or attribute of BPMN, DMN, `osprey:` or another vendor;
   - an element out of its place;
   - an attribute the rule model would drop.
   A file that is not one rule's is refused in words. A document type declaration is never read.
3. **Import** writes nothing.
   - It returns the rule and its declared dataset for the editor to open as a draft.
   - The body is capped as it streams, and each file is capped at 256 KB before it is parsed.
   - The dataset must be the case's own source or composite. Any other is the app's one
     `dataset_not_found`, whether it exists or not.
   - It needs `author_rules` at the case's Author level. *Export* needs `read_alert_queue` at Viewer and
     reads through the rules list's reach.
4. **"Stored from day one" (R2): the owner's or the orchestrator's call, below.**

**The question (it touches an accepted ADR, so it goes to the orchestrator first).** R2 and decision 3
say each rule "is saved as" BPMN and DMN. L2.11a builds a lossless codec and produces the files when they
are asked for (*Export*, *Show as BPMN*). The rule itself is still stored as its sentence.
- (a) **Recommended:** rules' L2.11 save writes the two files beside the rule, in the same transaction, at
  every version. The codec is already lossless and refuses anything it cannot carry. "Stored" then holds
  literally, and Export returns the stored files.
- (b) The sentence stays the store, with the files produced on demand. This needs an amendment saying R2
  is met by a lossless serialisation.
