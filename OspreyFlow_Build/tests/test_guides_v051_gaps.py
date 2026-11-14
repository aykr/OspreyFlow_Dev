"""What v0.5.1 shipped that the guides had not said (the docs lane's step 5 sweep, part 8), each held to the code that
does it (rule 12):

- user guide §2: a refresh keeps you signed in and where you were (ADR-050 Amendment 3);
- user guide §3: under GOV.UK, the slim header and phase banner and the one-row context banner (ADR-132 Amendment 8);
- the architecture guide and the administration guide's opening name the shared-platform profile, and the
  administration guide §14 says how a namespace there moves to a new release.
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
SRC = CORE / "apps" / "workspace" / "src"


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def code(path: str) -> str:
    return fold((SRC / path).read_text(encoding="utf-8"))


def guide(name: str) -> str:
    return fold((CORE / "docs" / f"{name}-guide.md").read_text(encoding="utf-8"))


def test_user_guide_2_says_a_refresh_keeps_you_signed_in_and_where_you_were() -> None:
    app, place, users = code("App.tsx"), code("auth/refreshPlace.ts"), code("auth/userManager.ts")
    # The identity provider's own session asked silently first, the screen only when it says no.
    assert "silent: () => renewSilently({ silentRequestTimeoutInSeconds: SILENT_AT_LOAD_TIMEOUT_SECONDS })," in app
    assert 'const PLACES: readonly Place[] = ["home", "case", "admin", "studio", "rules"];' in place
    assert "storage.setItem(REFRESH_PLACE_KEY, place);" in place and "placeAtLoad(" in app and "sessionStorage" in app
    # A place the rights do not open is kept as Home (`placeOnScreen`); of the Glass's views, only these are put back.
    assert "if (chosen && (chosen === \"admin\" || !caseOpen) && !offered.includes(chosen)) return \"home\";" in place
    views = re.search(r'const RESTORED_GLASS_VIEWS: readonly string\[\] = \[([^\]]*)\];', place)
    assert views and re.findall(r'"(\w+)"', views.group(1)) == ["graph", "map", "matrix", "reports"]
    assert "export function signOut(): Promise<void> { // ADR-050 Amendment 3: the next person in this tab does not start where this one was. forgetPlace(sessionStorage);" in users
    text = guide("user")
    assert "**Refreshing the page** keeps you signed in and where you were. It asks the sign-in service's own session first" in text
    layout = (SRC / "shell" / "railLayout.ts").read_text(encoding="utf-8")
    block = layout[layout.index("export const VIEW_LABELS") :]
    labels = dict(re.findall(r'^\s*(map|matrix|reports): "([^"]+)",$', block[: block.index("};")], re.MULTILINE))
    assert (f"Home stays Home, a case stays that case (on the view it had, where that is the graph, the {labels['map'].lower()}, "
            f"the {labels['matrix']} or {labels['reports']}; on any other view, the Glass's first)") in text  # fmt: skip
    assert "a place your roles do not open is shown as Home." in text
    assert "This is kept for the tab alone, and **Sign out** forgets it, so the next person to sign in there does not start where you were." in text


def test_user_guide_3_says_the_govuk_top_is_slim_and_the_banner_one_row() -> None:
    frame, banner = code("brand/BrandFrame.tsx"), code("shell/ContextBanner.tsx")
    assert '<div ref={above} className={claims === 0 ? "brand-chrome brand-chrome--compact" : "brand-chrome"}>' in frame
    assert "<GovukHeader withPlaces hostname={hostname} /> <PhaseBanner" in frame
    claimers = sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*.tsx")
                      if "test" not in p.name and "useFullFooter();" in p.read_text(encoding="utf-8"))  # fmt: skip
    assert claimers == ["auth/SignInScreen.tsx", "home/HomePage.tsx"], "the screens that keep the full GOV.UK top"
    assert 'className="govuk-notification-banner context-banner--govuk context-banner--folded"' in banner
    text = guide("user")
    assert ("**Under the GOV.UK theme**, on every screen but Home and the sign-in page, the GOV.UK header and the "
            "phase banner are slim, and the context banner, a GOV.UK notification banner, is folded into one row") in text  # fmt: skip


def test_the_shared_platform_profile_is_named_where_the_modes_are() -> None:
    profiles = (CORE / "cli" / "ospreyflow" / "deployments.py").read_text(encoding="utf-8")
    assert 'PROFILE_NAMES = ("local-lite", "small", "cluster", "cloud-platform")' in profiles
    assert "is a profile of its own, `cloud-platform` (the administration guide's section 6a)" in guide("architecture")
    profile = (CORE / "harness" / "cloud_platform" / "profile.yaml").read_text(encoding="utf-8")
    assert "build_args: {CONDUIT_JAVA: omitted}" in profile and "laurium: {dockerfile: services/laurium/Dockerfile" in profile
    assert ("There the Conduit's image is built without Java (so no basemap is built on the platform), and the second "
            "extraction engine, Laurium, has an image of its own.") in guide("architecture")  # fmt: skip
    admin = guide("administration")
    assert "and a namespace on an organisation's own shared Kubernetes platform (`cloud-platform`, section 6a)" in admin


def test_section_14_says_how_a_shared_platform_namespace_moves_to_a_new_release() -> None:
    admin = guide("administration")
    assert "**Moving to a new release (poc shape).** There is no separate upgrade runbook." in admin
    runbook = (CORE / "harness" / "cloud_platform" / "runbooks.py").read_text(encoding="utf-8")
    install = runbook[runbook.index("def render_install(") : runbook.index("def _seed_section(")]
    assert 'helm upgrade --install "$RELEASE" "$CHART"' in install, "INSTALL.md moves the release with helm upgrade --install"
    assert "- **The standard shape's runbooks**, as the poc shape has." in admin, "§6a.10 still lists them as coming"
    row = "| A namespace on a shared platform (`cloud-platform`), the poc shape | As section 6a.1's *Moving to a new release* says"
    section = admin[admin.index("## 14. Updates") : admin.index("**Checking for a newer release.**")]
    assert row in section and "The standard shape's runbooks are *coming* (section 6a.10) |" in section
