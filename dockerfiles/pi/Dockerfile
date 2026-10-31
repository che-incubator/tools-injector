ARG PI_VERSION=1.4.0

# Stage 1: install pi on a multi-arch Node image.
# ubi9/nodejs-22-minimal supports amd64, arm64, ppc64le, and s390x.
# UBI9 is used instead of UBI10 because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM registry.access.redhat.com/ubi9/nodejs-22-minimal:1 AS npm-installer

ARG PI_VERSION

# --ignore-scripts: pi's npm payload needs no install scripts, and skipping
# them keeps the build hermetic. Transitive deps are not pinned (unlike the
# pi.dev installer), but the built image is immutable, which is acceptable
# for image-based distribution.
RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent@${PI_VERSION} && \
    npm cache clean --force

# Verify binary exists
RUN which pi

# Stage 2: obtain the official Node.js binary from nodejs.org.
# pi requires Node >= 22.19; the ubi9/ubi10 node binaries are dynamically
# linked against libnode.so, which is not present in ubi10/ubi-minimal.
# The official upstream tarball is a self-contained binary that works on
# any modern Linux.
FROM alpine:3.21 AS node-provider

ARG TARGETARCH
ARG NODE_VERSION=22.23.4

RUN apk add --no-cache curl xz && \
    case "${TARGETARCH}" in \
      amd64) NODE_ARCH="x64" ;; \
      arm64) NODE_ARCH="arm64" ;; \
      s390x) NODE_ARCH="s390x" ;; \
      ppc64le) NODE_ARCH="ppc64le" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
      -o /tmp/node.tar.xz && \
    tar -xJf /tmp/node.tar.xz -C /tmp && \
    cp /tmp/node-v${NODE_VERSION}-linux-${NODE_ARCH}/bin/node /usr/local/bin/node

# The pi bin wrapper. Generated here (alpine) rather than in the runtime
# stage because ubi10 requires x86-64-v3, which QEMU cannot emulate when
# cross-building amd64 images on ARM hosts — the runtime stage must stay
# COPY-only.
RUN printf '#!/bin/sh\nDIR=$(dirname "$(readlink -f "$0")")\nexec "$DIR/node" "$DIR/../lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" "$@"\n' > /usr/local/bin/pi && \
    chmod +x /usr/local/bin/pi

# Stage 3: assemble the bundle into a minimal runtime image.
# Used as init container — copies bundle to shared volume, then exits.
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=node-provider /usr/local/bin/node /opt/pi/bin/node
COPY --from=node-provider /usr/local/bin/pi /opt/pi/bin/pi
COPY --from=npm-installer /opt/app-root/src/.npm-global/lib/node_modules /opt/pi/lib/node_modules

ARG PI_VERSION
ENV TOOL_NAME=pi TOOL_VERSION=${PI_VERSION}

LABEL org.opencontainers.image.description="Pi coding agent init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
