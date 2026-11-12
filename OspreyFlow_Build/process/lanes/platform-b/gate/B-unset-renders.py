"""gate-b: every profile's and fixture's render, as SHA-256 per artefact, for comparing main's code
with the branch's (nothing changes for a deployment that sets neither banner_text nor access_key).
Run with PYTHONPATH naming the tree to render with; prints JSON."""

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml
from harness.render import render

from schemas.deployment import OspreyConfig

BUILD = Path(sys.argv[1])
FIXTURES = [Path(p) for p in sys.argv[2:]]
ORIGIN = "https://demo.example.org"
STAMP = re.compile(r"\b[0-9a-f]{40}\b|\bv?\d+\.\d+\.\d+-\d+-g[0-9a-f]{7,}\b|\b[0-9a-f]{7,12}\b")
SYNTHETIC = {
    "default (local-lite)": {},
    "small": {"profile": "small", "network": {"public_origin": ORIGIN}},
    "small, govuk beta": {"profile": "small", "network": {"public_origin": ORIGIN},
                          "appearance": {"brand": "govuk", "service_name": "Demo", "phase": "beta",
                                         "organisation": "UK Public Sector Org"}},
    "small, own tls, redirect, superset": {
        "profile": "small",
        "network": {"public_origin": ORIGIN, "redirect_http": True,
                    "tls": {"certificate": "/etc/osprey/cert.pem", "key": "/etc/osprey/key.pem"}},
        "reporting": {"superset": True}},
    "local-lite, govuk alpha": {"appearance": {"brand": "govuk", "phase": "alpha"}},
}
out = {}
cases = {name: raw for name, raw in SYNTHETIC.items()}
for path in FIXTURES:
    cases[str(path)] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
for name, raw in cases.items():
    try:
        config = OspreyConfig.model_validate(raw)
        artefacts = render(config, allow_unpinned=True).artefacts
        # Each tree's own commit is in its image tags and version stamp; nothing else may differ.
        out[name] = {
            k: hashlib.sha256(STAMP.sub("<commit>", v).encode()).hexdigest()
            for k, v in sorted(artefacts.items())
        }
    except Exception as refused:  # noqa: BLE001 - recorded, compared like any answer
        out[name] = {"refused": f"{type(refused).__name__}: {str(refused)[:200]}"}
print(json.dumps(out, indent=1, sort_keys=True))
