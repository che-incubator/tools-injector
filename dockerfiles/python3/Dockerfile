# Stage 1: Get python3 + stdlib from Alpine
FROM alpine:3.21 AS builder

RUN apk add --no-cache python3 && \
    # Find the actual python3 binary (not the symlink)
    PYTHON_BIN=$(readlink -f /usr/bin/python3) && \
    cp "$PYTHON_BIN" /usr/local/bin/python3 && \
    chmod +x /usr/local/bin/python3 && \
    # Copy stdlib (needed for json, urllib, ssl, etc.)
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") && \
    mkdir -p /usr/local/lib/python${PYTHON_VERSION} && \
    cp -a /usr/lib/python${PYTHON_VERSION}/* /usr/local/lib/python${PYTHON_VERSION}/ && \
    # Copy required shared libraries
    mkdir -p /usr/local/lib && \
    cp /usr/lib/libpython${PYTHON_VERSION}.so* /usr/local/lib/ 2>/dev/null || true

# Stage 2: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/python3 /usr/local/bin/python3
COPY --from=builder /usr/local/lib/python* /usr/local/lib/
COPY --from=builder /usr/local/lib/libpython* /usr/lib64/

# Set PYTHONHOME so python3 finds its stdlib
ENV PYTHONHOME=/usr/local

LABEL org.opencontainers.image.description="Python3 runtime for DevWorkspace tool injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
