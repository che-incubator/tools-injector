# Stage 1: Download claude-code binary
# Use alpine for the builder stage because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM alpine:3.21 AS builder

ARG CLAUDE_CODE_VERSION=2.1.81
ARG TARGETARCH

RUN apk add --no-cache curl

RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) PLATFORM="linux-x64" ;; \
      arm64) PLATFORM="linux-arm64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL -o /usr/local/bin/claude \
      "https://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases/${CLAUDE_CODE_VERSION}/${PLATFORM}/claude" && \
    chmod +x /usr/local/bin/claude

# Stage 2: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/claude /usr/local/bin/claude

LABEL org.opencontainers.image.description="Claude Code CLI tool for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
