"""A start needs no network once the product is installed (slice NW1, 20 November 2026).

The two one-shot jobs that fetch model weights, `ollama-models` and `whisper-models`, ran their
download on every start: `ollama pull` for each model with no check before it, and
`huggingface-cli download` with no offline flag. `docker compose up -d --wait` counts a job that exits
non-zero as a failed start, so a machine that already held every weight but had no network failed to
start. These tests render the local-lite compose, take each job's script exactly as rendered, and run
it under `sh` with a PATH of stubs on which every pull and download is refused.

What the stubs model is the real tools' refusals, each measured on 20 November 2026 in the pinned
images (`ollama/ollama:0.18.2`, `ghcr.io/speaches-ai/speaches:0.8.3-cpu`) run with `--network none`:

* `ollama pull` of a model that is absent fails with `Error: pull model manifest: Get
  "https://registry.ollama.ai/...": dial tcp: lookup registry.ollama.ai ...: network is unreachable`.
  `ollama pull` of a model that is **present** fails the same way: it asks the registry for the
  manifest first, so it is not an offline check. `ollama list` needs only the local server and
  prints `NAME ID SIZE MODIFIED` and one row per model held.
* `huggingface-cli download <repo>` with the hub unreachable still returns the cached snapshot when
  there is one (it exits 0, after trying the network), and exits 1 with `LocalEntryNotFoundError`
  when there is none. With `HF_HUB_OFFLINE=1` it never tries the network: exit 0 on a cached
  snapshot, exit 1 with `LocalEntryNotFoundError ... outgoing traffic has been disabled` without.

A stub call that reaches for the network is logged with the word `NETWORK`; "no network needed" is
that no such line is logged. `sleep infinity` is stubbed to return, because reaching it is how the
`ollama-models` job reports that it is up and idle (`exec sleep infinity` ends its script).
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.render import render

from schemas.deployment import OspreyConfig
from tests.harness.test_render import _fake_resolver

_OLLAMA_STUB = r"""#!/bin/sh
root="$NW_OLLAMA_VOLUME/models/manifests/registry.ollama.ai/library"
case "$1" in
serve)
  # A server that outlives a failed job must not hold the job's pipes open.
  exec /bin/sleep 30 >/dev/null 2>&1 ;;
list)
  echo "NAME    ID    SIZE    MODIFIED"
  for f in "$root"/*/*; do
    [ -f "$f" ] || continue
    echo "$(basename "$(dirname "$f")"):$(basename "$f")  $(cat "$f")  1 GB  1 day ago"
  done ;;
pull)
  echo "NETWORK ollama pull $2" >> "$NW_LOG"
  served="$(awk -v m="$2" '$1 == m {print $2}' "$NW_REGISTRY" 2>/dev/null)"
  if [ -z "$served" ]; then
    echo "Error: pull model manifest: Get \"https://registry.ollama.ai/v2/library/${2%%:*}/manifests/${2#*:}\": dial tcp: lookup registry.ollama.ai: network is unreachable" >&2
    exit 1
  fi
  name="${2%%:*}"; tag="${2#*:}"
  mkdir -p "$root/$name" && echo "$served" > "$root/$name/$tag" ;;
*) echo "stub: unmodelled ollama $*" >&2; exit 2 ;;
esac
"""

_HF_STUB = r"""#!/bin/sh
[ "$1" = download ] || { echo "stub: unmodelled huggingface-cli $*" >&2; exit 2; }
shift
asked="$*"
force=0
if [ "$1" = --force-download ]; then force=1; shift; fi
repo="$NW_HF_CACHE/hub/models--$(echo "$1" | sed 's,/,--,')"
snapshots="$repo/snapshots"
# Measured: the tool never checks that the snapshot's files are there. A ref that names a snapshot
# folder that exists is a cache hit, whether the folder is full, partly filled or empty.
held() { [ -f "$repo/refs/main" ] && [ -d "$snapshots/$(cat "$repo/refs/main")" ]; }
if [ "$HF_HUB_OFFLINE" = 1 ]; then
  echo "local huggingface-cli download $1 (HF_HUB_OFFLINE=1)" >> "$NW_LOG"
  if [ "$force" = 1 ]; then echo "ValueError: Cannot pass 'force_download=True' when offline mode is enabled." >&2; exit 1; fi
  if held; then echo "$snapshots/$(cat "$repo/refs/main")"; exit 0; fi
  echo "huggingface_hub.errors.LocalEntryNotFoundError: Cannot find an appropriate cached snapshot folder for the specified revision on the local disk and outgoing traffic has been disabled." >&2
  exit 1
fi
echo "NETWORK huggingface-cli download $asked" >> "$NW_LOG"
if [ "$NW_HF_REACHABLE" = 1 ]; then
  # Read in huggingface_hub 0.33.4 (`file_download.py`, lines 1066, 1148 and 1152): online, a file
  # whose snapshot entry or blob already exists, at any length, is returned as it is. Only
  # `--force-download` replaces it. A half-written blob is cleared only when its own file is fetched
  # again, and a stray one is never touched.
  mkdir -p "$repo/refs" "$repo/blobs" "$snapshots/0123abc"
  echo 0123abc > "$repo/refs/main"
  for f in config.json model.bin tokenizer.json vocabulary.txt; do
    if [ "$force" = 1 ] || [ ! -e "$snapshots/0123abc/$f" ]; then echo "$f" > "$snapshots/0123abc/$f"; fi
  done
  echo "$snapshots/0123abc"; exit 0
fi
if [ "$force" = 1 ]; then
  echo "huggingface_hub.errors.LocalEntryNotFoundError: An error happened while trying to locate the file on the Hub and we cannot find the requested files in the local cache. Please check your connection and try again or make sure your Internet connection is on." >&2
  exit 1
fi
# Measured: with the hub unreachable it falls back to the cache, whatever the cache holds, and
# exits 0; only with nothing cached does it fail.
if held; then echo "$snapshots/$(cat "$repo/refs/main")"; exit 0; fi
echo "huggingface_hub.errors.LocalEntryNotFoundError: An error happened while trying to locate the files on the Hub and we cannot find the appropriate snapshot folder for the specified revision on the local disk. Please check your internet connection and try again." >&2
exit 1
"""

_SLEEP_STUB = r"""#!/bin/sh
if [ "$1" = infinity ]; then echo "idle" >> "$NW_LOG"; exit 0; fi
exec /bin/sleep "$@"
"""

_CHOWN_STUB = r"""#!/bin/sh
echo "chown $*" >> "$NW_LOG"
"""

_HF_CACHE_IN_THE_JOB = "/home/ubuntu/.cache/huggingface"
#: What the speech library requires of a model's snapshot (`faster_whisper.utils.download_model`'s
#: `allow_patterns`, read in the pinned image; `vocabulary.*` is `vocabulary.txt` for the repo used).
FORCED_FETCH_PREFIX = "NETWORK huggingface-cli download --force-download "
SPEECH_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


def _local_lite_jobs() -> tuple[str, str, str]:
    """The two jobs' scripts exactly as rendered for local-lite, with compose's `$$` turned into the
    `$` the shell inside the container receives, and the speech model's name."""
    config = OspreyConfig.model_validate({"profile": "local-lite"})
    compose = yaml.safe_load(render(config, resolver=_fake_resolver).artefacts["compose.yaml"])
    services = compose["services"]
    ollama = services["ollama-models"]
    whisper = services["whisper-models"]
    assert ollama["entrypoint"] == ["/bin/sh", "-c"] and whisper["entrypoint"] == ["/bin/sh", "-c"]
    return (
        ollama["command"][0].replace("$$", "$"),
        whisper["command"][0].replace("$$", "$"),
        config.models.transcription,
    )


OLLAMA_JOB, WHISPER_JOB, SPEECH_MODEL = _local_lite_jobs()
FORCED_FETCH = f"{FORCED_FETCH_PREFIX}{SPEECH_MODEL}"
#: (model, the id a deployment records for it): read from the rendered script, not restated.
MODELS = re.findall(r"^pull_and_verify (\S+) (\S+)$", OLLAMA_JOB, re.M)


def _write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class _Machine:
    """A temporary directory laid out as the two model volumes, a PATH of stubs, and a call log."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.ollama_volume = tmp_path / "ollama"
        self.hf_cache = tmp_path / "huggingface"
        self.hf_cache.mkdir()
        self.registry = tmp_path / "registry"  # what a reachable registry would serve
        self.log = tmp_path / "calls.log"
        self.log.write_text("", encoding="utf-8")
        stubs = tmp_path / "bin"
        stubs.mkdir()
        _write_stub(stubs, "ollama", _OLLAMA_STUB)
        _write_stub(stubs, "huggingface-cli", _HF_STUB)
        _write_stub(stubs, "sleep", _SLEEP_STUB)
        _write_stub(stubs, "chown", _CHOWN_STUB)
        self.stubs = stubs
        self.hf_reachable = False

    def hold_ollama_model(self, model: str, model_id: str) -> None:
        name, tag = model.split(":", 1)
        folder = self.ollama_volume / "models/manifests/registry.ollama.ai/library" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / tag).write_text(model_id, encoding="utf-8")

    def hold_every_ollama_model(self) -> None:
        for model, model_id in MODELS:
            self.hold_ollama_model(model, model_id)

    def hold_speech_model(
        self,
        *,
        without: tuple[str, ...] = (),
        empty: tuple[str, ...] = (),
        incomplete: bool = False,
    ) -> None:
        """The cache as the real tool lays it out: a ref, a snapshot folder with the model's files
        (`faster_whisper.utils` requires these), and the blobs. `without` leaves files out, `empty`
        leaves them as zero-length files, `incomplete` leaves a half-written blob, as a download
        cut short does."""
        repo = self.hf_cache / "hub" / f"models--{SPEECH_MODEL.replace('/', '--')}"
        snapshot = repo / "snapshots/0123abc"
        snapshot.mkdir(parents=True)
        (repo / "blobs").mkdir()
        (repo / "refs").mkdir()
        (repo / "refs/main").write_text("0123abc", encoding="utf-8")
        for name in SPEECH_FILES:
            if name not in without:
                (snapshot / name).write_bytes(b"" if name in empty else b"x")
        if incomplete:
            (repo / "blobs/9f8e7d.incomplete").write_bytes(b"x")

    def speech_model_is_complete(self) -> bool:
        repo = self.hf_cache / "hub" / f"models--{SPEECH_MODEL.replace('/', '--')}"
        snapshot = repo / "snapshots/0123abc"
        files_held = all(
            (snapshot / name).is_file() and (snapshot / name).stat().st_size
            for name in SPEECH_FILES
        )
        return files_held and not list((repo / "blobs").glob("*.incomplete"))

    def registry_serves(self, model: str, model_id: str) -> None:
        with self.registry.open("a", encoding="utf-8") as handle:
            handle.write(f"{model} {model_id}\n")

    def run(self, script: str) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": f"{self.stubs}:/usr/bin:/bin",
            "NW_LOG": str(self.log),
            "NW_OLLAMA_VOLUME": str(self.ollama_volume),
            "NW_HF_CACHE": str(self.hf_cache),
            "NW_REGISTRY": str(self.registry),
            "NW_HF_REACHABLE": "1" if self.hf_reachable else "0",
        }
        (self.ollama_volume / "models").mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            ["/bin/sh", "-c", script.replace(_HF_CACHE_IN_THE_JOB, str(self.hf_cache))],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def network_calls(self) -> list[str]:
        return [line for line in self.calls() if line.startswith("NETWORK")]


@pytest.fixture
def machine(tmp_path: Path) -> _Machine:
    return _Machine(tmp_path)


def _said(result: subprocess.CompletedProcess[str]) -> str:
    return " ".join(result.stderr.split()).lower()


def _says_what_to_do(result: subprocess.CompletedProcess[str], missing: str) -> None:
    """In words, as an operator reads them: what is missing, that the network is needed once, and
    what to do (connect and start again). Not the tool's own traceback."""
    said = _said(result)
    assert missing.lower() in said, result.stderr
    assert "needs the network once" in said, result.stderr
    assert "start again" in said, result.stderr


def test_the_rendered_jobs_are_the_ones_this_file_means_to_run() -> None:
    """The scripts are read from the real render, so a model added or removed is followed, and the
    check below that every model is held is not vacuous."""
    assert len(MODELS) >= 3
    assert "ollama pull" in OLLAMA_JOB and "huggingface-cli download" in WHISPER_JOB
    assert SPEECH_MODEL in WHISPER_JOB
    assert "$$" not in OLLAMA_JOB and "$$" not in WHISPER_JOB


# --- Case A: everything is already on the machine, every pull is refused ----------------------


def test_the_model_job_with_every_model_held_starts_without_the_network(
    machine: _Machine,
) -> None:
    machine.hold_every_ollama_model()
    result = machine.run(OLLAMA_JOB)
    assert result.returncode == 0, result.stderr
    assert machine.network_calls() == []
    assert machine.calls() == ["idle"], "the job should reach its idle state and nothing else"


def test_the_speech_job_with_the_model_held_starts_without_the_network(
    machine: _Machine,
) -> None:
    machine.hold_speech_model()
    result = machine.run(WHISPER_JOB)
    assert result.returncode == 0, result.stderr
    assert machine.network_calls() == []
    # It asked the cache, offline, and then did what the job always does to the volume.
    assert machine.calls()[0] == (
        f"local huggingface-cli download {SPEECH_MODEL} (HF_HUB_OFFLINE=1)"
    )
    assert any(line.startswith("chown -R 1000:1000") for line in machine.calls())


# --- Case B: something is absent and the pull is refused --------------------------------------


@pytest.mark.parametrize("absent", [model for model, _ in MODELS])
def test_a_missing_model_with_the_pull_refused_fails_in_words_and_pulls_only_that_model(
    machine: _Machine, absent: str
) -> None:
    for model, model_id in MODELS:
        if model != absent:
            machine.hold_ollama_model(model, model_id)
    result = machine.run(OLLAMA_JOB)
    assert result.returncode != 0
    assert machine.calls() == [f"NETWORK ollama pull {absent}"]
    _says_what_to_do(result, absent)


def test_a_model_held_at_another_digest_is_pulled_and_a_refused_pull_says_so_in_words(
    machine: _Machine,
) -> None:
    machine.hold_every_ollama_model()
    stale, _ = MODELS[0]
    machine.hold_ollama_model(stale, "000000000000")
    result = machine.run(OLLAMA_JOB)
    assert result.returncode != 0
    assert machine.calls() == [f"NETWORK ollama pull {stale}"]
    _says_what_to_do(result, stale)


def test_a_missing_speech_model_with_the_hub_refused_fails_in_words(machine: _Machine) -> None:
    result = machine.run(WHISPER_JOB)
    assert result.returncode != 0
    assert not any(line.startswith("chown") for line in machine.calls())
    _says_what_to_do(result, SPEECH_MODEL)


# --- A speech model cut short: the folder is there, the weights are not -----------------------

#: Each way a first download leaves the cache when it is interrupted: the snapshot's folder and
#: ref are written before the weights arrive, so the tool's own offline check still says "held".
INTERRUPTED = {
    "no weights": {"without": ("model.bin",)},
    "no vocabulary": {"without": ("vocabulary.txt",)},
    "no tokenizer": {"without": ("tokenizer.json",)},
    "weights of zero length": {"empty": ("model.bin",)},
    "a blob left half-written": {"incomplete": True},
}


@pytest.mark.parametrize("how", INTERRUPTED)
def test_the_stub_calls_a_cut_short_cache_a_hit_as_the_real_tool_does(
    machine: _Machine, how: str
) -> None:
    """Rule 15's second worked example: if the stub refused a partial cache, the cases below would
    show nothing. Measured in the pinned image: the offline tool exits 0 on a ref and a snapshot
    folder with no files, and the online tool with the hub unreachable does too."""
    machine.hold_speech_model(**INTERRUPTED[how])
    assert not machine.speech_model_is_complete()
    env = {"PATH": f"{machine.stubs}:/usr/bin:/bin", "NW_LOG": str(machine.log)}
    env |= {"NW_HF_CACHE": str(machine.hf_cache), "NW_HF_REACHABLE": "0"}
    for extra in ({"HF_HUB_OFFLINE": "1"}, {}):
        found = subprocess.run(
            ["huggingface-cli", "download", SPEECH_MODEL],
            env=env | extra,
            capture_output=True,
            text=True,
            check=False,
        )
        assert found.returncode == 0, found.stderr


@pytest.mark.parametrize("how", ["weights of zero length", "a blob left half-written"])
def test_the_stub_does_not_repair_online_what_the_real_tool_leaves_as_it_is(
    machine: _Machine, how: str
) -> None:
    """Rule 15, second worked example (round 3's finding). Read in `huggingface_hub` 0.33.4: a
    snapshot file that exists is returned without a fetch, even at zero length, and a stray
    half-written blob is never cleared. A stub that mended these would let the job's check pass
    while the product's check still failed after a real download. Only `--force-download` replaces."""
    machine.hold_speech_model(**INTERRUPTED[how])
    machine.hf_reachable = True
    env = {"PATH": f"{machine.stubs}:/usr/bin:/bin", "NW_LOG": str(machine.log)}
    env |= {"NW_HF_CACHE": str(machine.hf_cache), "NW_HF_REACHABLE": "1"}
    plain = subprocess.run(
        ["huggingface-cli", "download", SPEECH_MODEL],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert plain.returncode == 0, plain.stderr
    assert not machine.speech_model_is_complete()
    forced = subprocess.run(
        ["huggingface-cli", "download", "--force-download", SPEECH_MODEL],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert forced.returncode == 0, forced.stderr
    # Forcing replaces the files; a stray blob is still the job's to remove.
    assert machine.speech_model_is_complete() == (how == "weights of zero length")


def test_the_stub_refuses_a_forced_download_with_the_hub_unreachable(machine: _Machine) -> None:
    """The real tool raises when it cannot reach the hub and is told to fetch again."""
    machine.hold_speech_model()
    env = {"PATH": f"{machine.stubs}:/usr/bin:/bin", "NW_LOG": str(machine.log)}
    env |= {"NW_HF_CACHE": str(machine.hf_cache), "NW_HF_REACHABLE": "0"}
    forced = subprocess.run(
        ["huggingface-cli", "download", "--force-download", SPEECH_MODEL],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert forced.returncode == 1 and "LocalEntryNotFoundError" in forced.stderr


@pytest.mark.parametrize("how", INTERRUPTED)
def test_a_speech_model_cut_short_is_fetched_when_the_hub_is_reachable(
    machine: _Machine, how: str
) -> None:
    machine.hold_speech_model(**INTERRUPTED[how])
    machine.hf_reachable = True
    result = machine.run(WHISPER_JOB)
    assert result.returncode == 0, result.stderr
    # Not the plain call: the real tool leaves a zero-length file and a stray blob as they are.
    assert machine.network_calls() == [FORCED_FETCH]
    assert machine.speech_model_is_complete()
    assert any(line.startswith("chown -R 1000:1000") for line in machine.calls())


@pytest.mark.parametrize("how", [how for how in INTERRUPTED if how != "a blob left half-written"])
def test_a_speech_model_cut_short_with_the_hub_refused_fails_in_words(
    machine: _Machine, how: str
) -> None:
    """Not a start that reports success and leaves `whisper` unable to load its model."""
    machine.hold_speech_model(**INTERRUPTED[how])
    result = machine.run(WHISPER_JOB)
    assert result.returncode != 0
    assert not any(line.startswith("chown") for line in machine.calls())
    _says_what_to_do(result, SPEECH_MODEL)


def test_a_stray_half_written_blob_beside_a_whole_model_is_cleared_and_the_hub_is_not_needed(
    machine: _Machine,
) -> None:
    """Every file the speech library requires is there, so the model is whole and the network
    cannot add to it: the job removes the stray blob (which the real tool never would) and starts,
    rather than failing with advice to connect that could never help."""
    machine.hold_speech_model(incomplete=True)
    result = machine.run(WHISPER_JOB)
    assert result.returncode == 0, result.stderr
    assert machine.speech_model_is_complete()
    assert any(line.startswith("chown -R 1000:1000") for line in machine.calls())


# --- A first install, with the network, still works and still checks the digest ---------------


def test_a_first_install_fetches_every_model_and_the_speech_model(machine: _Machine) -> None:
    for model, model_id in MODELS:
        machine.registry_serves(model, model_id)
    machine.hf_reachable = True
    first = machine.run(OLLAMA_JOB)
    assert first.returncode == 0, first.stderr
    assert machine.network_calls() == [f"NETWORK ollama pull {model}" for model, _ in MODELS]
    second = machine.run(WHISPER_JOB)
    assert second.returncode == 0, second.stderr
    assert FORCED_FETCH in machine.network_calls()


def test_the_digest_is_still_checked_after_a_pull_that_happens(machine: _Machine) -> None:
    """ADR-020: a tag that moved upstream fails loudly rather than silently changing the model."""
    machine.hold_every_ollama_model()
    moved, expected = MODELS[0]
    machine.hold_ollama_model(moved, "000000000000")
    machine.registry_serves(moved, "ffffffffffff")
    result = machine.run(OLLAMA_JOB)
    assert result.returncode != 0
    assert machine.calls() == [f"NETWORK ollama pull {moved}"]
    said = _said(result)
    assert f"resolved to manifest ffffffffffff, expected {expected}" in said, result.stderr


def test_a_model_held_at_the_wrong_digest_is_repaired_by_a_pull_that_serves_the_right_one(
    machine: _Machine,
) -> None:
    machine.hold_every_ollama_model()
    stale, expected = MODELS[0]
    machine.hold_ollama_model(stale, "000000000000")
    machine.registry_serves(stale, expected)
    result = machine.run(OLLAMA_JOB)
    assert result.returncode == 0, result.stderr
    assert machine.calls() == [f"NETWORK ollama pull {stale}", "idle"]


def test_the_stubs_refuse_what_the_real_tools_refuse(machine: _Machine) -> None:
    """Rule 15, second worked example: a stub that grants what the real tool refuses shows nothing.
    So the stubs are held to the measured refusals before the cases above are trusted."""
    env: dict[str, Any] = {**os.environ, "PATH": f"{machine.stubs}:/usr/bin:/bin"}
    env.update(
        NW_LOG=str(machine.log),
        NW_OLLAMA_VOLUME=str(machine.ollama_volume),
        NW_HF_CACHE=str(machine.hf_cache),
        NW_REGISTRY=str(machine.registry),
        NW_HF_REACHABLE="0",
    )
    (machine.ollama_volume / "models").mkdir(parents=True)
    machine.hold_ollama_model("qwen2.5:0.5b-instruct", "a8b0c5157701")
    # A present model is still refused: `ollama pull` is not an offline check.
    pull = subprocess.run(
        ["ollama", "pull", "qwen2.5:0.5b-instruct"], env=env, capture_output=True, text=True
    )
    assert pull.returncode == 1 and "registry.ollama.ai" in pull.stderr
    # Offline, an absent snapshot is a failure; online with no network and none held, too.
    offline = {**env, "HF_HUB_OFFLINE": "1"}
    absent = ["huggingface-cli", "download", SPEECH_MODEL]
    assert subprocess.run(absent, env=offline, capture_output=True, text=True).returncode == 1
    assert subprocess.run(absent, env=env, capture_output=True, text=True).returncode == 1
