# Slice BL1 · BL1 · The slice line set-up

- **Build id:** BL1
- **Dial setting:** thrift
- **Rounds limit:** 1
- **After:** nothing

## What

The seats, the refusing hooks, the builder's stop gate, the merge and push scripts, the board and the dashboard's
status file, the dial and the accounts file: `slice-line/README.md`. Set-up only; no product code.

## Acceptance test

`OspreyFlow_Build/scripts/slice_line/tests/test_gates.py`, through `OspreyFlow_Build/scripts/slice_line/tests/run.sh`: each gate shown refusing a
planted violation in the shape its real call site produces.

## Checks

The same suite.

## Out of scope

Product code, backlog work, the three diffs for the owner (make ci wiring, CLAUDE.md, ADR-142), and merging:
BL1 changes the line itself, so the merge script refuses it; it reaches main by the owner's hand.
