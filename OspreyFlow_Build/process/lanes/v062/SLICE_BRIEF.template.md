# Slice <ID> · <build id from the plan> · <what, in one line>

<!-- Copy to slices/<ID>.md, fill in, add the row to slices.tsv, and commit both with
     merge_slice.py records. A slice whose build id is not in the plan is reported to the owner, not started. -->

- **Build id:** <BL1, CO1, IS2 ...: from dashboard/index.html>
- **Dial setting:** <thrift | balanced | sprint: the setting it is planned for; it starts on the current one>
- **Rounds limit:** <1 | 2: from the dial; the slice stops and asks the owner after this many verifier rounds>
- **After:** <slices that must be merged first, or "nothing">

## What

<What the slice delivers, in the owner's words where there are any. One slice, one thing a person can see or a
test can prove. The spec sections that bind it, by file and section.>

## Acceptance test

<The test that fails today and passes when the slice is done. Name its file(s) (they become acceptance_files)
and the command (acceptance). Say what failure it shows red, and why that failure is the real one (rule 15).>

## Checks

<The fast checks the builder must keep green (checks): the touched paths' tests, lint, type checks. Pure only:
nothing reaching a live store (ports 9). Live tests go in the acceptance command through stack_lease.sh.>

## Out of scope

<What the builder must not do in this slice, and the questions it must stop and ask rather than answer.>
