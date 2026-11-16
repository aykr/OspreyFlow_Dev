"""The media write before row 6's verify (`process/lanes/platform-b/v060/media_write.py`), against a stand-in
Conduit that refuses as `PUT /v1/investigations/{id}/nodes/{node}/picture` does: a name without a picture's
extension (415 `type_not_allowed`), an empty body (400), a marking above the deployment's (422), and that
answers the entity's picture only once one was stored (rule 15).

What a mistake would do, and the case that catches it (rule 12):
- a write the route refuses, taken for written: `test_a_refused_picture_stops_in_words`;
- a picture "set" that is not the entity's own: `test_a_picture_not_read_back_stops_in_words`;
- an image that is not one: `test_the_image_is_a_real_png`;
- a picture asked for an entity not on the case's canvas (the service reads the node from the working set,
  `entity_pictures._entity`; v0.6.0's row 6: 404 node_not_found): the stand-in refuses it as the real one does,
  so `test_the_picture_is_written_and_read_back` needs the person seeded first.
"""

from __future__ import annotations

import importlib.util
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "process/lanes/platform-b/v060/media_write.py"
_spec = importlib.util.spec_from_file_location("media_write_under_test", SCRIPT)
assert _spec and _spec.loader
mw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mw)


class _Answer:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status_code, self._body = status, body if body is not None else {}
        self.text = str(self._body)

    def json(self) -> Any:
        return self._body


class _Conduit:
    def __init__(self, *, keeps: bool = True) -> None:
        self.keeps, self.stored, self.canvas = keeps, {}, set()

    def post(self, path: str, headers: dict[str, str], json: dict[str, Any]) -> _Answer:
        if path.endswith("/search"):
            return _Answer(200, {"nodes": [{"id": "p1", "type": "Person"}]})
        if path.endswith("/seed"):
            self.canvas |= {n["id"] for n in json["nodes"]}
            return _Answer(200, {"delta": {}})
        if path.endswith("/pictures"):
            return _Answer(200, {"pictures": {n: self.stored[n] for n in json["node_ids"] if n in self.stored}})
        raise AssertionError(path)

    def put(self, path: str, headers: dict[str, str], params: dict[str, str], content: bytes) -> _Answer:
        if not params.get("name", "").lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return _Answer(415, {"detail": "That file type is not allowed."})
        if not content:
            return _Answer(400, {"detail": "The file is empty."})
        if params.get("classification") not in ("PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"):
            return _Answer(422, {"detail": "above_the_deployments_highest_marking"})
        if not params.get("legal_basis"):
            return _Answer(422, {"detail": "legal_basis required"})
        node = path.split("/")[5]
        if node not in self.canvas:  # the picture service reads the node from the case's working set alone
            return _Answer(404, {"error": "node_not_found"})
        if self.keeps:
            self.stored[node] = "doc-1"
        return _Answer(200, {"document_id": "doc-1"})


def test_the_picture_is_written_and_read_back() -> None:
    done = mw.write(_Conduit(), {"Authorization": "Bearer t"}, "case-1")
    assert done == {"node": "p1", "picture": "doc-1", "status": 200}


def test_a_refused_picture_stops_in_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mw, "NAME", "r1-synthetic-person.bin")
    with pytest.raises(SystemExit, match="the picture was refused: 415"):
        mw.write(_Conduit(), {"Authorization": "Bearer t"}, "case-1")


def test_a_picture_not_read_back_stops_in_words() -> None:
    with pytest.raises(SystemExit, match="is not the entity's own"):
        mw.write(_Conduit(keeps=False), {"Authorization": "Bearer t"}, "case-1")


def test_the_image_is_a_real_png() -> None:
    data = mw.png()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (1, 1)
    idat = data.index(b"IDAT")
    (length,) = struct.unpack(">I", data[idat - 4 : idat])
    assert zlib.decompress(data[idat + 4 : idat + 4 + length]) == b"\x00\x80"
