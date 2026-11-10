"""UPG's image-tag guard on the shared test server: P5b's `OwnImages` (process/lanes/platform-b/gates/
p5b_live_update.py), kept across the rehearsal's separate steps in a JSON file of the run's own.

    python upg_images.py hold    <state.json>   # before the main-head build: the tags it may move
    python upg_images.py claim   <state.json> <compose.yaml>   # at once after the build
    python upg_images.py restore <state.json>   # teardown: put back, or remove the run's own
    python upg_images.py check   <state.json>   # exit 1 if a tag the run moved is not back

Run with `p5b_live_update.py` beside it (copied from main, unchanged): `OwnImages` is P5b's, tested in
`tests/test_live_driver_own_tags.py`; this file's own `_load`/`_save` round trip and claim filter are
untested, and it holds under P5b's own prefix `osprey-p5b-hold/`, so a P5b run on the same server at the
same time would see this run's hold as its own (and the reverse): never run the two together. Never a
before-and-after difference of the machine's tags; another lane's changes are listed, not touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from p5b_live_update import OwnImages, image_table, others_changed, tags_changed

RUN = "upg-rehearsal"


def _load(state: Path) -> OwnImages:
    saved = json.loads(state.read_text())
    own = OwnImages(saved["before"])
    own.made, own.holds = saved["made"], saved["holds"]
    return own


def _save(state: Path, own: OwnImages) -> None:
    state.write_text(
        json.dumps({"before": own.before, "made": own.made, "holds": own.holds})
    )


def main(argv: list[str]) -> int:
    verb, state = argv[0], Path(argv[1])
    if verb == "hold":
        own = OwnImages(image_table())
        own.hold(run=RUN)
        _save(state, own)
        print(f"upg-images: held {own.holds or 'none'}")
    elif verb == "claim":
        own = _load(state)
        rendered = yaml.safe_load(Path(argv[2]).read_text())
        # A checkout's build (`build:`), or an owned image named by the user repository's registry
        # (a release-shaped reference, were one built here): both are the run's to put back.
        own.claim(
            s["image"]
            for s in rendered["services"].values()
            if "image" in s
            and ("build" in s or str(s["image"]).startswith("ghcr.io/aykr/"))
        )
        _save(state, own)
        print(f"upg-images: the run's images {own.made or 'none'}")
    elif verb == "restore":
        own = _load(state)
        for line in own.restore():
            print(f"upg-images: image {line}")
    elif verb == "check":
        own = _load(state)
        after = image_table()
        bad = tags_changed(own.before, after, own.made_ids(), own.claimed())
        theirs = others_changed(own.before, after, own.made_ids(), own.claimed())
        print(f"upg-images: another's tags changed meanwhile: {theirs or 'none'}")
        print(f"upg-images: the run's tags not put back or left: {bad or 'nothing'}")
        return 1 if bad else 0
    else:
        raise SystemExit(f"upg-images: no verb {verb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
