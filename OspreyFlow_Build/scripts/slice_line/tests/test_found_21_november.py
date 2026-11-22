"""Found on 21 November while applying the owner's lines (LINE_FIXES_5_BRIEF.md, 8.1, 8.2 and 8.4).

8.1: `records` refused any commit while slices.tsv differed in a started slice's frozen checks, and `resume.py refreeze`
refused unless the main checkout differed from main in slices.tsv alone: each waited for the other. Now records ignores
a slices.tsv change that an unapplied refreeze line covers (and will not commit slices.tsv itself then), and the
refreeze leaves other uncommitted briefs under slices/ as they are. 8.2: clear-stop is refused while an unapplied
refreeze line for the slice waits. 8.4: add-round on a slice refused by the gate names send-back as the action.
"""
from __future__ import annotations

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_resume import TODAY, V062, at_limit, changes, owner_line, red_stopped, resume, said_refused, set_state, state

BRIEF = f"{V062}/slices/S1.md"


def records(w, *paths):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), "records", "-m", "docs(process): briefs", *paths],
              w["repo"], w["env"], check=False)


def waiting_refreeze(w):
    """S1 started; its brief committed then edited again; its checks changed in the working slices.tsv."""
    r = w["repo"]
    (r / BRIEF).parent.mkdir(parents=True, exist_ok=True)
    (r / BRIEF).write_text("the brief\n")
    sh(f"git add {BRIEF} && git commit -qm 'docs: brief' --trailer 'Slice-Records: yes'", r, w["env"])
    at_limit(w)
    (r / BRIEF).write_text("the brief, corrected\n")
    tsv = r / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("\tsh accept.sh\ttrue\n", "\tsh accept.sh\ttrue && echo more\n", 1))


def test_records_commits_a_brief_while_a_covered_refreeze_waits(world):
    w = world
    waiting_refreeze(w)
    p = records(w, BRIEF)
    assert p.returncode == 1 and "needs the owner" in p.stderr, p.stderr  # no line yet: refused as before
    owner_line(w, f"S1\trefreeze\t{TODAY}")
    p = records(w, BRIEF)
    assert p.returncode == 0 and "\nCommitted " in "\n" + p.stdout, p.stdout + p.stderr
    assert f"{V062}/slices.tsv" in sh("git status --porcelain --untracked-files=no", w["repo"]).stdout  # left for the refreeze
    p = records(w, f"{V062}/slices.tsv")
    assert p.returncode == 1 and "waits for the owner's refreeze of S1" in p.stderr, p.stderr


def test_the_refreeze_leaves_other_uncommitted_briefs_as_they_are(world):
    w = world
    waiting_refreeze(w)
    owner_line(w, f"S1\trefreeze\t{TODAY}")
    p = resume(w, "S1", "refreeze")
    assert p.returncode == 0, p.stdout + p.stderr
    assert sh("git show --name-only --format= HEAD", w["repo"]).stdout.split() == [f"{V062}/slices.tsv"]
    assert (w["repo"] / BRIEF).read_text() == "the brief, corrected\n"  # still the conductor's, uncommitted


def test_clear_stop_waits_for_a_waiting_refreeze(world):
    w = world
    red_stopped(w)
    owner_line(w, f"S1\tclear-stop\t{TODAY}", f"S1\trefreeze\t{TODAY}")
    p = resume(w, "S1", "clear-stop")
    assert said_refused(p, "refreeze line for S1 is waiting", "apply it first"), p.stderr
    assert state(w)["phase"] == "stopped" and changes(w) == []


def test_add_round_on_a_slice_refused_by_the_gate_names_send_back(world):
    w = world
    at_limit(w)
    set_state(w, phase="refused", refused_for="gate", refused_tests=1)
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    p = resume(w, "S1", "add-round")
    assert said_refused(p, "send-back", "not used"), p.stderr
    assert changes(w) == []
    p = resume(w, "S1", "send-back")  # the line is still there for send-back to use past the limit
    assert p.returncode == 0, p.stdout + p.stderr
