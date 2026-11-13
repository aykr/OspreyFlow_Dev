"""Runs install_verify.SEARCH_PROBE as a reader's pod runs it, with a given tree holding rules' search client
(services/search_index/client.py) and a Python with opensearch-py and botocore, against search_domain_fake both ways
(the signed count admitted, and refused). Prints the probe's line and the verdict; gates/search-probe-real.txt is its
output, with the probe's hash so the record names the probe it ran.

    <python with opensearch-py, botocore> record_search_probe.py <tree with services/search_index>
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import install_verify as iv
import search_domain_fake

ALIAS = "ospreyflow-default"


def run(tree: str, *, refuse_signed: bool) -> None:
    server = search_domain_fake.start(ALIAS, refuse_signed=refuse_signed)
    env = {**os.environ, "PYTHONPATH": tree, "OPENSEARCH_URL": f"http://127.0.0.1:{server.server_port}",
           "OPENSEARCH_SIGNING": "sigv4", "OPENSEARCH_REGION": "eu-west-2",
           "AWS_ACCESS_KEY_ID": "AKIDEXAMPLE", "AWS_SECRET_ACCESS_KEY": "x"}
    done = subprocess.run([sys.executable, "-c", iv.SEARCH_PROBE], capture_output=True, text=True, env=env, cwd=tree, check=False)
    server.shutdown()
    print("probe stdout:", done.stdout.strip())
    print("verdict:", iv.search_answer(done.stdout))


def main() -> None:
    import opensearchpy

    print(f"# SEARCH_PROBE sha256 {hashlib.sha256(iv.SEARCH_PROBE.encode()).hexdigest()[:16]}, opensearch-py "
          f"{'.'.join(map(str, opensearchpy.VERSION))}, the client at {sys.argv[1]}; search_domain_fake over http")
    print("## a domain that admits the signed count")
    run(sys.argv[1], refuse_signed=False)
    print("## a domain that refuses the signed count too (the reader must fail)")
    run(sys.argv[1], refuse_signed=True)


if __name__ == "__main__":
    main()
