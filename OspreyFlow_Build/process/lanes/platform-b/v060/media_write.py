"""A real media write through the analyst's door, before the manifest verify (v0.6.0's package test row 6,
the orchestrator's ruling of 16 November 2026): a fresh install has written nothing to the media bucket, and
the verify holds every bucket to being written by the deployment.

The write is the Glass's own: an entity's picture, `PUT /v1/investigations/{id}/nodes/{node}/picture`
(ADR-105; spec 03), whose image the Conduit stores in the media store. The entity is the person R1's checks
loaded (`R1Synthetic`, in the check list's case), put on the case's canvas first; the image a synthetic 1x1 PNG made here (rule 9); the
picture then read back as the entity's own (`POST /v1/investigations/{id}/pictures`). Run through
`r1_live.sh media`, with R1's own environment; `tests/test_v060_media_write.py` holds it.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path
from typing import Any

GATES = Path(__file__).resolve().parents[2] / "platform" / "gates"
NAME = "r1-synthetic-person.png"


def png() -> bytes:
    """A 1x1 grey PNG: a real image, nothing of anyone's."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00\x80"))
            + chunk(b"IEND", b""))  # fmt: skip


def write(c: Any, admin: dict[str, str], case: str) -> dict[str, Any]:
    """The picture set on R1Synthetic and read back; stops in words at the first refusal."""
    found = c.post(f"/v1/investigations/{case}/search", headers=admin, json={"query": "R1Synthetic", "limit": 5})
    nodes = (found.json().get("nodes") or []) if found.status_code == 200 else []
    person = next((n for n in nodes if n.get("type") == "Person"), None)
    if person is None:
        raise SystemExit(f"no R1Synthetic person to give a picture: {found.status_code} {found.text[:200]}")
    # On the case's canvas first, as an analyst sets a picture on an entity they are looking at: the picture service
    # reads the node from the case's working set (`entity_pictures._entity`), not from search (row 6: 404).
    seeded = c.post(f"/v1/investigations/{case}/seed", headers=admin, json={"nodes": [person], "edges": []})
    if seeded.status_code != 200:
        raise SystemExit(f"the person could not be put on the case's canvas: {seeded.status_code} {seeded.text[:200]}")
    put = c.put(f"/v1/investigations/{case}/nodes/{person['id']}/picture", headers={**admin, "Content-Type": "image/png"},
                params={"name": NAME, "classification": "OFFICIAL", "legal_basis": "synthetic test data (R1)"},
                content=png())  # fmt: skip
    if put.status_code not in (200, 201):
        raise SystemExit(f"the picture was refused: {put.status_code} {put.text[:300]}")
    seen = c.post(f"/v1/investigations/{case}/pictures", headers=admin, json={"node_ids": [person["id"]]})
    # `list[EntityPicture]`: each {node_id, document_id}, the entities with a picture of their own the caller sees.
    held = {p["node_id"]: p["document_id"] for p in (seen.json() if seen.status_code == 200 else [])}
    if person["id"] not in held:
        raise SystemExit(f"the picture was set but is not the entity's own: {seen.status_code} {seen.text[:200]}")
    return {"node": person["id"], "picture": held[person["id"]], "status": put.status_code}


def main(argv: list[str]) -> int:  # pragma: no cover - the live half
    sys.path.insert(0, str(GATES))
    import r1_kind

    c, case = r1_kind.door(), r1_kind.state()["case"]
    done = write(c, {"Authorization": f"Bearer {r1_kind.token()}"}, case)
    line = f"PASS the person's picture is written through the analyst's door and read back as its own: {done}"
    r1_kind.record("media").write_text(line + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
