"""What the Conduit's image carries for the tier-1 basemap build (`06_DECISIONS.md` ADR-147
decision 3). **No Java runtime while the owner rules on its licence**: the Temurin runtime is GPL-2.0
with the Classpath exception, and the licence register (`spec/00_ARCHITECTURE.md` §7) passes no GPL,
so a JDK or JRE stage in the image fails here until the register records the owner's ruling. The
maps file's folder is made for the Conduit's user."""

from __future__ import annotations

import re

from tools.layout import CORE

DOCKERFILE = (CORE / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")


def test_the_image_carries_no_java_runtime_until_its_licence_is_ruled_on() -> None:
    assert not re.search(r"^FROM .*(temurin|openjdk|jdk|jre)", DOCKERFILE, re.M | re.I)
    assert "/opt/java" not in DOCKERFILE


def test_the_maps_file_s_folder_is_made_for_the_conduit_s_user() -> None:
    assert (
        "mkdir -p /run/osprey/map-settings && chown osprey:osprey /run/osprey/map-settings"
        in DOCKERFILE
    )
