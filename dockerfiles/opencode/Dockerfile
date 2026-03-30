# Stage 1: Download and extract opencode
# Use alpine for the builder stage because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM alpine:3.21 AS builder

ARG OPENCODE_VERSION=v1.2.27
ARG TARGETARCH

RUN apk add --no-cache curl tar gzip

RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) ARCH="x64" ;; \
      arm64) ARCH="arm64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/opencode.tar.gz \
      "https://github.com/anomalyco/opencode/releases/download/${OPENCODE_VERSION}/opencode-linux-${ARCH}.tar.gz" && \
    tar -xzf /tmp/opencode.tar.gz -C /tmp && \
    mv /tmp/opencode /usr/local/bin/opencode && \
    chmod +x /usr/local/bin/opencode

# Stage 2: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/opencode /usr/local/bin/opencode

LABEL org.opencontainers.image.description="Opencode CLI tool for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
