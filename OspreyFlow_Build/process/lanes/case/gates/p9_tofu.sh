#!/usr/bin/env bash
# backups.tf through OpenTofu (the orchestrator's minor item): `fmt -check`, and `validate` with the rendered folder's
# other files (they declare local.prefix and the variables backups.tf uses) and a providers block of its own, since
# the environments repository's folder holds the real one. Run on the server through stack_lease.sh offline, from
# OspreyFlow_Core; Docker for the pinned OpenTofu image the Makefile uses.
set -euo pipefail
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
PYTHONPATH=.:packages:../OspreyFlow_Build .venv/bin/python - "$W" <<'PY'
import sys
from pathlib import Path
from tests.cloud_platform_backup import rendered
out = Path(sys.argv[1])
for name, text in rendered.artefacts().items():
    if name.startswith("terraform/"):
        (out / name.removeprefix("terraform/")).write_text(text)
(out / "backups.tf").write_text(rendered.terraform())
(out / "providers.tf").write_text(
    'terraform {\n  required_providers {\n    aws = { source = "hashicorp/aws" }\n'
    '    kubernetes = { source = "hashicorp/kubernetes" }\n  }\n}\n'
    'provider "aws" {\n  region = "eu-west-2"\n}\n')
print("rendered:", ", ".join(sorted(p.name for p in out.iterdir())))
PY
TOFU_IMAGE=$(grep -E '^TOFU :=' ../OspreyFlow_Build/Makefile | grep -oE 'ghcr\.io/opentofu/opentofu:[0-9.]+')
echo "image: $TOFU_IMAGE"
docker run --rm -v "$W:/w" "$TOFU_IMAGE" -chdir=/w fmt -check -diff backups.tf && echo "fmt: backups.tf as tofu writes it"
docker run --rm -v "$W:/w" "$TOFU_IMAGE" -chdir=/w init -backend=false -input=false -no-color >/dev/null
docker run --rm -v "$W:/w" "$TOFU_IMAGE" -chdir=/w validate -no-color
