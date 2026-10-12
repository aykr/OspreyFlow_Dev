"""Superset's light and dark themes, generated from the Glass's design tokens (`06_DECISIONS.md`
ADR-111 Amendment 4).

    PYTHONPATH=. python -m scripts.superset_theme      # rewrites deploy/superset/osprey_theme.json

`tokens.css` is authoritative: no colour outside it. Its `:root` set is the dark theme (the working
default) and `[data-theme="light"]` the separately tuned light one; each becomes one of Superset 6's
themes (Ant Design tokens plus Superset's own). Charts use the both-modes chart set (`--chart-*`)
in either theme, because a chart's series keep the colours of its scheme whichever mode it is shown
in — never brass, which is the accent and no channel. The Superset image is built from
`deploy/superset/` alone, so the result is committed there, and `tests/test_superset_theme.py` fails
when it differs from what the tokens make.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "apps" / "workspace" / "src" / "design" / "tokens.css"
OUTPUT = ROOT / "deploy" / "superset" / "osprey_theme.json"

#: The order the chart colours are dealt in: neighbours far apart in hue.
CHANNELS = ("azure", "ochre", "jade", "violet", "cyan", "rose", "moss", "indigo", "plum")
APP_NAME = "OspreyFlow Reports"

_BLOCK = re.compile(r"(?P<selector>:root|\[data-theme=\"light\"\])\s*\{(?P<body>.*?)\n\}", re.S)
_DECLARATION = re.compile(r"--(?P<name>[a-z0-9-]+)\s*:\s*(?P<value>[^;]+);")
_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _declarations(body: str) -> dict[str, str]:
    return {m["name"]: m["value"].strip() for m in _DECLARATION.finditer(_COMMENT.sub("", body))}


def token_sets(css: str) -> tuple[dict[str, str], dict[str, str]]:
    """(dark, light), each with every `var(--x)` resolved. The light set overrides the dark one, as
    the stylesheet does, so a token the light set does not restate keeps its dark value."""
    blocks = {m["selector"]: _declarations(m["body"]) for m in _BLOCK.finditer(css)}
    dark = blocks[":root"]
    light = {**dark, **blocks['[data-theme="light"]']}

    def resolved(values: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in values:
            value = values[name]
            for _ in range(5):
                match = re.fullmatch(r"var\(--([a-z0-9-]+)\)", value)
                if match is None:
                    break
                value = values[match[1]]
            out[name] = value
        return out

    return resolved(dark), resolved(light)


def _px(value: str) -> int:
    return int(value.removesuffix("px"))


def _chart(t: dict[str, str]) -> list[str]:
    """The both-modes chart set (`--chart-*`): a chart keeps its series colours in either mode."""
    return [t[f"chart-{name}"] for name in CHANNELS]


def _theme(t: dict[str, str], *, algorithm: str) -> dict[str, object]:
    channels = _chart(t)
    return {
        "algorithm": algorithm,
        "token": {
            "brandAppName": APP_NAME,
            "colorPrimary": t["brass"],
            "colorLink": t["brass"],
            "colorLinkHover": t["brass-hover"],
            "colorLinkActive": t["brass-press"],
            "colorError": t["error"],
            "colorWarning": t["warning"],
            "colorSuccess": t["success"],
            "colorInfo": t["text-secondary"],
            "colorBgBase": t["surface-app"],
            "colorBgLayout": t["surface-app"],
            "colorBgContainer": t["surface-panel"],
            "colorBgElevated": t["surface-raised"],
            "colorTextBase": t["text-primary"],
            "colorText": t["text-primary"],
            "colorTextSecondary": t["text-secondary"],
            "colorTextTertiary": t["text-tertiary"],
            "colorTextQuaternary": t["text-disabled"],
            "colorBorder": t["border"],
            "colorBorderSecondary": t["border-subtle"],
            "fontFamily": t["ui"],
            "fontFamilyCode": t["mono"],
            "fontSize": _px(t["fs-13"]),
            "borderRadius": _px(t["r-control"]),
            "borderRadiusLG": _px(t["r-panel"]),
            "borderRadiusSM": _px(t["r-control"]),
            # Docked panels get a hairline, never a shadow as well (tokens.css).
            "dashboardTileBg": t["surface-panel"],
            "dashboardTileBorder": f"1px solid {t['border-subtle']}",
            "dashboardTileBorderRadius": _px(t["r-panel"]),
            "dashboardTileBoxShadow": "none",
        },
        "echartsOptionsOverrides": {
            "color": channels,
            "textStyle": {"fontFamily": t["ui"]},
            "tooltip": {
                "backgroundColor": t["surface-raised"],
                "borderColor": t["border"],
                "textStyle": {"color": t["text-primary"], "fontFamily": t["ui"]},
            },
        },
    }


def render(css: str) -> str:
    dark, light = token_sets(css)
    document = {
        "_generated": "by scripts/superset_theme.py from apps/workspace/src/design/tokens.css — "
        "do not edit; run `python -m scripts.superset_theme`",
        "default": _theme(light, algorithm="default"),
        "dark": _theme(dark, algorithm="dark"),
        # The palettes Superset's chart editor offers: the both-modes chart set, the light ramp.
        "categorical": {"colors": _chart(dark)},
        "sequential": {"colors": [light[f"seq-{n}"] for n in range(1, 7)]},
    }
    return json.dumps(document, indent=2) + "\n"


def main() -> int:
    OUTPUT.write_text(render(TOKENS.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
