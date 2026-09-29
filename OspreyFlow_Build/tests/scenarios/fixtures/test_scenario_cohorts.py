"""The promoted cohort fixtures produce the shape B4–B8 and B15 actually walk — round 13cb.

**Why a fixture module gets its own test.** These generators are now consumed by two tiers: the
in-process exit-criterion test and `scripts/seed_scenarios.py`, which seeds a rendered deployment
for the over-the-wire test. A silent change to the shape would make *both* tiers agree with each
other and disagree with `08_ACCEPTANCE_SCENARIOS.md` — two greens and no alarm, which is the
failure `CLAUDE.md` rule 12 keeps naming. The assertions below are the acceptance rows' own
wording turned into checks, so the thing that fails is the fixture, not the walkthrough four
layers downstream of it.

Rule 9, asserted rather than trusted: `test_every_number_is_in_the_reserved_drama_range`.
"""

from __future__ import annotations

from demo_fixtures.scenario_cohorts import (
    generate_cohort,
    generate_device_legs,
    generate_handle_cohort,
)
from demo_fixtures.seizure_record import (
    HANDSET_IMEI_NORMALISED,
    SIM_A_IMSI_NORMALISED,
    SIM_B_IMSI_NORMALISED,
)
from tools.layout import REPO as _REPO

SHARED = "shared-endpoint-under-test"


def test_b4_b5_every_member_reaches_the_shared_endpoint_in_two_hops() -> None:
    """B4/B5: seed the people, expand twice, find the one endpoint they have in common.

    Asserted as *reachability*, not as an edge count: B5's claim is that one hop out from the
    cohort's own endpoints discovers the shared one, and a construction that wired the people
    straight to the shared endpoint would satisfy a count while skipping the hop the row is about.
    """
    cohort = generate_cohort(shared_endpoint_id=SHARED, prefix="alpha", count=4)

    assert len(cohort.person_ids) == 4
    assert len(cohort.endpoint_ids) == 4

    uses = {(e.source, e.target) for e in cohort.edges if e.type == "USES"}
    comms = {(e.source, e.target) for e in cohort.edges if e.type == "COMMUNICATED_WITH"}

    for person, endpoint in zip(cohort.person_ids, cohort.endpoint_ids, strict=True):
        assert (person, endpoint) in uses, f"{person} does not use its own endpoint"
        assert (endpoint, SHARED) in comms, f"{endpoint} is not one hop from the shared endpoint"

    # No person is wired directly to the shared endpoint — the hop must be real.
    assert not any(p in {s for s, _ in comms} for p in cohort.person_ids)


def test_b7_the_second_cohort_shares_one_messaging_handle() -> None:
    """B7's literal: "a shared messaging handle is common to that cohort"."""
    cohort = generate_handle_cohort(prefix="beta", count=4)

    handles = [n for n in cohort.nodes if n.properties.get("endpoint_kind") == "handle"]
    assert len(handles) == 1, f"expected exactly one shared handle, got {len(handles)}"
    assert handles[0].id == cohort.shared_id

    users = {e.source for e in cohort.edges if e.type == "USES" and e.target == cohort.shared_id}
    assert users == set(cohort.person_ids), (
        "not every member of the cohort uses the shared handle, so B7 has nothing to find"
    )


def test_b8_the_handle_and_a_number_share_no_lexical_space() -> None:
    """**The precondition B8's disposition rests on**, asserted rather than assumed.

    `08_ACCEPTANCE_SCENARIOS.md` B8 links the handle to the shared endpoint with a `SAME_AS`
    *asserted at score 1.0*, citing ADR-024's pattern for "identifier systems with no lexical
    overlap". That disposition is only correct if the two really do have no overlap — if a future
    fixture made the handle `@447700900123`, a comparison function *could* score it and ADR-024's
    reasoning would no longer apply to this pair.
    """
    handle_cohort = generate_handle_cohort(prefix="beta", count=2)
    number_cohort = generate_cohort(shared_endpoint_id=SHARED, prefix="alpha", count=2)

    handle = next(n for n in handle_cohort.nodes if n.id == handle_cohort.shared_id)
    handle_value = handle.properties["value_normalised"]
    assert handle_value.startswith("@")

    for endpoint in (n for n in number_cohort.nodes if n.type == "Endpoint"):
        number = endpoint.properties["value_normalised"]
        shared_characters = set(handle_value) & set(number)
        assert not (shared_characters - set("-0123456789")), (
            f"the handle {handle_value!r} and the number {number!r} share lexical structure "
            "beyond digits, so ADR-024's 'no lexical resemblance' premise no longer holds for "
            "this pair and B8's asserted-at-1.0 disposition needs revisiting"
        )


def test_b15_two_sims_reach_one_handset_in_one_traversal() -> None:
    """B15: "Both SIMs link to one device; the SIM-swap pattern is one traversal, not a special
    case." Asserted as both SIMs pointing at the *same* handset id."""
    legs = generate_device_legs()

    assert len(legs.sim_ids) == 2
    paired = {(e.source, e.target) for e in legs.edges if e.type == "PAIRED_WITH"}
    assert paired == {(legs.sim_ids[0], legs.handset_id), (legs.sim_ids[1], legs.handset_id)}

    by_id = {n.id: n for n in legs.nodes}
    # **The handset is a `Device`, not an `Endpoint`** — `endpoint_kind` is an enum of
    # msisdn|imsi|email|handle|iban|card, and an IMEI names a handset, which `Device` carries as
    # its own identifier. A first attempt wrote it as an Endpoint and the ontology refused it;
    # this asserts the model the ontology actually declares.
    assert by_id[legs.handset_id].type == "Device"
    assert by_id[legs.handset_id].properties["imei"] == HANDSET_IMEI_NORMALISED
    assert all(by_id[s].properties["endpoint_kind"] == "imsi" for s in legs.sim_ids)

    # The identifiers are the seizure record's own, so B13's ingest and B15's pivot land on the
    # same handset rather than on two that merely look alike.
    assert {by_id[s].properties["value_normalised"] for s in legs.sim_ids} == {
        SIM_A_IMSI_NORMALISED,
        SIM_B_IMSI_NORMALISED,
    }


def test_ids_are_minted_per_call_so_reruns_do_not_collide() -> None:
    """The persistent `ospreyflow` database outlives any one run. Fixed ids would make a second
    seed collide with the first, and the failure would read as a duplicate rather than as stale
    fixture data — the reasoning the original test-local helpers gave, kept because it is still
    true and now matters more, since a deployment is seeded repeatedly."""
    first = generate_cohort(shared_endpoint_id=SHARED, prefix="alpha")
    second = generate_cohort(shared_endpoint_id=SHARED, prefix="alpha")
    assert set(first.person_ids).isdisjoint(second.person_ids)

    # …but pinning the token makes them reproducible, which the seeder needs to report what it
    # wrote.
    pinned_a = generate_cohort(shared_endpoint_id=SHARED, prefix="alpha", run_token="fixed")
    pinned_b = generate_cohort(shared_endpoint_id=SHARED, prefix="alpha", run_token="fixed")
    assert pinned_a.person_ids == pinned_b.person_ids


def test_every_number_is_in_the_reserved_drama_range() -> None:
    """`CLAUDE.md` rule 9 as a check rather than an intention. Ofcom reserves 07700 900000–900999
    precisely so fixtures never dial a real subscriber."""
    cohort = generate_cohort(shared_endpoint_id=SHARED, prefix="alpha", count=8)
    for endpoint in (n for n in cohort.nodes if n.type == "Endpoint"):
        value = endpoint.properties["value_normalised"]
        assert value.startswith("+44770090"), f"{value} is outside the reserved drama range"
        assert len(value) == len("+447700900123"), value


def test_a_pinned_token_produces_the_same_fixture_in_a_different_process() -> None:
    """**The property the seeder/test split depends on, and it did not hold at first.**

    `scripts/seed_scenarios.py` writes these nodes inside the deployment's own container; the
    over-the-wire test then has to *find* them, from a different process. So every value derived
    from the run token must be identical in both. The original derived them from `abs(hash(...))`,
    which Python randomises per interpreter — `abs(hash("scenarios")) % 900` gave 674 in one
    process and 514 in the next, measured. The test would have searched for an endpoint that was
    never written, and the failure would have read as "seeding is broken" rather than "the two
    processes disagree".

    This runs the generator in a *genuinely separate interpreter* rather than calling it twice
    here, because calling it twice in one process is exactly the check that cannot fail for this
    defect — the same trap `CLAUDE.md` rule 15 names about planted violations taking the real
    shape.
    """
    import subprocess
    import sys

    repo_root = _REPO
    program = (
        "import sys; sys.path[:0]=['packages','services','.']\n"
        "from demo_fixtures.scenario_cohorts import (\n"
        "    generate_cohort, generate_device_legs)\n"
        "c = generate_cohort(shared_endpoint_id='s', prefix='alpha', run_token='scenarios')\n"
        "d = generate_device_legs(run_token='scenarios')\n"
        "print([n.properties['value_normalised'] for n in c.nodes if n.type == 'Endpoint'])\n"
        "print([n.properties.get('value_normalised') or n.properties['imei'] for n in d.nodes])\n"
    )
    runs = [
        subprocess.run(
            [sys.executable, "-c", program],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for _ in range(2)
    ]
    assert runs[0] == runs[1], (
        "the same pinned token produced different values in two interpreters, so a seeder and a "
        f"test can never agree on what was written:\n{runs[0]}vs\n{runs[1]}"
    )
    assert runs[0].strip(), "the subprocess produced no output — the check would be vacuous"


def test_the_pre_swap_state_omits_the_swapped_sim() -> None:
    """**What a seeder asks for — round 13cdb.** `08_ACCEPTANCE_SCENARIOS.md` B13 ingests the
    later seizure record and the swap is what it reveals, so a deployment seeded with both SIMs
    leaves that ingest nothing to create and the hotlist never fires."""
    both = generate_device_legs(run_token="fixed")
    earlier = generate_device_legs(run_token="fixed", include_swapped_sim=False)

    assert len(both.sim_ids) == 2
    assert len(earlier.sim_ids) == 1
    assert earlier.sim_ids[0] == both.sim_ids[0], "the SIM that is kept must be the earlier one"
    assert earlier.handset_id == both.handset_id
    assert [e for e in earlier.edges if e.type == "PAIRED_WITH"], "the handset lost its only SIM"
