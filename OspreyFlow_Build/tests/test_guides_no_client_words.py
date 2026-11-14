"""No guide names the client, or a setting still to be confirmed, where the Glass now says neither (the owner's
exception of 14 November 2026: studio's route V3). The composition the code keys `client_parity` is called by the
Glass's own label, `COMPOSITION_LABEL.client_parity` in `strength/words.ts`; its scale is the raw-sum scale, as the
Inspector and the sentence builder say; the share measure is called by `MEASURE_LABEL.share`. Held to the code's
strings, never its comments (rule 12), and each check shown flagging the guides' own old words (rule 15).
"""

from __future__ import annotations

import re

from tests.test_guides_cloud_platform import CORE

SRC = CORE / "apps/workspace/src"
#: What the guides said before V3: the composition, its scale, the measure and the influencers' note.
OLD_WORDS = ("client parity", "client-parity", "client's scale", "confirmed with the client", "as the client works",
             "the client's own sum")  # fmt: skip


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def guide(name: str) -> str:
    text = (CORE / "docs" / f"{name}-guide.md").read_text(encoding="utf-8")
    return fold(re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL))


def code(path: str) -> str:
    source = (SRC / path).read_text(encoding="utf-8")
    source = re.sub(r"\{/\*.*?\*/\}|/\*.*?\*/", " ", source, flags=re.DOTALL)
    return fold(re.sub(r"(?m)^\s*//.*$", " ", source))


def old_words(texts: dict[str, str]) -> list[str]:
    return [f"{name}: {old!r}" for name, text in texts.items() for old in OLD_WORDS if old in text.lower()]


def label(source: str, table: str, key: str) -> str:
    m = re.search(rf"export const {table}: Record<\w+, string> = \{{(.*?)\}};", source)
    assert m, table
    found = re.search(rf"\b{key}: \"([^\"]+)\"", m.group(1))
    assert found, f"{table}.{key}"
    return found.group(1)


def test_no_guide_says_the_client_s_words() -> None:
    assert old_words({n: guide(n) for n in ("user", "developer", "administration", "architecture")}) == []


def test_the_guides_old_words_are_flagged() -> None:
    planted = {"user": 'and are marked "to be confirmed with the client". | **Client parity** | the client\'s own sum, '
               "the **raw sum on the client's scale** |", "developer": "    note: to be confirmed with the client"}  # fmt: skip
    assert old_words(planted) == ["user: 'client parity'", "user: \"client's scale\"", "user: 'confirmed with the client'",
                                  "user: \"the client's own sum\"", "developer: 'confirmed with the client'"]  # fmt: skip


def test_the_user_guide_names_the_composition_its_scale_and_the_measure_as_the_glass_does() -> None:
    words = code("strength/words.ts")
    composition, measure = label(words, "COMPOSITION_LABEL", "client_parity"), label(words, "MEASURE_LABEL", "share")
    assert composition == "Rarity plus adds" and measure == "share of pair links"
    inspector = code("inspector/StrengthExplained.tsx")
    assert 'aria-label="Raw sum on the raw-sum scale"' in inspector
    builder = code("alerts/SentenceBuilder.tsx")
    assert '<option value="client">the raw-sum scale (a raw sum, under rarity plus adds)</option>' in builder
    text = guide("user")
    assert f"| **{composition}** | rarity plus the influencers' added boosts, with no count and no recency: a raw sum |" in text
    assert "the Inspector also shows the **raw sum on the raw-sum scale** |" in text
    assert "*on the raw-sum scale* a raw sum up to 10 (met only under rarity plus adds)" in text
    assert f"By default rarity is worked out as the **{measure}**: a value" in text
    assert "its count would. Boosts add up." in text


def test_the_developer_guide_s_note_example_is_no_setting_still_to_be_confirmed() -> None:
    text = guide("developer")
    assert '| `note` | Shown beside it, such as "set from the 2026 calibration" |' in text
    assert "note: set from the 2026 calibration" in text
    assert "to be confirmed" not in text.lower()
