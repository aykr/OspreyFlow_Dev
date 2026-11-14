"""What SigV4 signing costs per OpenSearch request, which step 4 does not pay (its runner talks to
the stack's OpenSearch unsigned, on the host's loopback, without TLS; the client's poc signs every
call for `es` and sends it over TLS: ADR-149 Amendment 2's known difference).

The signer is the one the Conduit uses (`services/search_index/client.py`'s `_sigv4_auth`:
opensearch-py's `AWSV4SignerAsyncAuth` over botocore), given static synthetic credentials (no AWS
call is made: signing is local arithmetic over the request). Each request is a search body of
the size the search service sends (the access filter, the bands, the aggregations), to the
index's `_search` path. Prints the p50, p95 and max per signature in microseconds, and the CPU.

    OspreyFlow_Core/.venv/bin/python \\
      OspreyFlow_Build/process/lanes/platform/v052-measure/sigv4_cost.py [n]

TLS is not measured here: with the client's connection pool kept alive, its handshake is paid per
connection, not per request, and the per-request cost is the record encryption of a few KB.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time


def _body() -> bytes:
    """A search body of the service's own shape and size: the reader's access filter (a terms
    list of datasets and codes, a range of markings), five bands of match clauses, the type
    aggregation and the dataset filter's."""
    access = {
        "bool": {
            "filter": [
                {"terms": {"datasets": [f"ds-{i:04d}" for i in range(40)]}},
                {"terms": {"classification_rank": [0, 1, 2]}},
                {"bool": {"must_not": {"terms": {"handling_codes": ["R", "X", "Y"]}}}},
            ]
        }
    }
    bands = [
        {
            "constant_score": {
                "filter": {"term": {f"band_{b}": "kestral harbour"}},
                "boost": 3000 - b * 100,
            }
        }
        for b in range(5)
    ]
    body = {
        "query": {"bool": {"filter": [access], "should": bands, "minimum_should_match": 1}},
        "aggs": {"types": {"terms": {"field": "type", "size": 50}},
                 "datasets": {"terms": {"field": "datasets", "size": 100}}},
        "size": 20, "track_total_hits": True,
        "highlight": {"fields": {"text": {"fragment_size": 160, "number_of_fragments": 1}}},
    }  # fmt: skip
    return json.dumps(body).encode()


def main(argv: list[str]) -> int:
    from botocore.credentials import Credentials
    from opensearchpy import AWSV4SignerAsyncAuth

    n = int(argv[1]) if len(argv) > 1 else 20000
    auth = AWSV4SignerAsyncAuth(
        Credentials("AKIASYNTHETICEXAMPLE", "synthetic-secret-for-signing-only", "synthetic-token"),
        "eu-west-2",
        "es",
    )
    url = (
        "https://vpc-ospreyflow-poc-synthetic.eu-west-2.es.amazonaws.com:443/ospreyflow-poc/_search"
    )
    body = _body()
    for _ in range(500):  # warm-up
        auth("POST", url, body, {"Content-Type": "application/json"})
    times = []
    for _ in range(n):
        started = time.perf_counter_ns()
        auth("POST", url, body, {"Content-Type": "application/json"})
        times.append((time.perf_counter_ns() - started) / 1000)
    times.sort()
    print(json.dumps({
        "signatures": n, "body_bytes": len(body),
        "p50_us": round(statistics.median(times), 1),
        "p95_us": round(times[int(0.95 * n) - 1], 1),
        "max_us": round(times[-1], 1),
        "machine": f"{platform.machine()} {platform.processor() or ''}".strip(),
        "python": platform.python_version(),
    }, indent=2))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
