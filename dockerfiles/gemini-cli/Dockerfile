# Stage 1: Install gemini-cli with Node.js
FROM node:22-slim AS builder

RUN npm install -g @google/gemini-cli && \
    npm cache clean --force

# Verify binary exists
RUN which gemini

# Bundle node + gemini into /bundle for copying
RUN mkdir -p /bundle/bin /bundle/lib && \
    cp /usr/local/bin/node /bundle/bin/ && \
    cp -a /usr/local/lib/node_modules /bundle/lib/ && \
    cp -a /usr/local/bin/gemini /bundle/bin/gemini

# Stage 2: Minimal image containing the bundle
# Used as init container — copies bundle to shared volume, then exits.
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /bundle /opt/gemini-cli

LABEL org.opencontainers.image.description="Gemini CLI init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
