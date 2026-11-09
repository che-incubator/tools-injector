# lola (lola-ai on PyPI) on a python-build-standalone (PBS) glibc bundle.
# LOLA_VERSION is rewritten by the version-bump workflow; keep the exact form.
# PYTHON_VERSION/PYTHON_PBS_RELEASE mirror the PYTHON3_* pins in dockerfiles/python3:
# the python3 version bump rewrites them here in the same PR (keep the exact
# form) and builds this image with them before opening the PR, and pr.yml
# (check-registry-versions) fails on manual drift.
# lola-ai requires Python >= 3.13.
ARG LOLA_VERSION=0.7.1
# python3's PBS pins (rewritten by the python3 bump)
ARG PYTHON_VERSION=3.13.18
ARG PYTHON_PBS_RELEASE=20261026

# Stage 1: download and verify the python-build-standalone bundle (same steps
# as dockerfiles/python3). Alpine because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM alpine:3.21 AS builder

ARG PYTHON_VERSION
ARG PYTHON_PBS_RELEASE
ARG TARGETARCH

RUN apk add --no-cache curl tar gzip

RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) ARCH="x86_64" ;; \
      arm64) ARCH="aarch64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    mkdir -p /tmp/pbs && \
    ASSET="cpython-${PYTHON_VERSION}+${PYTHON_PBS_RELEASE}-${ARCH}-unknown-linux-gnu-install_only_stripped.tar.gz" && \
    curl -fsSL -o "/tmp/pbs/${ASSET}" \
      "https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_PBS_RELEASE}/cpython-${PYTHON_VERSION}%2B${PYTHON_PBS_RELEASE}-${ARCH}-unknown-linux-gnu-install_only_stripped.tar.gz" && \
    curl -fsSL -o /tmp/pbs/SHA256SUMS \
      "https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_PBS_RELEASE}/SHA256SUMS" && \
    grep -F "  ${ASSET}" /tmp/pbs/SHA256SUMS > /tmp/pbs/checksum.txt && \
    cd /tmp/pbs && \
    sha256sum -c checksum.txt && \
    tar -xzf "${ASSET}" -C /tmp/pbs && \
    mv /tmp/pbs/python /opt/lola && \
    rm -rf /tmp/pbs

# Stage 2: pip-install lola-ai with the bundled interpreter.
# The PBS python is a glibc build and cannot run on alpine (musl), so this
# stage uses UBI9 (glibc, QEMU-safe unlike UBI10). Running the bundle's own
# pip picks wheels matching that exact interpreter (pyyaml ships C wheels).
# Transitive dependencies are not pinned; the built image is immutable.
FROM registry.access.redhat.com/ubi9/ubi-minimal:9.8 AS pip-installer

ARG LOLA_VERSION

COPY --from=builder /opt/lola /opt/lola

RUN /opt/lola/bin/python3 -m pip install --no-cache-dir --disable-pip-version-check \
      --root-user-action=ignore "lola-ai==${LOLA_VERSION}"

# Replace pip's console script: its shebang hardcodes /opt/lola/bin/python3,
# which breaks once the bundle is copied to /injected-tools/lola/. The wrapper
# resolves its own location (it is reached through the /injected-tools/bin
# symlink). -I keeps the user's cwd and PYTHON* env vars off sys.path; -c with
# argv[0]="lola" (not -m) keeps click's program name, which also names the
# _LOLA_COMPLETE shell-completion variable.
RUN printf '%s\n' \
      '#!/bin/sh' \
      'DIR=$(dirname "$(readlink -f "$0")")' \
      'exec "$DIR/python3" -I -c '\''import sys; from lola.__main__ import main; sys.argv[0] = "lola"; sys.exit(main())'\'' "$@"' \
      > /opt/lola/bin/lola && \
    chmod +x /opt/lola/bin/lola

# Verify the bundle works after relocation, as it will in the workspace
RUN cp -a /opt/lola /tmp/lola-relocated && \
    out=$(/tmp/lola-relocated/bin/lola --version) && \
    if [ "$out" != "lola ${LOLA_VERSION}" ]; then \
      echo "unexpected lola --version output: $out" >&2; exit 1; \
    fi && \
    rm -rf /tmp/lola-relocated

# Stage 3: minimal runtime image.
# Used as init container — copies the bundle to the shared volume, then exits.
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=pip-installer /opt/lola /opt/lola

ARG LOLA_VERSION
ENV TOOL_NAME=lola TOOL_VERSION=${LOLA_VERSION}

LABEL org.opencontainers.image.description="lola AI context package manager (python-build-standalone bundle) for DevWorkspace tool injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
