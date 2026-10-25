ARG CODEX_VERSION=0.164.0

# Stage 1: Download and extract codex
# Use alpine for the builder stage because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM alpine:3.21 AS builder

ARG CODEX_VERSION
ARG TARGETARCH

RUN apk add --no-cache curl tar gzip

# Upstream tags releases as rust-v<semver>, so the download URL needs the prefix.
RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) ARCH="x86_64" ;; \
      arm64) ARCH="aarch64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/codex.tar.gz \
      "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-${ARCH}-unknown-linux-musl.tar.gz" && \
    tar -xzf /tmp/codex.tar.gz -C /tmp && \
    mv "/tmp/codex-${ARCH}-unknown-linux-musl" /usr/local/bin/codex && \
    chmod +x /usr/local/bin/codex

# Stage 2: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/codex /usr/local/bin/codex

ARG CODEX_VERSION
ENV TOOL_NAME=codex TOOL_VERSION=${CODEX_VERSION}

LABEL org.opencontainers.image.description="Codex CLI tool for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
