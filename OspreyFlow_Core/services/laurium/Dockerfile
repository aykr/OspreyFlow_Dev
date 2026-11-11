# Laurium's service (spec/06_DECISIONS.md ADR-135 Amendment 6): Laurium 0.6.0 on Python 3.13, in an
# image of its own, built only when the extraction engine Laurium is chosen. Built from this folder
# alone (`docker build services/laurium`): the Conduit's build context leaves it out (.dockerignore),
# so no image but this one carries Laurium, LangChain or spaCy (tools/no_langchain_check.py).
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# Debian's fixes that the base image does not carry yet, as every other image takes them.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Every package pinned by hash (requirements.txt, compiled from requirements.in for 3.13 on
# manylinux_2_28): Laurium from PyPI's 0.6.0 artefacts, never its repository's main; spaCy's
# en-core-web-sm 3.8.0 from Explosion's GitHub release, the one source beyond PyPI (the owner's
# ruling 3); wheels only, so nothing is built here; never Laurium's `encoder` extra (ruling 4).
COPY requirements.txt ./requirements.txt
RUN pip install --require-hashes --only-binary :all: --no-deps -r requirements.txt \
 && pip check \
 && rm requirements.txt

# The licence register (00_ARCHITECTURE.md §7) for this image's own packages, which
# `make licence-check` does not see: fails the build on any GPL licence, any it cannot read but the
# three recorded entries, and any package of the `encoder` extra.
COPY licence_gate.py licence-gate.txt ./
RUN pip install --require-hashes --only-binary :all: --no-deps -r licence-gate.txt \
 && python licence_gate.py \
 && pip uninstall -y pip-licenses prettytable wcwidth \
 && rm licence_gate.py licence-gate.txt

COPY __init__.py app.py app_contract.py schema_map.py settings.py ./laurium_service/
COPY NOTICE ./NOTICE
RUN useradd --create-home --uid 10001 laurium && chown -R laurium /srv
USER 10001:10001
EXPOSE 8000
# OSPREY_LAURIUM_GATEWAY_URL must name the deployment's gateway (http://litellm:4000); the service
# refuses to start without it, or with any setting that would send a call anywhere else.
CMD ["uvicorn", "laurium_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
