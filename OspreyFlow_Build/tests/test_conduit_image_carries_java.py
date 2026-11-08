"""The Conduit's image carries what the tier-1 basemap build needs (`06_DECISIONS.md` ADR-147
decision 3): a Java runtime on its `PATH` (planetiler is a Java program, run by
`scripts/build_local_basemap.run_planetiler` as `java -jar`), from a JDK pinned by digest, and the
maps file's folder owned by the Conduit's user. Without the runtime, *Build* in *Admin › Maps* says
"Java is not installed in the Conduit" (`map_admin.MapAdmin.basemap`)."""

from __future__ import annotations

import re

from tools.layout import CORE

DOCKERFILE = (CORE / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")


def test_the_image_takes_a_java_runtime_from_a_jdk_pinned_by_digest() -> None:
    assert re.search(r"^FROM eclipse-temurin:21-jdk@sha256:[0-9a-f]{64} AS java$", DOCKERFILE, re.M)
    assert "COPY --from=java /opt/java-runtime /opt/java" in DOCKERFILE
    path = re.search(r'^ENV PATH="([^"]+)"', DOCKERFILE, re.M)
    assert path is not None and "/opt/java/bin" in path.group(1).split(":")


def test_the_maps_file_s_folder_is_made_for_the_conduit_s_user() -> None:
    assert (
        "mkdir -p /run/osprey/map-settings && chown osprey:osprey /run/osprey/map-settings"
        in DOCKERFILE
    )
