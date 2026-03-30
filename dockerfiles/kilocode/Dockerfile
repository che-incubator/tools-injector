# Stage 1: Install kilocode with Node.js
FROM node:22-slim AS builder

RUN npm install -g @kilocode/cli && \
    npm cache clean --force

RUN which kilo

# Bundle node + kilocode into /bundle for copying
RUN mkdir -p /bundle/bin /bundle/lib && \
    cp /usr/local/bin/node /bundle/bin/ && \
    cp -a /usr/local/lib/node_modules /bundle/lib/ && \
    cp -a /usr/local/bin/kilo /bundle/bin/kilo

# Stage 2: Minimal image containing the bundle
# Used as init container — copies bundle to shared volume, then exits.
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /bundle /opt/kilocode

LABEL org.opencontainers.image.description="Kilo Code CLI init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
