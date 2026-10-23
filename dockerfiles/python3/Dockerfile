# Stage 1: Get python3 + stdlib from the official Python image (Alpine/musl)
# PYTHON3_VERSION must stay before FROM so it selects the image; the version-bump workflow rewrites this line.
ARG PYTHON3_VERSION=3.13.17
FROM python:${PYTHON3_VERSION}-alpine3.23 AS builder

# /usr/local/bin/python3 is a symlink to python3.X - replace it with the real
# binary so that COPY --from keeps a regular file rather than a dangling link
RUN PYTHON_BIN=$(readlink -f /usr/local/bin/python3) && \
    rm /usr/local/bin/python3 && \
    cp "$PYTHON_BIN" /usr/local/bin/python3

# Stage 2: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/python3 /usr/local/bin/python3
# Explicit destination: COPY of a directory copies its contents, so the stdlib
# directory name must be repeated. Update the minor version here when moving to 3.14+.
COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=builder /usr/local/lib/libpython3.13.so* /usr/lib64/

# Set PYTHONHOME so python3 finds its stdlib
ENV PYTHONHOME=/usr/local

LABEL org.opencontainers.image.description="Python3 runtime for DevWorkspace tool injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
