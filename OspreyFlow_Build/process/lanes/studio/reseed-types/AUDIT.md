# A type refusal stops a reseed: can any demo generator give one id two types? (14 November 2026)

The CARRIES row's worry: since ADR-124 Amendment 18 (a47c2c0), `upsert_nodes` refuses a write onto an id another
type holds. A generator whose ids hash the plan key alone (`pid_plan.node_id`), and which moved a key between
types, would then stop a reseed onto a store seeded before. **Answer: nothing can, today or across the
generators' history.** The row closes with no change to any generator. A guard test keeps it so.

## The packs, and which can carry an id from one seed to the next

| Pack (`scripts.demo_packs`) | Seed | How its node ids are made | Can an id persist across a reseed? |
| --- | --- | --- | --- |
| hmp | `seed_hmp_fixture` | Recipes and `hmp_network`: `new_node_id()`, new each run | No |
| operation-ledger | `seed_ledger_fixture` | Recipes and `ledger._direct_writes`: `new_node_id()` | No |
| paysim | `seed_paysim` | `paysim-acct-uuid5(account)` (one type), and it clears its own rows first (`clear_seeded_graph`) | No (cleared) |
| enron | `seed_enron` | Real data (rule 9: read, not run); it clears its own rows first | No (cleared) |
| prison-intelligence, prison-intelligence-scale | `seed_pid`, `seed_pid_scale` | `pid_plan.node_id(key)`: the SHA-256 of the plan key alone; recipes' own entities are `new_node_id()` | **Yes** |
| cyber-intrusion | `seed_cyber_intrusion` | `cyber-…` from the STIX id, which carries the STIX kind | **Yes** |
| fixture-corp | `seed_fixture_corp` | Fixed names: `corp-…`, `corp-path-hub`, `corp-path-spoke{n}-{m}` | **Yes** |

## What was checked

1. **Within each plan today:** no id has two types. The PID demo and scale plans (every `node_id` caller writes
   either the planned entity's own key and type, or a link's ends), cyber-intrusion's 22 nodes, and fixture-corp's
   31 plus its hub and spokes (`build_path_spokes`, all `Person`).
2. **Between packs:** the prefixes (`pid-`, `cyber-`, `corp-`, `paysim-`) never meet, and no id is shared.
3. **Across history:**
   - **PID:** `pid_history_audit.sh` builds every version of `pid_plan.py` on main as it was, since it imports
     only `pid_names.py`, in both profiles. 14,529 ids across the seven versions that have `node_id`, and none on
     more than one type (`pid_history.txt`). The two earliest versions (209a078, b2d1fdf) had no `node_id` and no
     writer, so no store holds an id from them.
   - **cyber-intrusion and fixture-corp:** one commit each on main; they have never changed.

## The guard

`tests/demo_fixtures/test_generator_ids_one_type.py` (rule 12):
- no PID id has two types, in either profile;
- no fixture-corp or cyber id has two types;
- no id is shared between packs, and an id in both PID profiles keeps its type in both.

It is shown red (`RED_RECORD.txt`) by a plant at the real call site: `pid_plan.node_id` hashing a key without its
kind, so a person's `pin:` and `cash:` would share an id. Three cases go red, and the restored tree is green. Its
own `test_the_check_finds_a_key_hashed_without_its_kind` proves the check can fail without touching the code.

## The live reseed (stack f, 14 November 2026, the owner's word to run it then)

The run was `live_reseed.py`, on stack f under studio's lease (taken 13:15:51Z, released after), beside case's
make; the host's load average at each run's start and end is in each record. Each of the four persisting packs was
seeded by main's seed path (`python -m <script> --case-name <the pack's case>`) and then reseeded once at main.

| Pack | Seed | Reseed | Nodes by type after the seed, and after the reseed | Refusals |
| --- | --- | --- | --- | --- |
| cyber-intrusion | exit 0 | exit 0 | the same 22 nodes in 7 types | none |
| prison-intelligence | exit 0 | exit 0 | the same 6,998 nodes in 8 types | none |
| prison-intelligence-scale | exit 0 | exit 0 | the same 7,176 nodes in 6 types | none |
| fixture-corp, as its dataset's owning unit (`unit-intel`) | exit 0 | exit 0 | the same 68 nodes (65 Person, 3 Organisation) | none |

**No type refusal, and no other write refused.** A reseed writes nothing new: every count is the same after it.

**The raw records:**
- `live_reseed.run1.txt`: the runner stopped before seeding, because it counted through a `V` type that ArcadeDB's
  schema does not have. Fixed.
- `live_reseed.613e29a.txt`: three packs clean. Fixture-corp was refused at case set-up, before any write:
  `DatasetRefusedError: not one of this unit's datasets`. On stack f, the fixture-corp dataset was already owned
  by `unit-intel`, left by an earlier run, while the runner seeded as `unit-1`. That is a property of the stack,
  not of a type.
- `live_reseed.aa145c6.fixture-corp.txt`: fixture-corp seeded as its owning unit, as `seed_internal` passes the
  owning unit. Both runs clean.

PID's one line matching "refus" was the seed's own help text ("If a rehearsal reset ever refuses…"), not a refusal.
