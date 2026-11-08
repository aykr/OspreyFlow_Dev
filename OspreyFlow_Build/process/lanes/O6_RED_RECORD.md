# O-six: six lanes and two test stacks, red then green (rule 15)

Recorded by the orchestrator, 8 November 2026, for ADR-142 Amendment 3. Offline (closed ports 59991–59994, no
OSPREY_LANE).

## Red: the new tests against the four-lane, one-stack scripts

```
E             ============================== 1 passed in 0.00s ===============================
E            +  where 0 = CompletedProcess(args=['/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/ospreyflow/Osp...              [100%]\n\n=============================
E             ============================== 1 passed in 0.00s ===============================
E            +  where 0 = CompletedProcess(args=['/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/ospreyflow/Osp...              [100%]\n\n=============================
FAILED tests/test_stack_lease.py::test_a_third_acquire_while_both_stacks_are_held_is_refused_and_names_both_holders
FAILED tests/test_stack_lease.py::test_a_lane_holds_one_stack_at_a_time
FAILED tests/test_stack_lease.py::test_a_named_stack_is_taken_even_when_another_is_free
FAILED tests/test_stack_lease.py::test_acquire_prints_the_ports_of_the_stack_taken
FAILED tests/test_stack_lease.py::test_release_by_a_lane_not_holding_it_is_refused
FAILED tests/test_stack_lease.py::test_the_holder_releases_once_the_stack_is_down
FAILED tests/test_stack_lease.py::test_up_is_refused_to_a_lane_not_holding_the_lease
FAILED tests/test_stack_lease.py::test_up_and_down_start_and_stop_only_the_holders_own_stack
FAILED tests/test_stack_lease.py::test_a_release_looks_only_at_its_own_stack
FAILED tests/test_port_guard.py::test_each_stack_is_reached_only_by_its_own_holder[studio-reached0-refused0]
FAILED tests/test_port_guard.py::test_a_run_pinning_stack_b_goes_ahead_only_under_stack_b_s_lease[studio-True]
FAILED tests/test_port_guard.py::test_a_run_pinning_stack_b_goes_ahead_only_under_stack_b_s_lease[None-True]
12 failed, 22 passed in 6.25s
FAILED tests/test_lanes_heartbeat.py::test_a_lease_older_than_its_limit_needs_you
FAILED tests/test_lanes_heartbeat.py::test_the_lanes_shown_by_default_are_the_six_of_amendment_3
FAILED tests/test_lanes_heartbeat.py::test_each_test_stack_is_shown_with_its_holder
FAILED tests/test_lanes_heartbeat.py::test_a_stack_b_lease_older_than_its_limit_needs_you
FAILED tests/test_lanes_launch.py::test_the_new_lanes_are_known[admin]
FAILED tests/test_lanes_launch.py::test_the_new_lanes_are_known[rules]
FAILED tests/test_lanes_launch.py::test_the_new_lanes_are_known[platform]
FAILED tests/test_lanes_launch.py::test_the_retired_glass_lane_is_refused
FAILED tests/test_lanes_launch.py::test_pausing_a_lane_holding_stack_b_releases_stack_b
FAILED tests/test_lanes_launch.py::test_an_unclean_pause_names_the_stack_still_held
10 failed, 34 passed in 20.04s
```

The first block is the lease and guard tests, the second the heartbeat and launcher tests. In the first,
the guard's start-up refusal for stack b printed its own inner run's pass (the run went ahead unrefused).

## Red: the guard planted to check one holder for both stacks

`holder = lease_holder(os.environ, stack)` replaced by `holder = lease_holder(os.environ)` in
`tests/port_guard.py` (stack a's holder checked for every stack), then restored:

```
FAILED tests/test_port_guard.py::test_each_stack_is_reached_only_by_its_own_holder[studio-reached0-refused0]
FAILED tests/test_port_guard.py::test_each_stack_is_reached_only_by_its_own_holder[rules-reached1-refused1]
2 failed, 18 deselected in 0.29s
```

## Green

`tests/test_lanes_heartbeat.py`, `test_lanes_launch.py`, `test_stack_lease.py` and `test_port_guard.py`: 80
passed. Two existing tests changed only their example: `test_headless_refuses_any_lane_but_docs` no longer
lists glass (now refused earlier, as an unknown lane), and the one-stack refusal became
`test_a_third_acquire_while_both_stacks_are_held_is_refused_and_names_both_holders`.

## Live, stack b

Under the lease "O-six: stack b smoke test" (orchestrator, stack b, 12:20Z): `up` started its four
containers; ArcadeDB on 2492 answered ready (204), Postgres on 55434 accepted connections and Valkey on
6380 answered PONG. The object store on 9002 had not answered when checked, so it is unproven. `down` and
`release` left both stacks free. Stack b's Postgres was given an empty `ospreyflow` database, which stack
a's holds and the tests default to, under the lease "O-six: create ospreyflow DB on stack b". The
containers were created from stack a's own images and settings (`docker inspect`), so no credential was
typed; stack b's ports are bound to 127.0.0.1 only.
