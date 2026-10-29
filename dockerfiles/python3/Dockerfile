# Python3 bundle from python-build-standalone (PBS) glibc releases.
# Both ARGs below are rewritten by the version-bump workflow; keep the exact form.
ARG PYTHON3_VERSION=3.13.18
ARG PYTHON3_PBS_RELEASE=20261026

# Stage 1: Download and verify the python-build-standalone bundle.
# Use alpine for the builder stage because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM alpine:3.21 AS builder

ARG PYTHON3_VERSION
ARG PYTHON3_PBS_RELEASE
ARG TARGETARCH

RUN apk add --no-cache curl tar gzip

# The tarball extracts to a single top-level "python" directory (bin/, include/,
# lib/, share/) that is relocatable: no wrapper script and no PYTHONHOME needed.
# Save the tarball under its real name (with "+") so sha256sum -c can find it;
# in the URL the "+" must be encoded as %2B. The grep is chained with && so a
# missing checksum line fails the build instead of skipping verification.
RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) ARCH="x86_64" ;; \
      arm64) ARCH="aarch64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    mkdir -p /tmp/pbs && \
    ASSET="cpython-${PYTHON3_VERSION}+${PYTHON3_PBS_RELEASE}-${ARCH}-unknown-linux-gnu-install_only_stripped.tar.gz" && \
    curl -fsSL -o "/tmp/pbs/${ASSET}" \
      "https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON3_PBS_RELEASE}/cpython-${PYTHON3_VERSION}%2B${PYTHON3_PBS_RELEASE}-${ARCH}-unknown-linux-gnu-install_only_stripped.tar.gz" && \
    curl -fsSL -o /tmp/pbs/SHA256SUMS \
      "https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON3_PBS_RELEASE}/SHA256SUMS" && \
    grep -F "  ${ASSET}" /tmp/pbs/SHA256SUMS > /tmp/pbs/checksum.txt && \
    cd /tmp/pbs && \
    sha256sum -c checksum.txt && \
    tar -xzf "${ASSET}" -C /tmp/pbs && \
    mv /tmp/pbs/python /opt/python3 && \
    rm -rf /tmp/pbs

# TEMPORARY (python3-init-compat): stage a /usr/local/bin/python3 symlink for
# the runtime COPY below. Remove with it (see the runtime-stage comment).
RUN mkdir -p /compat/usr/local/bin && \
    ln -s /opt/python3/bin/python3 /compat/usr/local/bin/python3

# Stage 2: Minimal runtime image.
# Used as init container — copies the bundle to the shared volume, then exits.
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /opt/python3 /opt/python3

# TEMPORARY (python3-init-compat): workspaces injected before the bundle switch
# in #183 still run `cp /usr/local/bin/python3 /injected-tools/python3` in their
# old init container; this symlink keeps that cp working (cp follows symlinks).
# REMOVAL TRIGGER: Remove this and the builder step once no DevWorkspace still
# carries the pre-#183 python3 init container (args /usr/local/bin/python3);
# find all pieces with: grep -rn python3-init-compat
COPY --from=builder /compat/usr/local/bin/python3 /usr/local/bin/python3

ARG PYTHON3_VERSION
ENV TOOL_NAME=python3 TOOL_VERSION=${PYTHON3_VERSION}

LABEL org.opencontainers.image.description="Python3 bundle (python-build-standalone) for DevWorkspace tool injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
