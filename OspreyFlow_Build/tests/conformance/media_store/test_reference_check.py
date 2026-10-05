"""The media reference check itself (ADR-094). The suite's "not a name this store makes" cases would
pass even with no check, because such a name is usually missing anyway (rule 15: a default-deny
fallthrough proves nothing about the branch). Here the file is really there, under a name the store
does not make, and must still be refused."""

from __future__ import annotations

import pytest

from adapters.media_objectstore.testing import InMemoryMediaStore
from ports.media import MediaNotFoundError


@pytest.mark.parametrize("planted", ["other/a.png", "media/../secret.png", "media/ABC.png"])
async def test_a_file_held_under_a_name_the_store_does_not_make_is_refused(planted: str) -> None:
    store = InMemoryMediaStore()
    store.files[planted] = b"present"
    with pytest.raises(MediaNotFoundError):
        await store.get(planted)
