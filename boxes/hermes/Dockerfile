# The sealed Hermes box (docs/HERMES_BOX.md). Build it only with tools/build_hermes_box.py,
# which checks every pin in pin.json before Docker sees the files.
#
# Base image pinned by digest (the multi-platform index, so the same pin works on a Mac and a
# server). The digest is the pin; BASE only names the registry it is fetched from.
ARG BASE=docker.io/library/python@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8
FROM ${BASE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Hermes's own locked dependencies, every one pinned by hash and installed from wheels only.
COPY requirements.lock /opt/alfred-box/requirements.lock
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-deps --require-hashes --only-binary=:all: \
        -r /opt/alfred-box/requirements.lock \
    && rm -rf /opt/venv/bin/pip* /opt/venv/lib/python*/site-packages/pip*

# Hermes itself at the pinned commit, as a source tree (the layout Hermes supports), never
# installed as a package. tools/build_hermes_box.py exported it from that exact commit.
COPY hermes/ /opt/hermes/
COPY pin.json config.yaml /opt/alfred-box/
COPY runner/ /opt/alfred-box/runner/

RUN useradd --uid 10001 --no-create-home --home-dir /hermes-home --shell /usr/sbin/nologin hermes \
    && chmod -R a-w /opt/hermes /opt/alfred-box /opt/venv

USER 10001:10001
ENV HOME=/hermes-home HERMES_HOME=/hermes-home/.hermes
WORKDIR /work
ENTRYPOINT ["/opt/venv/bin/python", "-I", "/opt/alfred-box/runner/alfred_box.py"]
