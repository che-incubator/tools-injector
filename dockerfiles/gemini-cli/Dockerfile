ARG GEMINI_CLI_VERSION=0.65.0

# Stage 1: install gemini-cli on a multi-arch Node image.
# ubi9/nodejs-22-minimal supports amd64, arm64, ppc64le, and s390x.
# UBI9 is used instead of UBI10 because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM registry.access.redhat.com/ubi9/nodejs-22-minimal:1 AS npm-installer

ARG GEMINI_CLI_VERSION

RUN npm install -g @google/gemini-cli@${GEMINI_CLI_VERSION} && \
    npm cache clean --force

# Verify binary exists
RUN which gemini

# Stage 2: obtain the official Node.js binary from nodejs.org.
# The ubi10 node binary is dynamically linked against libnode.so.127,
# which is not present in ubi10/ubi-minimal. The official upstream tarball
# is a self-contained binary that works on any modern Linux.
FROM alpine:3.21 AS node-provider

ARG TARGETARCH
ARG NODE_VERSION=22.16.0

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

# The gemini bin wrapper. The npm bin symlink cannot be COPYed (COPY
# dereferences it into a standalone script that fails to resolve its sibling
# imports), so generate an sh wrapper that runs the real entrypoint with the
# bundled node. Generated here (alpine) rather than in the runtime stage
# because ubi10 requires x86-64-v3, which QEMU cannot emulate when
# cross-building amd64 images on ARM hosts — the runtime stage must stay
# COPY-only.
RUN printf '#!/bin/sh\nDIR=$(dirname "$(readlink -f "$0")")\nexec "$DIR/node" "$DIR/../lib/node_modules/@google/gemini-cli/bundle/gemini.js" "$@"\n' > /usr/local/bin/gemini && \
    chmod +x /usr/local/bin/gemini

# Stage 3: assemble the bundle into a minimal runtime image.
# Used as init container — copies bundle to shared volume, then exits.
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=node-provider /usr/local/bin/node /opt/gemini-cli/bin/node
COPY --from=node-provider /usr/local/bin/gemini /opt/gemini-cli/bin/gemini
COPY --from=npm-installer /opt/app-root/src/.npm-global/lib/node_modules /opt/gemini-cli/lib/node_modules

ARG GEMINI_CLI_VERSION
ENV TOOL_NAME=gemini-cli TOOL_VERSION=${GEMINI_CLI_VERSION}

LABEL org.opencontainers.image.description="Gemini CLI init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
