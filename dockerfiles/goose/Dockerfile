# Stage 1: Download and extract goose
# Use alpine for the builder stage because UBI10 requires x86-64-v3 CPU support,
# which QEMU cannot emulate when cross-building amd64 images on ARM hosts.
FROM alpine:3.21 AS builder

ARG GOOSE_VERSION=v1.28.0
ARG TARGETARCH

RUN apk add --no-cache curl tar bzip2

RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) ARCH="x86_64" ;; \
      arm64) ARCH="aarch64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/goose.tar.bz2 \
      "https://github.com/block/goose/releases/download/${GOOSE_VERSION}/goose-${ARCH}-unknown-linux-gnu.tar.bz2" && \
    tar -xjf /tmp/goose.tar.bz2 -C /tmp && \
    mv /tmp/goose /usr/local/bin/goose && \
    chmod +x /usr/local/bin/goose

# Stage 2: Fetch libgomp for the target architecture
# Uses alpine with rpm2cpio to extract libgomp from the CentOS Stream 10 RPM,
# avoiding QEMU issues with running microdnf on UBI10 during cross-builds.
FROM alpine:3.21 AS libgomp

ARG TARGETARCH

RUN apk add --no-cache curl rpm2cpio cpio

RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) RPMARCH="x86_64" ;; \
      arm64) RPMARCH="aarch64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    REPO_URL="https://mirror.stream.centos.org/10-stream/BaseOS/${RPMARCH}/os/Packages" && \
    RPM_NAME=$(curl -fsSL "${REPO_URL}/" | grep -o 'libgomp-[^"]*\.rpm' | head -1) && \
    curl -fsSL -o /tmp/libgomp.rpm "${REPO_URL}/${RPM_NAME}" && \
    cd /tmp && rpm2cpio libgomp.rpm | cpio -idmv 2>/dev/null && \
    mkdir -p /out && \
    find /tmp -name 'libgomp.so*' -exec cp -P {} /out/ \;

# Stage 3: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=libgomp /out/libgomp.so* /usr/lib64/
COPY --from=builder /usr/local/bin/goose /usr/local/bin/goose

LABEL org.opencontainers.image.description="Goose CLI tool for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
