"""Render every profile but a declared cloud-platform from one tree (argv[1]) into argv[2], the
image tag (the checkout's HEAD, or 'unknown' with no .git) written as TAG."""
import copy, re, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path[:0] = [str(root / "OspreyFlow_Core"), str(root / "OspreyFlow_Core/packages"), str(root / "OspreyFlow_Build")]
import yaml
from harness.render import render
from tools.cp_policy_check import _resolver
from schemas.deployment import OspreyConfig
out = Path(sys.argv[2])
base = yaml.safe_load((root / "OspreyFlow_Build/tests/fixtures/deployment_v0_4_12/osprey.yaml").read_text())
configs = {"local-lite": base}
small = copy.deepcopy(base); small["profile"] = "small"; small["network"]["public_origin"] = "https://ospreyflow.example.org"
configs["small"] = small
cluster = {"profile": "cluster", "components": {"analytics_engine": "clickhouse"},
           "network": {"public_origin": "https://osprey.example.org"},
           "reporting": {"sync": True, "superset": True},
           "external": {"postgres": {"host": "db.example.internal"},
                        "valkey": {"host": "cache.example.internal", "port": 6380, "tls": True},
                        "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
                        "search": {"url": "https://search-osprey.eu-west-2.es.amazonaws.com"}},
           "cluster": {"shared_storage_class": "efs-sc"}}
configs["cluster"] = cluster
for fx in sorted((root / "OspreyFlow_Build/tests/fixtures/cloud_platform").glob("*.yaml")):
    if fx.stem != "development-sources":
        configs["cloud-platform-" + fx.stem] = yaml.safe_load(fx.read_text())
for name, raw in configs.items():
    d = out / name; d.mkdir(parents=True, exist_ok=True)
    try:
        arts = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts
    except Exception as e:
        (d / "REFUSED").write_text(f"{type(e).__name__}: {e}\n"); continue
    for k, v in arts.items():
        (d / k.replace("/", "_")).write_text(re.sub(r"(?<=:)([0-9a-f]{40}|unknown)\b", "TAG", v))
