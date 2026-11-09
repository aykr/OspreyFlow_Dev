# Draft for the orchestrator: ADR-143, Amendment (number to be reserved) — merging a drawn dataset as built (L3.9)

Status: built by the case lane at L3.9 under Prompt L. The decisions the brief left open were taken as
recommended and are recorded here for the owner to overrule. Amendment 2 decisions 6 and 7 and Amendment
3 stand except where this says so. Spec 03's *Merging a drawn dataset* and spec 01's line have the detail.

**As built.**

1. **One promotion.** A merge is L3.4's promotion (Amendment 5 decision 1) with the trigger `drawn_merge`:
   the drawn dataset's elements gain the target (`promote_elements`, the same elements, rule 6), all or
   nothing, under the target's highest marking and promotion policy, reviewed in the target's *Analyst
   promotions* by its Authors holding `review_promotions`, never the merger. Its record's `layer_id` is the
   drawn dataset.
2. **Who** (Amendment 3 decision 2): `merge_datasets` on all four routes; the target must be a source
   dataset of the drawing's unit that the merger is an Author of (its home case's, teams included). Every
   other target, of whatever kind, is answered 404 `not_a_target`, alike. The merger reads the drawing as
   any reader does, through its home case (its Author shares it with them): nothing here widens what
   anyone reads.
3. **Map the models: the same name only (open question to the owner, below).** An element's type is its
   store class and the merge keeps the same element, so a drawn type goes in only as the target's type of
   the same name; a type the target lacks is left out, saying so, and may be proposed on the target's Model
   tab and merged later. Amendment 2 decision 6.1's "each drawn type to one of the target's types" is
   therefore met only where the names agree.
4. **Match.** Candidates are read through the merger scoped to the target alone, in the adapter (no filter
   after retrieval), so no node of another dataset or above the merger is offered, counted or ordered, and
   the reads are the same with such a node present or absent. A chosen match must be one offered now, of a
   drawn node that goes (422 `not_a_match`, alike for every reason). It is written in the load's own
   transaction as a `SAME_AS` that is `inferred` and scored (`model_version` drawn_merge), in the target,
   marked as the stricter of its ends and within the target's highest (rule 5: a person confirms it;
   rule 6: nothing collapsed). An approval checks each match again through the reviewer.
5. **Dry run** counts only what the merger may see and writes nothing; the screen asks for it again after
   any change, and offers *Merge* only after it (the route does not require it, as Amendment 5's delete).
6. **After the merge** (decision 7): the drawing's home case reads the target, and the drawn dataset
   read-only (so what did not become data stays readable to the same members, and the Studio reaches the
   drawing no more); its boards become views (drawing off, layout and sharing kept, the drawn nodes added
   to the selection); a merged view answers `annotations` read through each reader's own principal (an
   item they may not see has none). One merge per drawing; one waiting at a time.
7. **Revert** is the promotion's operator command; for a drawn merge it also withdraws the merge's matches
   in its transaction, then puts the case back on the drawing and the views back to boards; without those
   stores it refuses.
8. **Not atomic across stores:** the graph commit comes first and the Postgres steps of decision 7 after it,
   as L3.4's `promoted_at`; a failure between them leaves the elements merged and the case on its drawing,
   said in the Conduit's log and repaired by running the revert (recorded, not built: a retry of the Postgres
   steps is a hygiene item if the orchestrator wants one).

**Open question for the owner (from item 3).** (a) same name only, as built; (b) a retype inside the load
through `supersede_node` (a new revision of another type, its revert undoing the supersede: a port change
and conformance cases); (c) copies into the target for a retyped item (two mechanisms, two reverts).

**Tests.** `tests/services/api/test_drawn_merge.py` (each check red by its plant, `process/lanes/case/gates/
L3.9-plants.txt`); the live store cases in `test_promotion_store.py`, `test_case_views_store.py`,
`test_datasets_store.py` (`gates/L3.9-live-plants.py`); `tests/conformance/graph_port/test_promotion.py`'s
merge transaction cases; `keyboard/drawn-merge.spec.ts`, `keyboard/views.spec.ts`; axe in every harness.
