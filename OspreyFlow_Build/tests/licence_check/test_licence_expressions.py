"""The licence gate reads a licence *expression*, not a bag of words (`spec/00_ARCHITECTURE.md` §7;
the review of 18 October 2026).

Before this, `is_allowed` passed any text containing "lgpl", so `"AGPL-3.0 AND LGPL-2.1"` — the
shape a package naming two licences takes — passed; it allowed every LGPL package, where §7 admits
LGPL only by a recorded exception naming the package; and it matched by substring, so a word
containing "mit" counted as MIT. Each case below plants one of those in the form the gate really
receives: pip-licenses joins a package's licences with "; ", license-checker's are joined with
" AND " by `main()`, and SPDX expressions carry AND, OR and parentheses.
"""

from __future__ import annotations

import pytest
from tools.licence_check import RECORDED_LGPL_EXCEPTIONS, find_offenders, is_allowed


@pytest.mark.parametrize(
    "text",
    [
        "MIT License",
        "Apache Software License",
        "BSD-3-Clause",
        "Mozilla Public License 2.0 (MPL 2.0)",
        "Python Software Foundation License",
        "The Unlicense (Unlicense)",
        "MIT License; Apache Software License",
        "Apache-2.0 OR GPL-3.0",  # a choice: Apache is enough
        "(MIT OR GPL-2.0) AND BSD-3-Clause",
        # Added 19 October 2026 (§7): numpy's, regex's and torch's.
        "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
        "Apache-2.0 AND CNRI-Python",
        "Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSL-1.0 AND MIT",
    ],
)
def test_an_allowed_licence_or_choice_passes(text: str) -> None:
    assert is_allowed(text), text


@pytest.mark.parametrize(
    "text",
    [
        "AGPL-3.0 AND LGPL-2.1",  # the review's planted shape: the LGPL term let AGPL through
        "GNU Affero General Public License v3; GNU Lesser General Public License v3 (LGPLv3)",
        "MIT AND GPL-3.0",
        "MIT License; GNU General Public License v3 (GPLv3)",
        "GPL-3.0 OR AGPL-3.0",  # a choice between two refused licences is refused
        "(MIT OR Apache-2.0) AND GPL-3.0",  # a choice of two allowed, then a refused term
        "CC-BY-SA-4.0",  # share-alike is not CC-BY
        "LGPL-3.0",  # no recorded exception for an unnamed package
        "GNU Lesser General Public License v3 (LGPLv3)",
        "Limited Use Licence",  # "limited" is not MIT
        "Commercial",
        "UNKNOWN",
        "",
    ],
)
def test_a_refused_licence_anywhere_in_the_expression_fails(text: str) -> None:
    assert not is_allowed(text), text


def test_lgpl_passes_only_for_a_package_with_a_recorded_exception() -> None:
    assert {"deepparse", "gensim", "poutyne"} <= set(RECORDED_LGPL_EXCEPTIONS)
    lgpl = "GNU Lesser General Public License v3 (LGPLv3)"
    assert is_allowed(lgpl, package="deepparse")
    assert not is_allowed(lgpl, package="some-other-package")
    # An exception covers the package's LGPL, never a GPL it also declares.
    assert not is_allowed(f"{lgpl}; GNU General Public License v3 (GPLv3)", package="deepparse")


def test_offenders_are_judged_with_their_own_name() -> None:
    packages = [
        {"Name": "deepparse", "Version": "1", "License": "GNU Lesser General Public License v3"},
        {"Name": "sneaky", "Version": "1", "License": "AGPL-3.0 AND LGPL-2.1"},
        {"Name": "fine", "Version": "1", "License": "MIT License"},
    ]
    assert [p["Name"] for p in find_offenders(packages)] == ["sneaky"]
