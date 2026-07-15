# Stage 1: Download Cursor CLI bundle via minimal install script
# Alpine builder: UBI10 requires x86-64-v3, QEMU can't emulate amd64 on ARM hosts.
FROM alpine:3.21 AS builder

ARG CURSOR_CLI_VERSION=2026.07.13-7fe37d2
ARG CURSOR_CLI_CHANNEL=lab
ARG TARGETARCH

ENV CURSOR_CLI_VERSION=${CURSOR_CLI_VERSION} \
    CURSOR_CLI_CHANNEL=${CURSOR_CLI_CHANNEL} \
    TARGETARCH=${TARGETARCH}

RUN apk add --no-cache curl tar
COPY dockerfiles/cursor-cli/install.sh /tmp/install.sh
RUN chmod +x /tmp/install.sh && /tmp/install.sh

# Stage 2: Minimal runtime image (init container only)
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /opt/cursor-cli /opt/cursor-cli

LABEL org.opencontainers.image.description="Cursor CLI init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
