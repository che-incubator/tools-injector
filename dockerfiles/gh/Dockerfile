FROM alpine:3.21 AS builder
ARG GH_VERSION=2.95.0
ARG TARGETARCH
RUN apk add --no-cache curl tar
RUN case "$TARGETARCH" in \
      amd64) ARCH="amd64" ;; \
      arm64) ARCH="arm64" ;; \
    esac && \
    curl -fsSL -o /tmp/gh.tar.gz \
      "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.tar.gz" && \
    tar -xzf /tmp/gh.tar.gz -C /tmp && \
    mv /tmp/gh_${GH_VERSION}_linux_${ARCH}/bin/gh /usr/local/bin/gh && \
    chmod +x /usr/local/bin/gh

FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0
COPY --from=builder /usr/local/bin/gh /usr/local/bin/gh
LABEL description="GitHub CLI (gh) injector for Eclipse Che workspaces" \
      source="https://github.com/che-incubator/tools-injector"
