FROM alpine:3.21 AS builder

ARG TARGETARCH
ARG UV_VERSION=0.13.6

# musl builds are fully static, so the same binary runs on glibc and musl workspaces.
# The published .sha256 is normalized (awk takes the hash field whether the file is a
# bare hash or the "<hash>  <filename>" sha256sum format) before verifying.
RUN ARCH=$(case "${TARGETARCH}" in amd64) echo "x86_64" ;; arm64) echo "aarch64" ;; *) echo "${TARGETARCH}" ;; esac) && \
    apk add --no-cache curl tar && \
    BASE_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${ARCH}-unknown-linux-musl" && \
    curl -fsSL -o /tmp/uv.tar.gz "${BASE_URL}.tar.gz" && \
    curl -fsSL -o /tmp/uv.tar.gz.sha256 "${BASE_URL}.tar.gz.sha256" && \
    echo "$(awk '{print $1}' /tmp/uv.tar.gz.sha256)  /tmp/uv.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/uv.tar.gz -C /tmp --strip-components=1 && \
    mv /tmp/uv /tmp/uvx /usr/local/bin/ && \
    chmod +x /usr/local/bin/uv /usr/local/bin/uvx

FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx

LABEL org.opencontainers.image.description="uv Python package manager init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
