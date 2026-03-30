FROM alpine:3.21 AS builder

ARG TARGETARCH
ARG TMUX_VERSION=3.6a

RUN ARCH=$(case "${TARGETARCH}" in amd64) echo "x86_64" ;; arm64) echo "arm64" ;; *) echo "${TARGETARCH}" ;; esac) && \
    wget -qO- "https://github.com/tmux/tmux-builds/releases/download/v${TMUX_VERSION}/tmux-${TMUX_VERSION}-linux-${ARCH}.tar.gz" \
      | tar xz -C /usr/local/bin tmux

FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/tmux /usr/local/bin/tmux

LABEL org.opencontainers.image.description="tmux init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
