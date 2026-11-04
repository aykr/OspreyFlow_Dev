"""The doctor's checks for the local engine on an NVIDIA GPU (`06_DECISIONS.md` ADR-135 Amendment 1
decision 4), before `install` or `apply` changes anything.

The stand-ins (`conftest.FakeProbes`) answer as the real ones do, refusals included (rule 15):
`nvidia-smi` not installed, `nvidia-smi` failing because it cannot reach the driver (exit 9), a
field it does not know (exit 2), and `docker info` listing only `runc` on a server without the
NVIDIA Container Toolkit. The real probe is run against stand-in programs on `PATH`.

What a mistake would do, and the case that catches it:
- an install going ahead on a server whose GPU Docker cannot reach, so Ollama starts on the CPU and
  nobody is told — `test_each_gpu_prerequisite_faked_absent_fails_in_words`, and
  `test_an_install_without_the_toolkit_is_refused_with_nothing_changed`;
- a GPU asked for on macOS or Windows, where Docker Desktop gives a container none — the same case;
- the Container Toolkit configured for CDI alone refused — `test_a_cdi_nvidia_device_is_enough`;
- a GPU too small for the 14b refusing the install rather than naming the 7b —
  `test_a_gpu_below_fourteen_gib_is_a_warning_naming_the_7b`;
- `apply` turning the GPU on past the same checks —
  `test_apply_onto_a_gpu_is_refused_with_nothing_changed_when_the_driver_is_not_loaded`;
- the command and the schema disagreeing on the extraction model a GPU runs —
  `test_the_command_reads_the_extraction_model_as_the_schema_does`;
- the real probe reading `nvidia-smi` wrongly — `test_the_real_probe_answers_as_nvidia_smi_does`.
"""

from __future__ import annotations

import platform
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from ospreyflow import doctor
from ospreyflow.doctor import Check, GpuPlan, SystemProbes, gpu_plan, run_doctor

from schemas.deployment import OspreyConfig

from .conftest import NVIDIA_SMI_NO_DRIVER, RUNTIMES_WITHOUT_TOOLKIT, FakeProbes, Rig

FOURTEEN = GpuPlan("qwen2.5:14b-instruct")
SEVEN = GpuPlan("qwen2.5:7b-instruct")


def _gpu_checks(probes: FakeProbes, tmp_path: Path, plan: GpuPlan = FOURTEEN) -> dict[str, Check]:
    checks = run_doctor("lite", probes, product=tmp_path, gpu=plan)
    return {c.name: c for c in checks if c.name.startswith("gpu")}


def test_a_gpu_server_with_its_driver_and_toolkit_passes_and_names_its_gpu(
    tmp_path: Path,
) -> None:
    probes = FakeProbes()
    checks = _gpu_checks(probes, tmp_path)
    assert sorted(checks) == ["gpu", "gpu-docker", "gpu-memory"]
    assert all(c.ok and not c.warn for c in checks.values())
    # The doctor prints the GPU's name and memory (16311 MiB is 15.9 GiB).
    assert "NVIDIA GeForce RTX 5060 Ti" in checks["gpu"].says
    assert "15.9 GiB" in checks["gpu"].says
    assert "595.99.02" in checks["gpu"].says
    assert "qwen2.5:14b-instruct" in checks["gpu-memory"].says


def _no_toolkit(probes: FakeProbes) -> None:
    assert probes.info is not None
    probes.info["Runtimes"] = dict(RUNTIMES_WITHOUT_TOOLKIT)


@pytest.mark.parametrize(
    ("name", "arrange", "words", "fix"),
    [
        ("gpu", lambda p: p.missing.add("nvidia-smi"), "nvidia-smi is not installed",
         "Install the NVIDIA driver"),
        ("gpu", lambda p: setattr(p, "driver_loaded", False),
         "couldn't communicate with the NVIDIA driver", "restart"),
        ("gpu-docker", _no_toolkit, "no nvidia runtime", "nvidia-ctk runtime configure"),
        ("gpu-host", lambda p: setattr(p, "system_name", "Darwin"), "macOS", "Linux"),
        ("gpu-host", lambda p: setattr(p, "system_name", "Windows"), "Windows", "Linux"),
    ],
    ids=["no-driver", "driver-not-loaded", "no-toolkit", "macos", "windows"],
)  # fmt: skip
def test_each_gpu_prerequisite_faked_absent_fails_in_words(
    tmp_path: Path, name: str, arrange: Callable[[FakeProbes], object], words: str, fix: str
) -> None:
    probes = FakeProbes()
    arrange(probes)
    checks = _gpu_checks(probes, tmp_path)
    assert [c.name for c in checks.values() if not c.ok] == [name]
    assert words in checks[name].says, checks[name].says
    assert fix in checks[name].fix, checks[name].fix


def test_on_macos_nothing_of_the_gpu_is_asked(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.system_name = "Darwin"
    _gpu_checks(probes, tmp_path)
    assert probes.nvidia_asked == []


def test_a_cdi_nvidia_device_is_enough(tmp_path: Path) -> None:
    """The Container Toolkit configured for CDI alone registers no runtime; Docker 28 lists the
    devices it discovered instead."""
    probes = FakeProbes()
    _no_toolkit(probes)
    assert probes.info is not None
    probes.info["DiscoveredDevices"] = [{"Source": "cdi", "ID": "nvidia.com/gpu=all"}]
    checks = _gpu_checks(probes, tmp_path)
    assert checks["gpu-docker"].ok
    assert "nvidia.com/gpu=all" in checks["gpu-docker"].says


@pytest.mark.parametrize(
    ("gpu", "mib", "shown"),
    [
        ("NVIDIA GeForce RTX 3060 Ti", 8192, "8.0 GiB"),
        ("NVIDIA GeForce RTX 3060", 12288, "12.0 GiB"),
    ],
)
def test_a_gpu_below_fourteen_gib_is_a_warning_naming_the_7b(
    tmp_path: Path, gpu: str, mib: int, shown: str
) -> None:
    """ADR-135 Amendment 1, as measured 4 November 2026: the 14b at 32k context with a q8_0 KV
    cache used 12.0 GiB of the GPU; 14 GiB is asked for, so a 12 GB card is a warning too."""
    probes = FakeProbes()
    probes.gpus = [(gpu, mib, "595.99.02")]
    checks = _gpu_checks(probes, tmp_path)
    memory = checks["gpu-memory"]
    assert memory.ok and memory.warn
    assert shown in memory.says and "14 GiB" in memory.says
    assert "qwen2.5:7b-instruct" in memory.fix
    # Named, the 7b asks for no memory check at all.
    assert "gpu-memory" not in _gpu_checks(probes, tmp_path, SEVEN)


def test_without_a_gpu_nothing_of_it_is_asked(tmp_path: Path) -> None:
    probes = FakeProbes()
    checks = run_doctor("lite", probes, product=tmp_path)
    assert not [c for c in checks if c.name.startswith("gpu")]
    assert probes.nvidia_asked == []


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"resources": {"gpu": "none"}},
        {"resources": {"gpu": "nvidia"}},
        {"resources": {"gpu": "nvidia"}, "models": {"extraction": "qwen2.5:7b-instruct"}},
        {"resources": {"gpu": "nvidia"}, "models": {"local_only": True}},
    ],
)
def test_the_command_reads_the_extraction_model_as_the_schema_does(raw: dict[str, Any]) -> None:
    """The command depends on PyYAML alone, so it reads `osprey.yaml` itself; it must reach the
    schema's own answer (`OspreyConfig.extraction_model`)."""
    plan = gpu_plan(raw)
    config = OspreyConfig.model_validate(raw)
    if config.resources.gpu == "nvidia":
        assert plan == GpuPlan(config.extraction_model)
    else:
        assert plan is None


def test_the_stand_in_refuses_as_nvidia_smi_and_docker_do() -> None:
    """Rule 15: the stand-in is trusted only once it is shown refusing what the real ones refuse."""
    probes = FakeProbes()
    assert probes.nvidia_smi(["--query-gpu=name,memory.total", "--format=csv,noheader"]) == (
        0, "NVIDIA GeForce RTX 5060 Ti, 16311 MiB\n")  # fmt: skip
    assert probes.nvidia_smi(["--query-gpu=name,vram", "--format=csv"])[0] == 2  # type: ignore[index]
    probes.driver_loaded = False
    assert probes.nvidia_smi(doctor.NVIDIA_SMI_QUERY) == (9, NVIDIA_SMI_NO_DRIVER)
    probes.missing.add("nvidia-smi")
    assert probes.nvidia_smi(doctor.NVIDIA_SMI_QUERY) is None
    _no_toolkit(probes)
    assert probes.info is not None
    assert "nvidia" not in probes.info["Runtimes"]  # type: ignore[operator]


# ---- through the command: doctor, install, apply ------------------------------------------------

SERVER = {
    "address": "https://osprey.example.internal",
    "certificate": "/etc/ospreyflow/tls/osprey.crt",
    "key": "/etc/ospreyflow/tls/osprey.key",
    "gpu": "nvidia",
}


def _answers(tmp_path: Path, **server: object) -> Path:
    path = tmp_path / "install.yaml"
    answers = {"mode": "small", "server": {**SERVER, **server}, "components": {"dashboards": False}}
    path.write_text(yaml.safe_dump(answers), encoding="utf-8")
    return path


def test_the_doctor_checks_the_gpu_the_answers_ask_for(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("doctor", "--mode", "small", "--config", str(_answers(tmp_path))) == 0
    out = capsys.readouterr().out
    assert "NVIDIA GeForce RTX 5060 Ti" in out and "15.9 GiB" in out
    _no_toolkit(rig.probes)
    assert rig("doctor", "--mode", "small", "--config", str(_answers(tmp_path))) == 1
    # Without server.gpu, nothing of the GPU is asked.
    rig.probes.nvidia_asked.clear()
    assert rig("doctor", "--mode", "small", "--config", str(_answers(tmp_path, gpu="none"))) == 0
    assert rig.probes.nvidia_asked == []


def test_the_doctor_checks_the_gpu_lites_osprey_yaml_asks_for(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    config = rig.config()
    (rig.product / "osprey.yaml").write_text(
        yaml.safe_dump({**config, "resources": {"gpu": "nvidia"}}), encoding="utf-8"
    )
    rig.probes.system_name = "Darwin"
    assert rig("doctor") == 1
    assert "macOS" in capsys.readouterr().out


def test_an_install_without_the_toolkit_is_refused_with_nothing_changed(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (rig.product / "osprey.yaml").read_bytes()
    _no_toolkit(rig.probes)
    assert rig("install", "--mode", "small", "--config", str(_answers(tmp_path)), "--force") == 1
    out = capsys.readouterr().out
    assert "nvidia-ctk runtime configure" in out
    assert "Nothing was installed" in out
    assert rig.runner.argvs() == []
    assert (rig.product / "osprey.yaml").read_bytes() == before


def test_an_install_on_a_small_gpu_warns_and_writes_the_gpu(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.probes.gpus = [("NVIDIA GeForce RTX 3060 Ti", 8192, "595.99.02")]
    assert rig("install", "--mode", "small", "--config", str(_answers(tmp_path)), "--force") == 0
    assert "qwen2.5:7b-instruct" in capsys.readouterr().out
    assert rig.config()["resources"] == {"gpu": "nvidia"}


def _gpu_osprey_yaml(rig: Rig) -> None:
    rig.install_deployment()
    config = rig.config()
    (rig.product / "osprey.yaml").write_text(
        yaml.safe_dump({**config, "resources": {"gpu": "nvidia"}}), encoding="utf-8"
    )


def test_apply_onto_a_gpu_is_refused_with_nothing_changed_when_the_driver_is_not_loaded(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _gpu_osprey_yaml(rig)
    rig.probes.driver_loaded = False
    assert rig("apply") == 1
    out = capsys.readouterr().out
    assert NVIDIA_SMI_NO_DRIVER.split(".")[0] in out
    assert "Nothing was changed" in out
    assert rig.runner.argvs() == []


def test_apply_onto_a_gpu_that_is_ready_applies(rig: Rig) -> None:
    _gpu_osprey_yaml(rig)
    assert rig("apply") == 0
    assert len(rig.runner.with_word("--reapply")) == 1


# ---- the real probe ---------------------------------------------------------------------------


def _program(folder: Path, name: str, script: str) -> None:
    program = folder / name
    program.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    program.chmod(0o755)


def test_the_real_probe_answers_as_nvidia_smi_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`SystemProbes.nvidia_smi` against stand-in programs on `PATH`: none there; one failing as the
    real one does without its driver (exit 9); one answering as the test server's did."""
    monkeypatch.setenv("PATH", str(tmp_path))
    probes = SystemProbes()
    assert probes.nvidia_smi(doctor.NVIDIA_SMI_QUERY) is None
    message = NVIDIA_SMI_NO_DRIVER.strip()
    _program(tmp_path, "nvidia-smi", f'echo "{message}"\nexit 9')
    assert probes.nvidia_smi(doctor.NVIDIA_SMI_QUERY) == (9, message + "\n")
    _program(tmp_path, "nvidia-smi", 'echo "$@" > "$0.args"\n'
             "echo 'NVIDIA GeForce RTX 5060 Ti, 16311, 595.99.02'")  # fmt: skip
    assert probes.nvidia_smi(doctor.NVIDIA_SMI_QUERY) == (
        0, "NVIDIA GeForce RTX 5060 Ti, 16311, 595.99.02\n")  # fmt: skip
    asked = (tmp_path / "nvidia-smi.args").read_text(encoding="utf-8").split()
    assert asked == list(doctor.NVIDIA_SMI_QUERY)
    assert probes.system() == platform.system()
